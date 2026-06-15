from datetime import date

import pytest

from asset_finance_modeler.assets.saas.model import ModelResults, SaasModel
from asset_finance_modeler.assets.saas.schema import (
    AcquisitionConfig,
    CapitalConfig,
    COGSConfig,
    DebtInstrument,
    ExternalDataConfig,
    HorizonConfig,
    ModelMeta,
    OpexConfig,
    PerActiveCustomerCosts,
    PerActiveUnitCosts,
    PricingConfig,
    RetentionConfig,
    RevenueConfig,
    RevenueSource,
    SaasModelConfig,
    TaxesConfig,
    TeamRole,
    ValuationConfig,
    WorkingCapital,
)


def _minimal_config(periods=24, with_debt=False) -> SaasModelConfig:
    debt = []
    if with_debt:
        debt = [DebtInstrument(
            name="enisa", principal=100_000, drawdown_period=0,
            interest_rate_annual=0.05, term_months=24, amortization="french",
        )]
    return SaasModelConfig(
        meta=ModelMeta(
            name="test",
            horizon=HorizonConfig(periods=periods, frequency="M"),
            start_date=date(2026, 1, 1),
            initial_cash=50_000,
        ),
        revenue=RevenueConfig(sources=[RevenueSource(
            name="subs",
            pricing=PricingConfig(per_unit_per_period=300, setup_one_time=1000),
            acquisition=AcquisitionConfig(
                new_units_per_period=5, avg_units_per_customer=2.5, cac_per_customer=800,
            ),
            retention=RetentionConfig(monthly_churn_rate=0.02),
        )]),
        cost_of_revenue=COGSConfig(
            per_active_unit=PerActiveUnitCosts(llm_tokens=[], infra_eur=5.0),
            per_active_customer=PerActiveCustomerCosts(support_eur=10),
        ),
        operating_expenses=OpexConfig(
            team=[TeamRole(role="founder", monthly_cost=4000, headcount=2)],
            infra_fixed_eur=500,
            marketing_eur=1000,
        ),
        capital=CapitalConfig(
            working_capital=WorkingCapital(days_sales_outstanding=30, days_payable_outstanding=30),
            debt=debt,
        ),
        taxes=TaxesConfig(),
        valuation=ValuationConfig(discount_rate_annual=0.20),
        external_data=ExternalDataConfig(),
    )


def test_saas_model_run_returns_results():
    cfg = _minimal_config(periods=12)
    results = SaasModel(cfg).run()
    assert isinstance(results, ModelResults)
    assert len(results.pnl["revenue"]) == 12
    assert len(results.cashflow["cash"]) == 12
    assert "ltv_cac" in results.unit_econ
    assert "enterprise_value" in results.valuation
    assert "revenue_y1" in results.summary


def test_saas_model_revenue_positive():
    cfg = _minimal_config(periods=12)
    results = SaasModel(cfg).run()
    assert results.pnl["revenue"][0] > 0
    assert results.pnl["revenue"][11] > results.pnl["revenue"][0]


def test_saas_model_with_debt_has_interest_expense():
    cfg = _minimal_config(periods=24, with_debt=True)
    results = SaasModel(cfg).run()
    assert results.pnl["interest_expense"][0] > 0
    assert results.debt_metrics["leverage"][0] >= 0


def test_saas_model_runway_metric_present():
    cfg = _minimal_config(periods=12)
    results = SaasModel(cfg).run()
    assert "runway_months" in results.summary


# ---------------------------------------------------------------------------
# P2-5: previously-dead SaaS parameters now take effect
# ---------------------------------------------------------------------------


def _cfg_with(**overrides):
    """Build a 36-period monthly config, then apply attribute overrides via
    small mutators keyed by name."""
    cfg = _minimal_config(periods=36)
    return cfg


