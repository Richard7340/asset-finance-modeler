from datetime import date

from asset_finance_modeler.assets.saas.schema import (
    AcquisitionConfig,
    CapitalConfig,
    COGSConfig,
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
    SensitivityGrid,
    TaxesConfig,
    TeamRole,
    ValuationConfig,
    WorkingCapital,
)


def test_taxes_defaults():
    t = TaxesConfig()
    assert t.corporate_income_tax_rate == 0.25
    assert t.tax_loss_carryforward is True


def test_valuation_with_sensitivity():
    v = ValuationConfig(
        discount_rate_annual=0.20,
        sensitivity_grid=SensitivityGrid(wacc=[0.15, 0.20], growth=[0.02, 0.03]),
    )
    # P3: default terminal_method is now "none" (no perpetuity on finite-life
    # assets); Gordon/exit_multiple remain available as explicit opt-ins.
    assert v.terminal_method == "none"


def test_external_data_empty():
    e = ExternalDataConfig()
    assert e.benchmarks == {}


def test_saas_model_config_minimal():
    cfg = SaasModelConfig(
        meta=ModelMeta(
            name="gestnova",
            horizon=HorizonConfig(periods=12, frequency="M"),
            start_date=date(2026, 5, 1),
            initial_cash=100_000,
        ),
        revenue=RevenueConfig(sources=[
            RevenueSource(
                name="subs",
                pricing=PricingConfig(per_unit_per_period=300),
                acquisition=AcquisitionConfig(
                    new_units_per_period=5, avg_units_per_customer=2.5, cac_per_customer=800,
                ),
                retention=RetentionConfig(monthly_churn_rate=0.02),
            ),
        ]),
        cost_of_revenue=COGSConfig(
            per_active_unit=PerActiveUnitCosts(llm_tokens=[], infra_eur=2),
            per_active_customer=PerActiveCustomerCosts(),
        ),
        operating_expenses=OpexConfig(
            team=[TeamRole(role="founder", monthly_cost=4000, headcount=3)],
        ),
        capital=CapitalConfig(working_capital=WorkingCapital()),
        taxes=TaxesConfig(),
        valuation=ValuationConfig(discount_rate_annual=0.20),
        external_data=ExternalDataConfig(),
    )
    assert cfg.meta.name == "gestnova"
    assert cfg.taxes.corporate_income_tax_rate == 0.25
