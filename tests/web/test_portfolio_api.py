from fastapi.testclient import TestClient


def _client(monkeypatch, tmp_path):
    monkeypatch.setenv("SIM_TOKEN", "tk")
    monkeypatch.setenv("SIM_ONLY", "1")
    monkeypatch.setenv("ASSET_FINANCE_DB_PATH", str(tmp_path))
    from asset_finance_modeler.mcp_server.http_server import app
    return TestClient(app)


def test_portfolio_aggregates_saved_assets(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    c.post("/api/assets?t=tk", json={"model_id": "business_restaurant", "name": "Resto", "overrides": {}})
    c.post("/api/assets?t=tk", json={"model_id": "bess_20mw_4h", "name": "BESS", "overrides": {}})
    p = c.get("/api/portfolio?t=tk").json()
    assert p["totals"]["count"] == 2
    assert len(p["assets"]) == 2
    assert p["totals"]["npv"] != 0
    names = {a["name"] for a in p["assets"]}
    assert {"Resto", "BESS"} == names
