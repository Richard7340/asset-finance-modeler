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
    # GOLDEN history: 1,317,143 -> 956,749 (FIX 1/2) -> 849,643 (P1-4 timeline)
    # -> 918,282 (P1-5: the year-15 €846k BESS repowering is now depreciated,
    # adding a tax shield in yrs 15-30 that lifts BESS after-tax FCF/NPV).
    assert abs(base["kpis"]["npv_hybrid"] - 918_282) <= 1
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
