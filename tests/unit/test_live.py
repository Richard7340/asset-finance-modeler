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


# ---------------------------------------------------------------------------
# L1: cost / margin overlay must preserve NI = EBT - tax and shift CFO by the
# AFTER-TAX (net_income) delta, not the raw pre-tax delta. L2: interest_expense
# is a cost into EBT (higher interest -> lower EBT/NI/CFO).
# Base year 0: revenue 1000, ebitda 400, ebit 300, ebt 250 (interest 50),
# tax 62.5 (eff rate 25%), net_income 187.5, cfo 287.5.
# ---------------------------------------------------------------------------

_TRACKABLE_LINES = ["revenue", "ebitda", "ebit", "ebt", "tax", "net_income",
                    "interest_expense"]


def _assert_ni_consistent(rows: dict, year: int) -> None:
    """NI = EBT - tax on the spliced live series for ``year``."""
    ebt = rows["ebt"][year]
    tax = rows["tax"][year]
    ni = rows["net_income"][year]
    assert abs(ni - (ebt - tax)) < 1e-6, (
        f"NI {ni} != EBT {ebt} - tax {tax} = {ebt - tax}"
    )


def test_cost_line_overlay_preserves_ni_and_after_tax_cfo():
    """L1: overriding EBITDA on a profitable base preserves NI = EBT - tax on
    the spliced series, and CFO moves by the AFTER-TAX delta; tax is recomputed
    at the base year's effective rate (not shifted by the raw pre-tax delta)."""
    base = _base_output()
    # ebitda 400 -> 300 (pre-tax delta -100). eff rate at base = 62.5/250 = 0.25.
    actuals = {"income_statement.rows.ebitda": {0: 300.0}}
    out = compute_live(base, actuals_by_line_by_year=actuals, elapsed_years=1,
                       discount_rate=0.08)
    rows = out["live"]["series"]["income_statement"]["rows"]
    # ebitda/ebit/ebt all shift by -100.
    assert rows["ebitda"][0] == 300.0
    assert rows["ebit"][0] == 200.0
    assert rows["ebt"][0] == 150.0
    # tax recomputed at 25% on new ebt 150 -> 37.5 (NOT 62.5 - 100 = -37.5).
    assert abs(rows["tax"][0] - 37.5) < 1e-6
    # NI = EBT - tax = 150 - 37.5 = 112.5.
    assert abs(rows["net_income"][0] - 112.5) < 1e-6
    _assert_ni_consistent(rows, 0)
    # CFO shifts by the AFTER-TAX (NI) delta: 112.5 - 187.5 = -75 (not -100).
    base_cfo = base["cash_flow"]["cfo"][0]
    assert abs(out["live"]["series"]["cash_flow"]["cfo"][0] - (base_cfo - 75.0)) < 1e-6


def test_higher_interest_lowers_ebt_ni_cfo():
    """L2: a higher interest_expense actual is a cost into EBT -> EBT/NI/CFO
    all fall (current code wrongly raises them)."""
    base = _base_output()
    # interest 50 -> 90 (delta +40 cost). eff rate 25%.
    actuals = {"income_statement.rows.interest_expense": {0: 90.0}}
    out = compute_live(base, actuals_by_line_by_year=actuals, elapsed_years=1,
                       discount_rate=0.08)
    rows = out["live"]["series"]["income_statement"]["rows"]
    assert rows["interest_expense"][0] == 90.0
    # EBT down by 40 -> 210; tax 25% -> 52.5; NI = 157.5.
    assert abs(rows["ebt"][0] - 210.0) < 1e-6
    assert abs(rows["tax"][0] - 52.5) < 1e-6
    assert abs(rows["net_income"][0] - 157.5) < 1e-6
    _assert_ni_consistent(rows, 0)
    # NI/CFO below base.
    assert rows["net_income"][0] < base["income_statement"]["rows"]["net_income"][0]
    assert out["live"]["series"]["cash_flow"]["cfo"][0] < base["cash_flow"]["cfo"][0]
    # Less cash early -> live NPV below base.
    assert out["live"]["kpis"]["npv"] < out["base"]["kpis"]["npv"]


