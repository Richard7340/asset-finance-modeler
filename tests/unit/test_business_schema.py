from asset_finance_modeler.assets.business.schema import BusinessModelConfig, RevenueLine


def test_business_config_defaults_and_lines():
    cfg = BusinessModelConfig(
        meta={"name": "Restaurante", "horizon": {"periods": 120, "frequency": "M"}},
        revenue=[{"name": "Comidas", "year1_amount": 500000, "growth_pct_yr": 0.03}],
        cogs={"pct_of_revenue": 0.35},
        opex={"fixed_lines": [{"name": "Personal", "year1_amount": 200000}], "variable_pct_of_revenue": 0.05},
        capex={"items": [{"name": "Reforma", "amount": 150000, "period": 0, "depreciation_years": 10}]},
        taxes={"corporate_income_tax_rate": 0.25},
        valuation={"discount_rate_annual": 0.10},
    )
    assert cfg.revenue[0].year1_amount == 500000
    assert cfg.cogs.pct_of_revenue == 0.35
    assert cfg.opex.variable_pct_of_revenue == 0.05
    cfg2 = cfg.model_copy(update={"revenue": cfg.revenue + [RevenueLine(name="Bebidas", year1_amount=120000)]})
    assert len(cfg2.revenue) == 2
