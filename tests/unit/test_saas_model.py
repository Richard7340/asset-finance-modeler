from datetime import date

import pytest

from asset_finance_modeler.assets.saas.model import ModelResults, SaasModel
from asset_finance_modeler.assets.saas.schema import (
    AcquisitionConfig,
    COGSConfig,
    CapitalConfig,
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
        capital=CapitalConfig(working_capital=WorkingCapital(days_sales_outstanding=30, days_payable_outstanding=30), debt=debt),
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
