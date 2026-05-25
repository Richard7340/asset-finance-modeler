"""Client for Gestnova VDR (Virtual Data Room) API.

Provides upload/download/list for financial reports shared via VDR.
Auth via GESTNOVA_VDR_TOKEN env var.
"""
import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class VDRFile:
    path: str
    name: str
    size: int = 0
    modified_at: str = ""
    is_directory: bool = False


@dataclass
class VDRClient:
    base_url: str = field(default_factory=lambda: os.environ.get("GESTNOVA_VDR_URL", "http://localhost:4300"))
    token: str = field(default_factory=lambda: os.environ.get("GESTNOVA_VDR_TOKEN", ""))

    @property
    def is_configured(self) -> bool:
        return bool(self.token)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    async def upload(self, workspace_id: str, path: str, content: str | bytes, content_type: str = "application/json") -> dict[str, Any]:
        if not self.is_configured:
            return {"ok": False, "error": "VDR not configured (GESTNOVA_VDR_TOKEN missing)"}
        try:
            import httpx
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    f"{self.base_url}/api/vdr/{workspace_id}/file",
                    headers=self._headers(),
                    json={"path": path, "content": content if isinstance(content, str) else content.decode()},
                )
                if r.status_code < 300:
                    return {"ok": True, "path": path, "workspace_id": workspace_id}
                return {"ok": False, "error": f"Upload failed: {r.status_code}", "body": r.text[:200]}
        except ImportError:
            return {"ok": False, "error": "httpx not installed"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def download(self, workspace_id: str, path: str) -> dict[str, Any]:
        if not self.is_configured:
            return {"ok": False, "error": "VDR not configured"}
        try:
            import httpx
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.get(
                    f"{self.base_url}/api/vdr/{workspace_id}/file",
                    params={"path": path},
                    headers=self._headers(),
                )
                if r.status_code == 200:
                    return {"ok": True, "content": r.text, "path": path}
                return {"ok": False, "error": f"Download failed: {r.status_code}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def list_files(self, workspace_id: str, prefix: str = "") -> dict[str, Any]:
        if not self.is_configured:
            return {"ok": False, "error": "VDR not configured"}
        try:
            import httpx
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.get(
                    f"{self.base_url}/api/vdr/{workspace_id}/tree",
                    headers=self._headers(),
                )
                if r.status_code == 200:
                    data = r.json()
                    files = data if isinstance(data, list) else data.get("files", [])
                    if prefix:
                        files = [f for f in files if str(f.get("path", "")).startswith(prefix)]
                    return {"ok": True, "files": files, "count": len(files)}
                return {"ok": False, "error": f"List failed: {r.status_code}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def export_report_json(self, scenario_data: dict, project_data: dict | None = None) -> str:
        report = {
            "type": "gestnova-financial-report",
            "version": "1.0",
            "generated_at": datetime.now(UTC).isoformat(),
            "scenario": scenario_data,
        }
        if project_data:
            report["project"] = project_data
        return json.dumps(report, indent=2, default=str)

    def export_report_markdown(self, scenario_data: dict, project_data: dict | None = None) -> str:
        lines = [
            f"# Financial Report",
            f"",
            f"**Generated:** {datetime.now(UTC).strftime('%Y-%m-%d %H:%M')}",
            f"",
        ]
        if project_data:
            lines.append(f"## Project: {project_data.get('name', 'Unnamed')}")
            lines.append(f"- Technology: {project_data.get('technology', 'N/A')}")
            lines.append(f"- Capacity: {project_data.get('capacity_mw', 'N/A')} MW")
            lines.append("")

        lines.append(f"## Scenario: {scenario_data.get('name', 'Unnamed')}")

        if "results" in scenario_data:
            results = scenario_data["results"]
            lines.append(f"")
            lines.append(f"### Key Metrics")
            for key, value in results.items():
                if isinstance(value, (int, float)):
                    lines.append(f"- **{key}**: {value:,.2f}")
                else:
                    lines.append(f"- **{key}**: {value}")

        return "\n".join(lines)