def test_price_escalation_raises_year2_price():
    # price_escalation_annual lifts the per-unit price at each year boundary.
    base = _minimal_config(periods=36)
    esc = _minimal_config(periods=36)
    esc.revenue.sources[0].pricing.price_escalation_annual = 0.10
    r_base = SaasModel(base).run()
    r_esc = SaasModel(esc).run()
    # Year-1 (month 0) identical; year-2 (month 12) revenue is higher with esc
    # for the SAME active base (price stepped up 10%).
    assert r_esc.pnl["revenue"][0] == r_base.pnl["revenue"][0]
    assert r_esc.pnl["revenue"][12] > r_base.pnl["revenue"][12]


def test_expansion_revenue_increases_subscription():
    base = _minimal_config(periods=36)
    exp = _minimal_config(periods=36)
    exp.revenue.sources[0].retention.expansion_revenue_pct = 0.02
    r_base = SaasModel(base).run()
    r_exp = SaasModel(exp).run()
    # Expansion compounds on the existing base → later revenue strictly higher.
    assert r_exp.pnl["revenue"][24] > r_base.pnl["revenue"][24]


def test_gross_revenue_retention_reduces_subscription():
    base = _minimal_config(periods=36)
    grr = _minimal_config(periods=36)
    grr.revenue.sources[0].retention.gross_revenue_retention = 0.90
    r_base = SaasModel(base).run()
    r_grr = SaasModel(grr).run()
    # GRR < 1 erodes per-cohort revenue beyond logo churn → lower later revenue.
    assert r_grr.pnl["revenue"][24] < r_base.pnl["revenue"][24]


def test_payroll_taxes_increase_team_cost():
    base = _minimal_config(periods=12)
    base.taxes.payroll_taxes_pct = 0.0
    hi = _minimal_config(periods=12)
    hi.taxes.payroll_taxes_pct = 0.30
    r_base = SaasModel(base).run()
    r_hi = SaasModel(hi).run()
    # Higher payroll taxes raise opex → lower EBITDA.
    assert r_hi.pnl["opex"][0] > r_base.pnl["opex"][0]
    assert r_hi.pnl["ebitda"][0] < r_base.pnl["ebitda"][0]


def test_onboarding_one_time_cost_hits_cogs():
    base = _minimal_config(periods=12)
    base.cost_of_revenue.per_active_customer.onboarding_one_time_eur = 0.0
    onb = _minimal_config(periods=12)
    onb.cost_of_revenue.per_active_customer.onboarding_one_time_eur = 500.0
    r_base = SaasModel(base).run()
    r_onb = SaasModel(onb).run()
    # New customers each period incur a one-time onboarding cost → higher COGS.
    assert sum(r_onb.pnl["cogs"]) > sum(r_base.pnl["cogs"])


def test_exit_multiple_arr_is_honored_when_set():
    base = _minimal_config(periods=24)
    ex = _minimal_config(periods=24)
    ex.valuation.exit_multiple_arr = 8.0
    r_base = SaasModel(base).run()
    r_ex = SaasModel(ex).run()
    # With an ARR exit multiple, the terminal value lifts the enterprise value.
    assert r_ex.valuation["terminal_value"] > 0
    assert r_ex.valuation["enterprise_value"] > r_base.valuation["enterprise_value"]


def test_inflation_escalates_fixed_opex_buckets():
    # P2-5: inflation_annual escalates the scalar fixed-opex buckets at each
    # year boundary (infra/marketing/legal/other). 0 → flat (unchanged).
    base = _minimal_config(periods=36)
    base.meta.inflation_annual = 0.0
    infl = _minimal_config(periods=36)
    infl.meta.inflation_annual = 0.10
    r_base = SaasModel(base).run()
    r_infl = SaasModel(infl).run()
    # Year-1 opex identical; year-3 opex higher with inflation (fixed buckets up).
    assert r_infl.pnl["opex"][0] == pytest.approx(r_base.pnl["opex"][0])
    assert r_infl.pnl["opex"][24] > r_base.pnl["opex"][24]


def test_inflation_zero_unchanged():
    a = _minimal_config(periods=24)
    a.meta.inflation_annual = 0.0
    b = _minimal_config(periods=24)
    b.meta.inflation_annual = 0.0
    assert SaasModel(a).run().pnl["opex"] == SaasModel(b).run().pnl["opex"]
