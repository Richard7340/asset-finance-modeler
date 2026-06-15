from fastapi.testclient import TestClient


def _client(monkeypatch, tmp_path):
    monkeypatch.setenv("SIM_TOKEN", "tk")
    monkeypatch.setenv("SIM_ONLY", "1")
    monkeypatch.setenv("ASSET_FINANCE_DB_PATH", str(tmp_path))
    from asset_finance_modeler.mcp_server.http_server import app
    return TestClient(app)


def test_portfolio_filters_by_lifecycle(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    a1 = c.post("/api/assets?t=tk", json={"model_id": "bess_20mw_4h", "name": "Op"}).json()["id"]
    c.post("/api/assets?t=tk", json={"model_id": "bess_20mw_4h", "name": "Opp"})
    c.patch(f"/api/assets/{a1}/lifecycle?t=tk", json={"lifecycle": "operational"})

    op = c.get("/api/portfolio?t=tk&lifecycle=operational").json()
    assert op["totals"]["count"] == 1
    assert [a["id"] for a in op["assets"]] == [a1]

    opp = c.get("/api/portfolio?t=tk&lifecycle=opportunity").json()
    assert opp["totals"]["count"] == 1

    all_ = c.get("/api/portfolio?t=tk").json()  # sin filtro = todos (compat v2)
    assert all_["totals"]["count"] == 2