def test_every_trackable_line_keeps_ni_eq_ebt_minus_tax():
    """Overriding EVERY trackable P&L line (one at a time) keeps NI = EBT - tax
    on the spliced live series (not just revenue)."""
    base = _base_output()
    base_vals = {k: base["income_statement"]["rows"][k][0] for k in _TRACKABLE_LINES}
    for key in _TRACKABLE_LINES:
        # Perturb the line by a non-trivial amount.
        new_val = base_vals[key] * 1.3 if base_vals[key] else 100.0
        actuals = {f"income_statement.rows.{key}": {0: new_val}}
        out = compute_live(base, actuals_by_line_by_year=actuals,
                           elapsed_years=1, discount_rate=0.08)
        rows = out["live"]["series"]["income_statement"]["rows"]
        _assert_ni_consistent(rows, 0)


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


# ---------------------------------------------------------------------------
# Terminal / residual value honoring (fix(live): honrar valor terminal/residual
# en la recomputacion base-vs-live). For an asset whose BASE valuation includes
# a residual/exit inflow (e.g. real estate sale at horizon end), the base NPV
# recomputed by ``compute_live`` must carry that SAME residual — otherwise the
# base panel shows a spuriously negative NPV that contradicts the stored one.
# ---------------------------------------------------------------------------


def _residual_base_output() -> dict:
    """A 3-year base whose CFO+CFI footing is negative without a terminal: a
    big upfront capex (year 0) recovered only by an exit/residual at horizon
    end. Mirrors the real-estate shape (acquire, rent, sell)."""
    return {
        "income_statement": {
            "years": [1, 2, 3],
            "rows": {
                "revenue": [240.0, 245.0, 250.0],
                "ebitda": [210.0, 214.0, 218.0],
                "ebit": [110.0, 114.0, 118.0],
                "interest_expense": [70.0, 60.0, 50.0],
                "ebt": [40.0, 54.0, 68.0],
                "tax": [10.0, 13.5, 17.0],
                "net_income": [30.0, 40.5, 51.0],
            },
        },
        "cash_flow": {
            "years": [1, 2, 3],
            "cfo": [130.0, 140.5, 151.0],
            "cfi": [-3000.0, 0.0, 0.0],
            "cff": [1800.0, -60.0, -65.0],
        },
    }


def test_residual_value_lifts_base_npv_out_of_spurious_negative():
    """Without the residual the recomputed base NPV is deeply negative (the
    capex is never recovered); threading the residual makes it materially
    higher (no longer a spurious structural negative)."""
    base = _residual_base_output()
    out_no_res = compute_live(
        base, actuals_by_line_by_year={}, elapsed_years=0, discount_rate=0.06
    )
    out_res = compute_live(
        base, actuals_by_line_by_year={}, elapsed_years=0, discount_rate=0.06,
        residual_value=3000.0,
    )
    npv_no_res = out_no_res["deviation_summary"]["npv_base"]
    npv_res = out_res["deviation_summary"]["npv_base"]
    # Residual is recovered at horizon end -> the recomputed base must rise by
    # roughly the PV of 3000 at 6% over 3 years (~2519), and the spurious
    # ~-2.5k+ deficit must be largely closed.
    assert npv_no_res < -2000.0
    assert npv_res > npv_no_res
    assert abs((npv_res - npv_no_res) - 3000.0 / (1.06 ** 3)) < 5.0


def test_residual_applied_to_both_base_and_live_no_actuals():
    """With no actuals, live == base even when a residual is threaded (the
    residual is a future exit value unaffected by past operational deviations)."""
    base = _residual_base_output()
    out = compute_live(
        base, actuals_by_line_by_year={}, elapsed_years=1, discount_rate=0.06,
        residual_value=3000.0,
    )
    assert out["live"]["kpis"]["npv"] == out["base"]["kpis"]["npv"]
    assert out["deviation_summary"]["npv_delta"] == 0.0


