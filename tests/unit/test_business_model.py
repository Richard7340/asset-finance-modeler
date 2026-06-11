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
