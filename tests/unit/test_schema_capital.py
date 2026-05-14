import pytest
from pydantic import ValidationError

from asset_finance_modeler.assets.saas.schema import (
    CapExItem,
    CapitalConfig,
    DebtInstrument,
    FundingRound,
    WorkingCapital,
)


def test_working_capital_defaults():
    wc = WorkingCapital()
    assert wc.days_sales_outstanding == 30
    assert wc.days_payable_outstanding == 30
    assert wc.days_inventory == 0


def test_funding_round():
    r = FundingRound(period=6, amount=250_000, type="pre_seed", dilution=0.15)
    assert r.valuation_pre is None


def test_debt_instrument_french():
    d = DebtInstrument(
        name="enisa", principal=200_000, drawdown_period=0,
        interest_rate_annual=0.045, term_months=84, amortization="french",
    )
    assert d.grace_period_months == 0
    assert d.origination_fee_pct == 0


def test_debt_instrument_custom_requires_schedule():
    with pytest.raises(ValidationError):
        DebtInstrument(
            name="bad", principal=100_000, drawdown_period=0,
            interest_rate_annual=0.04, term_months=12, amortization="custom",
        )


def test_capex_item():
    c = CapExItem(name="laptop_fleet", amount=12_000, period=3, depreciation_years=3)
    assert c.depreciation_years == 3


def test_capital_minimal():
    cap = CapitalConfig(working_capital=WorkingCapital())
    assert cap.debt == []
    assert cap.funding_rounds == []
    assert cap.capex_schedule == []
