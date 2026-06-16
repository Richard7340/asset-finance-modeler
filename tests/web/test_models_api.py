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


def test_svj_hybrid_run_has_statements(monkeypatch):
    """P3-2: svj_hybrid /run returns income_statement + cash_flow (consolidated
    P&L/CF of the hybrid) so a generic client consumes it like any other model,
    while keeping the legacy keys (bridge/cashflows/curves/dscr_profile/kpis)."""
    c = _client(monkeypatch)
    out = c.post("/api/models/svj_hybrid/run?t=tk", json={"overrides": {}}).json()
    # legacy keys preserved
    for k in ("bridge", "cashflows", "curves", "dscr_profile", "kpis"):
        assert k in out, f"missing legacy key {k}"
    # new generic keys
    assert "income_statement" in out and "cash_flow" in out
    rows = out["income_statement"]["rows"]
    assert "revenue" in rows and len(rows["revenue"]) >= 1
    assert out["income_statement"]["years"][0] == 1
    assert "cfo" in out["cash_flow"]


def test_saas_listed_schema_and_run(monkeypatch):
    """P3-6: a SaaS model is reachable via /api/models like any other model —
    listed, schema introspectable, and runs into kpis+income_statement+cash_flow.
    """
    c = _client(monkeypatch)
    models = c.get("/api/models?t=tk").json()["models"]
    saas = [m for m in models if m["asset_type"] == "saas"]
    assert saas, "no SaaS model listed"
    sid = saas[0]["id"]

    leaves = c.get(f"/api/models/{sid}/schema?t=tk").json()["inputs"]
    assert leaves and any(l["section"] == "revenue" for l in leaves)

    out = c.post(f"/api/models/{sid}/run?t=tk", json={"overrides": {}}).json()
    assert "kpis" in out and "income_statement" in out and "cash_flow" in out
    rows = out["income_statement"]["rows"]
    assert "revenue" in rows and len(rows["revenue"]) >= 1
    assert "npv" in out["kpis"]  # EV exposed as npv for portfolio compatibility


def test_invalid_override_path_returns_400(monkeypatch):
    """P3-3: a bad override path is a client error (400 with the offending
    path), not a server 500."""
    c = _client(monkeypatch)
    r = c.post(
        "/api/models/bess_20mw_4h/run?t=tk",
        json={"overrides": {"production.does_not_exist.deep": 5}},
    )
    assert r.status_code == 400
    assert "production.does_not_exist.deep" in r.json()["detail"]


def test_out_of_range_override_returns_400(monkeypatch):
    """FIX 2: an out-of-range override (violates a Pydantic bound) is a client
    error (400) with a clear field message, not a 500."""
    c = _client(monkeypatch)
    r = c.post(
        "/api/models/saas_gestnova/run?t=tk",
        json={"overrides": {"revenue.sources[0].retention.monthly_churn_rate": 1.5}},
    )
    assert r.status_code == 400, r.text
    assert "monthly_churn_rate" in r.json()["detail"]


def test_valid_saas_override_still_runs(monkeypatch):
    """A valid in-range override still returns 200."""
    c = _client(monkeypatch)
    r = c.post(
        "/api/models/saas_gestnova/run?t=tk",
        json={"overrides": {"revenue.sources[0].retention.monthly_churn_rate": 0.02}},
    )
    assert r.status_code == 200, r.text
    assert "kpis" in r.json()
