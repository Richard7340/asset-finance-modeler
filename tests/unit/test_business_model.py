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


def test_business_tax_loss_carryforward():
    """P0-5: a year-1 loss offsets year-2 taxable income.

    Year 1 EBT = -410k, year 2 EBT = +400k. With carryforward the year-2 tax
    is 0 (400k fully offset by the 410k loss), not 100k. The flag was a no-op.
    """
    cfg = BusinessModelConfig(
        meta={"name": "CF", "horizon": {"periods": 2, "frequency": "Y"}},
        revenue=[{"name": "Ventas", "year1_amount": 90_000, "growth_pct_yr": 0.0}],
        cogs={"pct_of_revenue": 0.0},
        # Year 1: revenue 90k - opex 500k = -410k. Year 2 revenue same; we add a
        # one-off boost via a second revenue line that only exists year 2? Simpler:
        # use a single line but engineer year-2 EBT via growth. Instead, make
        # opex a fixed 500k year1 and rev grow so year-2 EBT=+400k.
        opex={"fixed_lines": [{"name": "Burn", "year1_amount": 500_000}], "escalation_pct_yr": 0.0},
        capex={"items": []},
        taxes={"corporate_income_tax_rate": 0.25, "tax_loss_carryforward": True},
        valuation={"discount_rate_annual": 0.10, "terminal_method": "none"},
    )
    # Engineer revenues directly: year1=90k (EBT -410k), year2=900k (EBT +400k).
    cfg.revenue[0].year1_amount = 90_000
    cfg.revenue[0].growth_pct_yr = 9.0  # year2 = 90k*(1+9)=900k → EBT 400k
    out = BusinessModel(cfg).run()
    # frequency Y, ppy=1 → per-period == per-year
    assert out.pnl["ebt"][0] == pytest.approx(-410_000)
    assert out.pnl["ebt"][1] == pytest.approx(400_000)
    assert out.pnl["tax"][1] == pytest.approx(0.0)  # fully offset, not 100k

    # Disabling the flag → year-2 tax is the full 100k.
    cfg_off = cfg.model_copy(deep=True)
    cfg_off.taxes.tax_loss_carryforward = False
    out_off = BusinessModel(cfg_off).run()
    assert out_off.pnl["tax"][1] == pytest.approx(100_000)


def test_business_cfo_stays_levered():
    """P0-4: the cash-flow statement CFO remains levered (real cash, interest paid).

    Only the valuation FCF is unlevered; the statement keeps net income.
    """
    levered = BusinessModel(_cfg_annual(financed=True)).run()
    unlevered = BusinessModel(_cfg_annual(financed=False)).run()
    # Interest reduces net income → levered CFO total < unlevered CFO total.
    assert sum(levered.cashflow["cfo"]) < sum(unlevered.cashflow["cfo"])


def _cfg_wc(receivable_days=0.0, payable_days=0.0, inventory_days=0.0):
    return BusinessModelConfig(
        meta={"name": "WC", "horizon": {"periods": 3, "frequency": "Y"}},
        revenue=[{"name": "Ventas", "year1_amount": 1_000_000, "growth_pct_yr": 0.10}],
        cogs={"pct_of_revenue": 0.40},
        opex={"fixed_lines": [{"name": "Personal", "year1_amount": 200_000}], "escalation_pct_yr": 0.0},
        capex={"items": []},
        working_capital={
            "receivable_days": receivable_days,
            "payable_days": payable_days,
            "inventory_days": inventory_days,
        },
        taxes={"corporate_income_tax_rate": 0.25},
        valuation={"discount_rate_annual": 0.10, "terminal_method": "none"},
    )


def test_business_working_capital_changes_cfo():
    """P0-6: raising receivable_days 0→90 reduces CFO (cash tied up in AR).

    With zero WC days the CFO was net_income + dep; the days were a no-op.
    """
    base = BusinessModel(_cfg_wc(receivable_days=0)).run()
    with_ar = BusinessModel(_cfg_wc(receivable_days=90)).run()
    assert sum(with_ar.cashflow["cfo"]) != pytest.approx(sum(base.cashflow["cfo"]))
    # Growing AR consumes cash → total CFO lower with 90 days of receivables.
    assert sum(with_ar.cashflow["cfo"]) < sum(base.cashflow["cfo"])


def test_business_payable_days_release_cash():
    """P0-6: raising payable_days frees cash (supplier financing) → higher CFO."""
    base = BusinessModel(_cfg_wc(payable_days=0)).run()
    with_ap = BusinessModel(_cfg_wc(payable_days=60)).run()
    assert sum(with_ap.cashflow["cfo"]) > sum(base.cashflow["cfo"])


def test_business_inventory_days_consume_cash():
    """P0-6: raising inventory_days ties up cash → lower CFO."""
    base = BusinessModel(_cfg_wc(inventory_days=0)).run()
    with_inv = BusinessModel(_cfg_wc(inventory_days=45)).run()
    assert sum(with_inv.cashflow["cfo"]) < sum(base.cashflow["cfo"])


def test_residual_value_raises_ev():
    """P0-7: a residual_value (asset sale) adds a discounted terminal inflow."""
    base = BusinessModel(_cfg_annual(financed=False)).run()
    cfg = _cfg_annual(financed=False)
    cfg.valuation.residual_value = 1_000_000
    with_res = BusinessModel(cfg).run()
    wacc = cfg.valuation.discount_rate_annual
    expected_delta = 1_000_000 / (1.0 + wacc) ** 3  # 3-year horizon
    assert with_res.valuation["enterprise_value"] - base.valuation["enterprise_value"] == pytest.approx(
        expected_delta, rel=1e-9
    )


def test_real_estate_preset_not_artificially_negative():
    """P0-7: the real-estate preset's VAN is no longer structurally negative.

    A €3M property held 10 years recovers capital via a residual sale value at
    horizon end. Without it, terminal=none gives a deeply negative EV.
    """
    from asset_finance_modeler.assets.business.loader import load_business_preset

    cfg = load_business_preset("real_estate_rental")
    out = BusinessModel(cfg).run()
    assert out.valuation["enterprise_value"] > 0
    # The residual must be part of the explicit FCF, not a Gordon perpetuity.
    assert cfg.valuation.terminal_method == "none"
    assert cfg.valuation.residual_value is not None and cfg.valuation.residual_value > 0
