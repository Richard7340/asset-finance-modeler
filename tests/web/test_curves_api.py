from fastapi.testclient import TestClient


def _client(monkeypatch):
    monkeypatch.setenv("SIM_TOKEN", "tk"); monkeypatch.setenv("SIM_ONLY", "1")
    from asset_finance_modeler.mcp_server.http_server import app
    return TestClient(app)


def test_list_curves_with_source_and_values(monkeypatch):
    c = _client(monkeypatch)
    data = c.get("/api/curves?t=tk").json()["curves"]
    names = {cv["name"] for cv in data}
    assert {"spread_da_es", "ancillary_afrr_es", "solar_capture_es"} <= names
    spread = next(cv for cv in data if cv["name"] == "spread_da_es")
    assert "Agere" in spread["source"] or "Modo" in spread["source"]
    assert len(spread["values"]) == 30
    assert spread["values"][0] > 0


def test_p1_consultant_curves_listed_with_metadata(monkeypatch):
    c = _client(monkeypatch)
    data = c.get("/api/curves?t=tk").json()["curves"]
    by_name = {cv["name"]: cv for cv in data}
    for n in ("wind_capture_es", "h2_offtake_eu", "biomethane_offtake_eu", "ppa_solar_es"):
        assert n in by_name, f"{n} not listed by /api/curves"
        cv = by_name[n]
        assert cv["source"]
        assert cv["bankable"] is not None
        assert len(cv["values"]) == 30


def test_get_single_curve_and_404(monkeypatch):
    c = _client(monkeypatch)
    assert c.get("/api/curves/solar_capture_es?t=tk").status_code == 200
    assert c.get("/api/curves/nope_xyz?t=tk").status_code == 404
