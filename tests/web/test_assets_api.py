from fastapi.testclient import TestClient


def test_assets_crud(monkeypatch, tmp_path):
    monkeypatch.setenv("SIM_TOKEN", "tk")
    monkeypatch.setenv("SIM_ONLY", "1")
    monkeypatch.setenv("ASSET_FINANCE_DB_PATH", str(tmp_path))
    from asset_finance_modeler.mcp_server.http_server import app
    c = TestClient(app)
    created = c.post("/api/assets?t=tk", json={"model_id": "bess_20mw_4h", "name": "Mi BESS", "overrides": {}}).json()
    aid = created["id"]
    lst = c.get("/api/assets?t=tk").json()["assets"]
    assert any(a["id"] == aid and a["name"] == "Mi BESS" for a in lst)
    got = c.get(f"/api/assets/{aid}?t=tk").json()
    assert got["model_id"] == "bess_20mw_4h" and "results_snapshot" in got
    c.delete(f"/api/assets/{aid}?t=tk")
    assert all(a["id"] != aid for a in c.get("/api/assets?t=tk").json()["assets"])