def test_residual_above_base_actual_still_raises_live():
    """An above-base actual in a past year must still raise the live NPV even
    with a residual threaded (residual unchanged, actuals move the delta)."""
    base = _residual_base_output()
    actuals = {"income_statement.rows.revenue": {0: 480.0}}  # double base y0
    out = compute_live(
        base, actuals_by_line_by_year=actuals, elapsed_years=1,
        discount_rate=0.06, residual_value=3000.0,
    )
    assert out["live"]["kpis"]["npv"] > out["base"]["kpis"]["npv"]


def test_no_residual_default_unchanged():
    """residual_value defaults to 0 -> existing no-terminal behaviour is exact
    (regression guard for infra/SVJ whose base must stay as-is)."""
    base = _base_output()
    out_default = compute_live(
        base, actuals_by_line_by_year={}, elapsed_years=1, discount_rate=0.08
    )
    out_zero = compute_live(
        base, actuals_by_line_by_year={}, elapsed_years=1, discount_rate=0.08,
        residual_value=0.0,
    )
    assert out_default["deviation_summary"]["npv_base"] == \
        out_zero["deviation_summary"]["npv_base"]


# ---------------------------------------------------------------------------
# fix(live): anchor the base-vs-live panel to the asset's REAL stored base NPV
# (the engine NPV, on whatever footing the engine values — unlevered NOPAT FCF
# for business/real-estate, consolidated unlevered for SVJ), and report the live
# as stored + the actuals-driven delta (which is computed consistently on the
# SAME CFO+CFI footing for both recomputed base and live, so the delta is valid).
# ---------------------------------------------------------------------------


def test_stored_base_npv_anchors_base_exactly():
    """When a stored base NPV is supplied, ``npv_base`` reported == stored
    EXACTLY, regardless of the CFO+CFI recompute footing."""
    base = _base_output()
    out = compute_live(
        base, actuals_by_line_by_year={}, elapsed_years=1, discount_rate=0.08,
        stored_base_npv=999_000.0,
    )
    assert out["base"]["kpis"]["npv"] == 999_000
    assert out["deviation_summary"]["npv_base"] == 999_000


def test_stored_base_npv_no_actuals_live_equals_stored():
    """No actuals -> live == base == stored exactly (delta 0)."""
    base = _base_output()
    out = compute_live(
        base, actuals_by_line_by_year={}, elapsed_years=1, discount_rate=0.08,
        stored_base_npv=999_000.0,
    )
    assert out["live"]["kpis"]["npv"] == 999_000
    assert out["deviation_summary"]["npv_delta"] == 0.0


def test_stored_base_npv_live_is_stored_plus_delta():
    """live = stored + (recomputed_live - recomputed_base). The actuals-driven
    delta is added to the TRUE stored base."""
    base = _base_output()
    actuals = {"income_statement.rows.revenue": {0: 1500.0}}  # above base y0
    # Recompute the raw (unanchored) delta to compare.
    raw = compute_live(base, actuals_by_line_by_year=actuals, elapsed_years=1,
                       discount_rate=0.08)
    raw_delta = raw["live"]["kpis"]["npv"] - raw["base"]["kpis"]["npv"]
    out = compute_live(
        base, actuals_by_line_by_year=actuals, elapsed_years=1,
        discount_rate=0.08, stored_base_npv=999_000.0,
    )
    assert out["base"]["kpis"]["npv"] == 999_000
    assert out["live"]["kpis"]["npv"] == 999_000 + raw_delta
    # Above-base actual -> live still > base.
    assert out["live"]["kpis"]["npv"] > out["base"]["kpis"]["npv"]
    assert out["deviation_summary"]["npv_delta"] == raw_delta


def test_stored_base_npv_none_falls_back_to_recompute():
    """No stored base provided -> recomputed base (current behaviour) is kept."""
    base = _base_output()
    out_none = compute_live(
        base, actuals_by_line_by_year={}, elapsed_years=1, discount_rate=0.08,
        stored_base_npv=None,
    )
    out_legacy = compute_live(
        base, actuals_by_line_by_year={}, elapsed_years=1, discount_rate=0.08,
    )
    assert out_none["base"]["kpis"]["npv"] == out_legacy["base"]["kpis"]["npv"]
