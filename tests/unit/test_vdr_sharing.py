import asyncio
import json

from asset_finance_modeler.mcp_server.tools.vdr_sharing import (
    handle_explain_vdr,
    handle_import_from_vdr,
    handle_list_workspace_shared,
    handle_share_to_vdr,
)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_share_to_vdr_without_token(monkeypatch):
    monkeypatch.delenv("GESTNOVA_VDR_TOKEN", raising=False)
    result = _run(handle_share_to_vdr({"scenario_id": "test-123", "format": "json"}))
    data = json.loads(result[0]["text"])
    assert data["ok"] is True
    assert data["status"] == "local_only"
    assert data["report"]["scenario_id"] == "test-123"


def test_share_requires_id():
    result = _run(handle_share_to_vdr({}))
    data = json.loads(result[0]["text"])
    assert data["ok"] is False
    assert "required" in data["error"]


def test_share_with_project_id(monkeypatch):
    monkeypatch.delenv("GESTNOVA_VDR_TOKEN", raising=False)
    result = _run(handle_share_to_vdr({"project_id": "proj-456", "format": "markdown"}))
    data = json.loads(result[0]["text"])
    assert data["ok"] is True
    assert data["report"]["project_id"] == "proj-456"
    assert data["report"]["format"] == "markdown"


def test_import_from_vdr_requires_path():
    result = _run(handle_import_from_vdr({}))
    data = json.loads(result[0]["text"])
    assert data["ok"] is False
    assert "vdr_path required" in data["error"]


def test_import_from_vdr_requires_token(monkeypatch):
    monkeypatch.delenv("GESTNOVA_VDR_TOKEN", raising=False)
    result = _run(handle_import_from_vdr({"vdr_path": "reports/test.json"}))
    data = json.loads(result[0]["text"])
    assert data["ok"] is False
    assert "not configured" in data["error"]


def test_list_workspace_shared_requires_token(monkeypatch):
    monkeypatch.delenv("GESTNOVA_VDR_TOKEN", raising=False)
    result = _run(handle_list_workspace_shared({"workspace_id": "ws-1"}))
    data = json.loads(result[0]["text"])
    assert data["ok"] is False
    assert "not configured" in data["error"]


def test_explain_vdr():
    result = _run(handle_explain_vdr({"vdr_path": "reports/test.json"}))
    data = json.loads(result[0]["text"])
    assert data["ok"] is True
    assert "suggested_flow" in data
    assert len(data["suggested_flow"]) == 3


def test_explain_vdr_requires_path():
    result = _run(handle_explain_vdr({}))
    data = json.loads(result[0]["text"])
    assert data["ok"] is False
    assert "vdr_path required" in data["error"]
