from fastapi.testclient import TestClient


def _client(monkeypatch, tmp_path):
    monkeypatch.setenv("SIM_TOKEN", "tk")
    monkeypatch.setenv("SIM_ONLY", "1")
    monkeypatch.setenv("ASSET_FINANCE_DB_PATH", str(tmp_path))
    from asset_finance_modeler.mcp_server.http_server import app
    return TestClient(app)


def _operational_asset(c, commissioning="2026-01-01T00:00:00") -> str:
    aid = c.post(
        "/api/assets?t=tk",
        json={"model_id": "bess_20mw_4h", "name": "B", "overrides": {}},
    ).json()["id"]
    c.patch(
        f"/api/assets/{aid}/lifecycle?t=tk",
        json={
            "lifecycle": "operational",
            "tracking_frequency": "monthly",
            "commissioning_date": commissioning,
        },
    )
    return aid


def _base_revenue(c, aid) -> list[float]:
    snap = c.get(f"/api/assets/{aid}?t=tk").json()["results_snapshot"]
    return snap["income_statement"]["rows"]["revenue"]


def test_variance_revenue_year1(monkeypatch, tmp_path):
    # Año 0 (2026) ya terminado: se compara con el año entero (el año EN CURSO
    # se compara hasta hoy, ver test_variance_anio_en_curso_hasta_hoy).
    import asset_finance_modeler.web_api.actuals as _act
    from datetime import datetime as _dt
    monkeypatch.setattr(_act, '_hoy', lambda: _dt(2027, 6, 1))
    c = _client(monkeypatch, tmp_path)
    aid = _operational_asset(c)
    base = _base_revenue(c, aid)
    # Two monthly actuals in model year 0 (2026) for revenue -> aggregate.
    c.post(
        f"/api/assets/{aid}/actuals?t=tk",
        json={
            "actuals": [
                {"period_start": "2026-01-01",
                 "line_path": "income_statement.rows.revenue", "value": 100.0},
                {"period_start": "2026-02-01",
                 "line_path": "income_statement.rows.revenue", "value": 150.0},
            ]
        },
    )
    r = c.get(f"/api/assets/{aid}/variance?t=tk&line_path=income_statement.rows.revenue")
    assert r.status_code == 200
    lines = r.json()["lines"]
    assert len(lines) == 1
    ln = lines[0]
    assert ln["line_path"] == "income_statement.rows.revenue"
    assert ln["base"] == base
    # Year 0 actual is aggregated; later years have no data -> null.
    assert ln["actual"][0] == 250.0
    assert all(v is None for v in ln["actual"][1:])
    # Deviation year 0 = actual - base.
    assert ln["deviation"][0] == 250.0 - base[0]
    assert ln["deviation"][1] is None
    # deviation_pct present for year 0.
    assert ln["deviation_pct"][0] is not None
    assert ln["deviation_pct"][1] is None
    # Cumulative + fulfillment use only the years that have actuals.
    assert ln["cumulative_actual"] == 250.0
    assert ln["cumulative_base"] == base[0]
    assert ln["fulfillment_pct"] is not None


def test_variance_all_lines(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    aid = _operational_asset(c)
    r = c.get(f"/api/assets/{aid}/variance?t=tk")
    assert r.status_code == 200
    lines = r.json()["lines"]
    paths = {ln["line_path"] for ln in lines}
    assert "income_statement.rows.revenue" in paths
    # No actuals at all -> actual series is all null.
    rev = next(ln for ln in lines if ln["line_path"] == "income_statement.rows.revenue")
    assert all(v is None for v in rev["actual"])
    assert rev["cumulative_actual"] == 0.0
    assert rev["fulfillment_pct"] is None  # nothing to compare


def test_variance_requires_token(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    aid = _operational_asset(c)
    assert c.get(f"/api/assets/{aid}/variance").status_code == 401


def test_variance_unknown_asset_404(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    assert c.get("/api/assets/scn-nope/variance?t=tk").status_code == 404


def test_variance_year_offset_by_commissioning(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    aid = _operational_asset(c, commissioning="2026-01-01T00:00:00")
    # Actual in 2027 -> model year index 1.
    c.post(
        f"/api/assets/{aid}/actuals?t=tk",
        json={"actuals": [{"period_start": "2027-06-01",
                           "line_path": "income_statement.rows.revenue", "value": 500.0}]},
    )
    r = c.get(f"/api/assets/{aid}/variance?t=tk&line_path=income_statement.rows.revenue")
    ln = r.json()["lines"][0]
    assert ln["actual"][0] is None
    assert ln["actual"][1] == 500.0


def test_variance_anio_en_curso_hasta_hoy(monkeypatch, tmp_path):
    """26-sep: con datos hasta marzo, el año en curso se compara con su
    previsión hasta hoy, no con el año entero; y sale el detalle mes a mes."""
    import asset_finance_modeler.web_api.actuals as act
    from datetime import datetime as dt
    monkeypatch.setattr(act, "_hoy", lambda: dt(2026, 4, 1))
    c = _client(monkeypatch, tmp_path)
    aid = _operational_asset(c)
    base = _base_revenue(c, aid)
    c.post(f"/api/assets/{aid}/actuals?t=tk", json={"actuals": [
        {"period_start": "2026-01-15", "line_path": "income_statement.rows.revenue", "value": 100.0},
        {"period_start": "2026-03-10", "line_path": "income_statement.rows.revenue", "value": 50.0},
    ]})
    ln = c.get(f"/api/assets/{aid}/variance?t=tk&line_path=income_statement.rows.revenue").json()["lines"][0]
    frac = ln["fraccion_del_anio"]
    assert 0.24 < frac < 0.26
    assert ln["anio_en_curso"] == 0
    assert abs(ln["base_comparada"][0] - base[0] * frac) < 1
    assert abs(ln["deviation"][0] - (150.0 - base[0] * frac)) < 1
    assert ln["mensual"][0] == {"mes": 1, "real": 100.0, "prevision": round(base[0] / 12, 4)}
    assert ln["mensual"][1]["real"] is None
