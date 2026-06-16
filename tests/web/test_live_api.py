"""F3-2: GET /api/assets/{id}/live — base vs live reprojection + comparison."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient


def _client(monkeypatch, tmp_path):
    monkeypatch.setenv("SIM_TOKEN", "tk")
    monkeypatch.setenv("SIM_ONLY", "1")
    monkeypatch.setenv("ASSET_FINANCE_DB_PATH", str(tmp_path))
    from asset_finance_modeler.mcp_server.http_server import app
    return TestClient(app)


def _operational_asset(c, model_id="bess_20mw_4h", commissioning=None) -> str:
    if commissioning is None:
        # Two years ago so elapsed_years >= 2.
        commissioning = datetime(datetime.now(timezone.utc).year - 2, 1, 1).isoformat()
    aid = c.post(
        "/api/assets?t=tk",
        json={"model_id": model_id, "name": "B", "overrides": {}},
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


def _opportunity_asset(c, model_id="bess_20mw_4h") -> str:
    return c.post(
        "/api/assets?t=tk",
        json={"model_id": model_id, "name": "Opp", "overrides": {}},
    ).json()["id"]


def test_live_requires_token(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    aid = _operational_asset(c)
    assert c.get(f"/api/assets/{aid}/live").status_code == 401


def test_live_unknown_asset_404(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    assert c.get("/api/assets/scn-nope/live?t=tk").status_code == 404


def test_live_non_operational_422(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    aid = _opportunity_asset(c)
    r = c.get(f"/api/assets/{aid}/live?t=tk")
    assert r.status_code in (400, 422)
    assert "operation" in r.json()["detail"].lower() or \
        "operativ" in r.json()["detail"].lower()


def test_live_no_actuals_equals_base(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    aid = _operational_asset(c)
    r = c.get(f"/api/assets/{aid}/live?t=tk")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) >= {"base", "live", "comparison"}
    assert "kpis" in body["base"] and "income_statement" in body["base"]
    assert "kpis" in body["live"] and "cash_flow" in body["live"]
    # No actuals -> live == base.
    assert body["comparison"]["npv_base"] == body["comparison"]["npv_live"]
    assert body["comparison"]["delta"] == 0.0


def test_live_real_estate_base_npv_matches_stored_not_spurious_negative(
    monkeypatch, tmp_path
):
    """Real estate's base valuation includes a residual sale at horizon end, so
    the LIVE recomputed ``npv_base`` must carry that residual too: it should be
    close to the asset's STORED base NPV (positive), not a spurious large
    negative from ignoring the exit inflow."""
    c = _client(monkeypatch, tmp_path)
    aid = _operational_asset(c, model_id="real_estate_rental")
    stored = c.get(f"/api/assets/{aid}?t=tk").json()["results_snapshot"]["kpis"]["npv"]
    assert stored > 0  # the stored base NPV is positive (residual recovers capital)
    r = c.get(f"/api/assets/{aid}/live?t=tk")
    assert r.status_code == 200
    npv_base = r.json()["comparison"]["npv_base"]
    # Before the fix this came out ~-1.7M (residual ignored). After threading the
    # residual it tracks the stored base within the irreducible levered-CFO vs
    # unlevered-FCF footing gap (the business EV is on unlevered FCF; live
    # recomputes on CFO+CFI). Tolerance: within 15% of the residual value.
    residual = 3_000_000.0
    assert abs(npv_base - stored) < 0.15 * residual
    # And unambiguously NOT the old spurious deep-negative.
    assert npv_base > -0.25 * residual


def test_live_revenue_actual_moves_npv(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    aid = _operational_asset(c)
    base = c.get(f"/api/assets/{aid}?t=tk").json()["results_snapshot"]
    base_rev_y0 = base["income_statement"]["rows"]["revenue"][0]
    # A real revenue well above base in commissioning year (model year 0).
    yr = datetime.now(timezone.utc).year - 2
    c.post(
        f"/api/assets/{aid}/actuals?t=tk",
        json={
            "actuals": [
                {"period_start": f"{yr}-01-01",
                 "line_path": "income_statement.rows.revenue",
                 "value": base_rev_y0 * 2 + 1_000_000.0},
            ]
        },
    )
    r = c.get(f"/api/assets/{aid}/live?t=tk")
    assert r.status_code == 200
    comp = r.json()["comparison"]
    assert comp["npv_live"] > comp["npv_base"]
    assert comp["delta"] > 0
