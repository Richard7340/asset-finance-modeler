import pytest

from asset_finance_modeler.assets.business.model import BusinessModel
from asset_finance_modeler.assets.business.schema import BusinessModelConfig


def _cfg(rev=500000):
    return BusinessModelConfig(
        meta={"name": "Neg", "horizon": {"periods": 120, "frequency": "M"}},
        revenue=[{"name": "Ventas", "year1_amount": rev, "growth_pct_yr": 0.03}],
        cogs={"pct_of_revenue": 0.35},
        opex={
            "fixed_lines": [{"name": "Personal", "year1_amount": 200000}],
            "variable_pct_of_revenue": 0.05,
        },
        capex={
            "items": [
                {
                    "name": "Capex",
                    "amount": 150000,
                    "period": 0,
                    "depreciation_years": 10,
                }
            ]
        },
        taxes={"corporate_income_tax_rate": 0.25},
        valuation={"discount_rate_annual": 0.10},
    )


def test_business_run_statements_and_kpis():
    out = BusinessModel(_cfg()).run()
    for k in ("revenue", "ebitda", "ebit", "ebt", "tax", "net_income"):
        assert k in out.pnl
    assert "cfo" in out.cashflow and "cfi" in out.cashflow
    assert out.project_kpis is not None
    # annualized revenue year1 ~ 500000 (sum of 12 monthly periods)
    assert abs(sum(out.pnl["revenue"][:12]) - 500000) < 1.0
    more = BusinessModel(_cfg(rev=800000)).run()
    assert sum(more.pnl["ebitda"][:12]) > sum(out.pnl["ebitda"][:12])


def _cfg_annual(financed: bool, rev=1_000_000):
    """3-year annual business; optionally with a subordinated debt ticket."""
    data = {
        "meta": {"name": "Lev", "horizon": {"periods": 3, "frequency": "Y"}},
        "revenue": [{"name": "Ventas", "year1_amount": rev}],
        "cogs": {"pct_of_revenue": 0.30},
        "opex": {
            "fixed_lines": [{"name": "Personal", "year1_amount": 300_000}],
            "escalation_pct_yr": 0.0,
        },
        "capex": {
            "items": [{"name": "Capex", "amount": 500_000, "period": 0, "depreciation_years": 5}]
        },
        "taxes": {"corporate_income_tax_rate": 0.25, "tax_loss_carryforward": False},
        "valuation": {"discount_rate_annual": 0.10, "terminal_method": "none"},
    }
    if financed:
        data["financing"] = {
            "subordinated": {
                "principal": 400_000,
                "interest_rate": 0.08,
                "tenor_years": 3,
                "amortization": "linear",
            }
        }
    return BusinessModelConfig(**data)


def test_business_valuation_fcf_is_unlevered():
    """P0-4: the valuation FCF/EV must be unlevered — independent of debt.

    The old model used FCF = net_income + dep + capex; net_income carried the
    interest deduction but the debt principal/drawdown was dropped, so adding
    debt silently changed the project EV. Unlevered FCF = EBIT*(1-t)+D&A-capex
    is financing-independent, so the EV must match the all-equity case.
    """
    ev_unlevered = BusinessModel(_cfg_annual(financed=False)).run().valuation["enterprise_value"]
    ev_levered = BusinessModel(_cfg_annual(financed=True)).run().valuation["enterprise_value"]
    assert ev_levered == pytest.approx(ev_unlevered, rel=1e-9)


def test_business_ev_matches_discounted_unlevered_fcf():
    """P0-4: EV = PV of unlevered FCF (EBIT*(1-t)+D&A-capex), terminal=none."""
    cfg = _cfg_annual(financed=True)
    out = BusinessModel(cfg).run()
    pnl = out.pnl
    cf = out.cashflow
    tax_rate = cfg.taxes.corporate_income_tax_rate
    wacc = cfg.valuation.discount_rate_annual

    expected_ev = 0.0
    for y in range(3):
        ebit = pnl["ebit"][y]
        dep = pnl["depreciation"][y]
        nopat = ebit * (1.0 - tax_rate) if ebit > 0 else ebit
        capex = -cf["cfi"][y]  # cfi is negative spend
        fcf = nopat + dep - capex
        expected_ev += fcf / (1.0 + wacc) ** (y + 1)
    assert out.valuation["enterprise_value"] == pytest.approx(expected_ev, rel=1e-9)


def test_business_cfo_stays_levered():
    """P0-4: the cash-flow statement CFO remains levered (real cash, interest paid).

    Only the valuation FCF is unlevered; the statement keeps net income.
    """
    levered = BusinessModel(_cfg_annual(financed=True)).run()
    unlevered = BusinessModel(_cfg_annual(financed=False)).run()
    # Interest reduces net income → levered CFO total < unlevered CFO total.
    assert sum(levered.cashflow["cfo"]) < sum(unlevered.cashflow["cfo"])
