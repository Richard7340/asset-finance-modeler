from fastapi.testclient import TestClient


def _client(monkeypatch):
    monkeypatch.setenv("SIM_TOKEN", "tk")
    monkeypatch.setenv("SIM_ONLY", "1")
    from asset_finance_modeler.mcp_server.http_server import app  # noqa: PLC0415
    return TestClient(app)


def test_business_models_listed_and_runnable(monkeypatch):
    c = _client(monkeypatch)
    ids = {m["id"] for m in c.get("/api/models?t=tk").json()["models"]}
    assert {"business_generic", "business_restaurant", "business_industrial", "real_estate_rental"} <= ids
    sch = c.get("/api/models/business_generic/schema?t=tk").json()["inputs"]
    assert any(leaf["path"].startswith("revenue[0]") for leaf in sch)
    base = c.post("/api/models/business_generic/run?t=tk", json={"overrides": {}}).json()
    assert "income_statement" in base and base["income_statement"]["rows"]["revenue"][0] > 0
    up = c.post(
        "/api/models/business_generic/run?t=tk",
        json={"overrides": {"revenue[0].year1_amount": 9999999}},
    ).json()
    assert up["income_statement"]["rows"]["revenue"][0] != base["income_statement"]["rows"]["revenue"][0]
