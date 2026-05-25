"""VDR sharing tools — share financial reports to Gestnova VDR."""
import json
import os
from datetime import UTC, datetime


async def handle_share_to_vdr(arguments: dict) -> list:
    """Export a scenario/project report to Gestnova VDR as a shareable file."""
    scenario_id = arguments.get("scenario_id")
    project_id = arguments.get("project_id")
    format_type = arguments.get("format", "json")  # json, markdown, html
    workspace_id = arguments.get("workspace_id")

    if not scenario_id and not project_id:
        return [{"type": "text", "text": json.dumps({"ok": False, "error": "scenario_id or project_id required"})}]

    # Build report data (the actual financial data would come from the store)
    report = {
        "type": "financial-report",
        "generated_at": datetime.now(UTC).isoformat(),
        "scenario_id": scenario_id,
        "project_id": project_id,
        "workspace_id": workspace_id,
        "format": format_type,
    }

    # In production, this would POST to Gestnova VDR API
    vdr_token = os.environ.get("GESTNOVA_VDR_TOKEN", "")
    vdr_base = os.environ.get("GESTNOVA_VDR_URL", "http://localhost:4300")

    if not vdr_token:
        return [{"type": "text", "text": json.dumps({
            "ok": True,
            "status": "local_only",
            "message": "VDR token not configured. Report generated locally.",
            "report": report,
        })}]

    try:
        import httpx  # noqa: PLC0415
        async with httpx.AsyncClient() as client:
            filename = f"financial_report_{scenario_id or project_id}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.{format_type}"
            r = await client.post(
                f"{vdr_base}/api/vdr/{workspace_id or 'default'}/file",
                headers={"Authorization": f"Bearer {vdr_token}"},
                json={"path": f"financial-reports/{filename}", "content": json.dumps(report, indent=2)},
                timeout=30,
            )
            if r.status_code < 300:
                return [{"type": "text", "text": json.dumps({"ok": True, "vdr_path": f"financial-reports/{filename}", "workspace_id": workspace_id})}]
            return [{"type": "text", "text": json.dumps({"ok": False, "error": f"VDR upload failed: {r.status_code}"})}]
    except Exception as e:
        return [{"type": "text", "text": json.dumps({"ok": True, "status": "local_only", "error": str(e), "report": report})}]


async def handle_import_from_vdr(arguments: dict) -> list:
    """Import financial data from a VDR file."""
    vdr_path = arguments.get("vdr_path", "")
    workspace_id = arguments.get("workspace_id")

    if not vdr_path:
        return [{"type": "text", "text": json.dumps({"ok": False, "error": "vdr_path required"})}]

    vdr_token = os.environ.get("GESTNOVA_VDR_TOKEN", "")
    vdr_base = os.environ.get("GESTNOVA_VDR_URL", "http://localhost:4300")

    if not vdr_token:
        return [{"type": "text", "text": json.dumps({"ok": False, "error": "GESTNOVA_VDR_TOKEN not configured"})}]

    try:
        import httpx  # noqa: PLC0415
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{vdr_base}/api/vdr/{workspace_id or 'default'}/file",
                params={"path": vdr_path},
                headers={"Authorization": f"Bearer {vdr_token}"},
                timeout=30,
            )
            if r.status_code == 200:
                return [{"type": "text", "text": json.dumps({"ok": True, "content": r.text, "vdr_path": vdr_path})}]
            return [{"type": "text", "text": json.dumps({"ok": False, "error": f"VDR read failed: {r.status_code}"})}]
    except Exception as e:
        return [{"type": "text", "text": json.dumps({"ok": False, "error": str(e)})}]


async def handle_list_workspace_shared(arguments: dict) -> list:
    """List financial reports shared in a workspace VDR."""
    workspace_id = arguments.get("workspace_id", "default")

    vdr_token = os.environ.get("GESTNOVA_VDR_TOKEN", "")
    vdr_base = os.environ.get("GESTNOVA_VDR_URL", "http://localhost:4300")

    if not vdr_token:
        return [{"type": "text", "text": json.dumps({"ok": False, "error": "GESTNOVA_VDR_TOKEN not configured"})}]

    try:
        import httpx  # noqa: PLC0415
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{vdr_base}/api/vdr/{workspace_id}/tree",
                headers={"Authorization": f"Bearer {vdr_token}"},
                timeout=30,
            )
            if r.status_code == 200:
                tree = r.json()
                # Filter for financial reports
                reports = [f for f in (tree if isinstance(tree, list) else tree.get("files", [])) if "financial" in str(f).lower()]
                return [{"type": "text", "text": json.dumps({"ok": True, "workspace_id": workspace_id, "reports": reports, "total": len(reports)})}]
            return [{"type": "text", "text": json.dumps({"ok": False, "error": f"VDR list failed: {r.status_code}"})}]
    except Exception as e:
        return [{"type": "text", "text": json.dumps({"ok": False, "error": str(e)})}]


async def handle_explain_vdr(arguments: dict) -> list:
    """Explain a financial report from VDR in natural language."""
    vdr_path = arguments.get("vdr_path", "")
    arguments.get("question", "Explica este informe financiero")

    if not vdr_path:
        return [{"type": "text", "text": json.dumps({"ok": False, "error": "vdr_path required"})}]

    return [{"type": "text", "text": json.dumps({
        "ok": True,
        "message": f"To explain '{vdr_path}', first import it with financial.import_from_vdr, then use the scenario tools to analyze it.",
        "suggested_flow": [
            f"1. financial.import_from_vdr(vdr_path='{vdr_path}')",
            "2. Parse the imported data",
            "3. Use scenario comparison tools for analysis",
        ],
    })}]
