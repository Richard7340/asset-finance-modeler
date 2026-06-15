"""SVJ hybrid now exposes the FULL FV + BESS + debt/valuation input trees,
with override-by-path on any leaf, while keeping the 6 legacy drivers working
and the default output identical."""

from __future__ import annotations


def test_svj_hybrid_exposes_full_tree(monkeypatch):
    monkeypatch.setenv("SIM_TOKEN", "tk")
    monkeypatch.setenv("SIM_ONLY", "1")
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from asset_finance_modeler.mcp_server.http_server import app  # noqa: PLC0415

    c = TestClient(app)
    leaves = c.get("/api/models/svj_hybrid/schema?t=tk").json()["inputs"]
    paths = {leaf["path"] for leaf in leaves}
    assert len(leaves) > 100
    assert any(p.startswith("fv.") for p in paths)
    assert any(p.startswith("bess.") for p in paths)
    assert "subordinated.interest_rate" in paths


def test_svj_hybrid_default_unchanged_and_deep_override(monkeypatch):
    from asset_finance_modeler.deals.svj import run_svj  # noqa: PLC0415

    base = run_svj({})
    # FV merchant capture is now curve-driven (solar_capture_es, Agere): year-1
    # capture is ~36 EUR/MWh straight from the curve instead of base 36 x 0.85
    # capture_ratio, lifting FV (and thus hybrid) revenue. NPV moved from the
    # old base+escalation figure (~1,031,876) to the curve-driven ~1,317,143.
    assert abs(base["kpis"]["npv_hybrid"] - 1_317_143) < 50_000
    assert abs(base["kpis"]["moic_sub"] - 1.37) < 0.05
    # legacy key still works
    leg = run_svj({"fv_ppa_price": 60})
    assert leg["kpis"]["npv_hybrid"] != base["kpis"]["npv_hybrid"]
    # deep FV path override changes the result
    deep = run_svj({"fv.production.capacity_mwp": 6.0})
    assert deep["kpis"]["npv_fv"] != base["kpis"]["npv_fv"]
    # subordinated rate override
    sub = run_svj({"subordinated.interest_rate": 0.10})
    assert sub["kpis"]["moic_sub"] != base["kpis"]["moic_sub"]
