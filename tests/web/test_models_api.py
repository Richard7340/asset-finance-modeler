from fastapi.testclient import TestClient


def _client(monkeypatch):
    monkeypatch.setenv("SIM_TOKEN", "tk")
    monkeypatch.setenv("SIM_ONLY", "1")
    from asset_finance_modeler.mcp_server.http_server import app
    return TestClient(app)


def test_list_models(monkeypatch):
    c = _client(monkeypatch)
    ids = {m["id"] for m in c.get("/api/models?t=tk").json()["models"]}
    assert {"bess_20mw_4h", "solar_pv_50mw_spain", "svj_hybrid"} <= ids


def test_model_schema(monkeypatch):
    c = _client(monkeypatch)
    leaves = c.get("/api/models/bess_20mw_4h/schema?t=tk").json()["inputs"]
    sections = {l["section"] for l in leaves}
    assert "production" in sections and "financing" in sections
    assert any(l["path"] == "production.power_mw" for l in leaves)


def test_model_run_with_override_and_statements(monkeypatch):
    c = _client(monkeypatch)
    base = c.post("/api/models/bess_20mw_4h/run?t=tk", json={"overrides": {}}).json()
    assert "income_statement" in base and "cash_flow" in base and "kpis" in base
    assert len(base["income_statement"]["years"]) >= 1
    up = c.post("/api/models/bess_20mw_4h/run?t=tk", json={"overrides": {"production.power_mw": 40}}).json()
    assert up["income_statement"]["rows"]["revenue"][0] != base["income_statement"]["rows"]["revenue"][0]
