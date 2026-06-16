"""F3-1: compute_live — base-vs-live reprojection by overlay-of-actuals.

The base output is the frozen ``results_snapshot`` shape (annual
income_statement + cash_flow). ``compute_live`` copies the base annual series,
replaces past-year (year < elapsed_years) tracked lines with the aggregated
actual, minimally re-derives the dependent P&L for those years using the base
year's cost/tax ratios, recomputes the spliced FCF and LIVE KPIs (NPV with the
base convention, IRR, DSCR), and leaves future years untouched.
"""
from __future__ import annotations

import copy

from asset_finance_modeler.core.live import compute_live


def _base_output() -> dict:
    """A small synthetic 3-year base output (generic snapshot shape)."""
    return {
        "income_statement": {
            "years": [1, 2, 3],
            "rows": {
                "revenue": [1000.0, 1100.0, 1200.0],
                "ebitda": [400.0, 440.0, 480.0],
                "ebit": [300.0, 340.0, 380.0],
                "interest_expense": [50.0, 40.0, 30.0],
                "ebt": [250.0, 300.0, 350.0],
                "tax": [62.5, 75.0, 87.5],
                "net_income": [187.5, 225.0, 262.5],
            },
        },
        "cash_flow": {
            "years": [1, 2, 3],
            "cfo": [287.5, 325.0, 362.5],
            "cfi": [-2000.0, 0.0, 0.0],
            "cff": [1800.0, -100.0, -100.0],
        },
    }


def test_no_actuals_live_equals_base():
    base = _base_output()
    out = compute_live(base, actuals_by_line_by_year={}, elapsed_years=1,
                       discount_rate=0.08)
    # Series identical.
    assert out["live"]["series"]["income_statement"]["rows"]["revenue"] == \
        out["base"]["series"]["income_statement"]["rows"]["revenue"]
    # KPIs identical.
    assert out["live"]["kpis"]["npv"] == out["base"]["kpis"]["npv"]
    assert out["live"]["kpis"]["irr_project"] == out["base"]["kpis"]["irr_project"]
    assert out["live"]["kpis"]["dscr_min"] == out["base"]["kpis"]["dscr_min"]
    assert out["deviation_summary"]["npv_delta"] == 0.0


def test_revenue_actual_above_base_raises_npv():
    base = _base_output()
    # Year 0 revenue real = 1500 (vs 1000 base): more cash this year -> NPV up.
    actuals = {"income_statement.rows.revenue": {0: 1500.0}}
    out = compute_live(base, actuals_by_line_by_year=actuals, elapsed_years=1,
                       discount_rate=0.08)
    assert out["live"]["kpis"]["npv"] > out["base"]["kpis"]["npv"]
    # Year 0 revenue overridden with the real value.
    live_rev = out["live"]["series"]["income_statement"]["rows"]["revenue"]
    assert live_rev[0] == 1500.0
    # Dependent lines re-derived for year 0 (ebitda margin preserved at 0.40).
    live_ebitda = out["live"]["series"]["income_statement"]["rows"]["ebitda"]
    assert abs(live_ebitda[0] - 600.0) < 1e-6  # 1500 * (400/1000)


def test_future_years_intact():
    base = _base_output()
    actuals = {"income_statement.rows.revenue": {0: 1500.0}}
    out = compute_live(base, actuals_by_line_by_year=actuals, elapsed_years=1,
                       discount_rate=0.08)
    live_rev = out["live"]["series"]["income_statement"]["rows"]["revenue"]
    base_rev = _base_output()["income_statement"]["rows"]["revenue"]
    # Years 1,2 (future, index >= elapsed_years) untouched.
    assert live_rev[1] == base_rev[1]
    assert live_rev[2] == base_rev[2]


def test_cost_line_actual_above_base_lowers_ebitda_and_cfo():
    """A cost overrun via a lower EBITDA actual must drop net_income and CFO
    for that year (cost up == ebitda down)."""
    base = _base_output()
    # Directly track ebitda: real ebitda 300 (vs 400 base) -> margin worse.
    actuals = {"income_statement.rows.ebitda": {0: 300.0}}
    out = compute_live(base, actuals_by_line_by_year=actuals, elapsed_years=1,
                       discount_rate=0.08)
    live = out["live"]["series"]
    assert live["income_statement"]["rows"]["ebitda"][0] == 300.0
    # net_income down vs base year 0.
    assert live["income_statement"]["rows"]["net_income"][0] < \
        base["income_statement"]["rows"]["net_income"][0]
    # CFO down vs base year 0.
    assert live["cash_flow"]["cfo"][0] < base["cash_flow"]["cfo"][0]
    # NPV down vs base (less cash early).
    assert out["live"]["kpis"]["npv"] < out["base"]["kpis"]["npv"]


def test_base_not_mutated():
    base = _base_output()
    snapshot = copy.deepcopy(base)
    compute_live(base, actuals_by_line_by_year={
        "income_statement.rows.revenue": {0: 9999.0}}, elapsed_years=1,
        discount_rate=0.08)
    assert base == snapshot
