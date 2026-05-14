import pytest

from asset_finance_modeler.core.statements import CashFlowBuilder


def test_cashflow_basic_no_wc_no_debt():
    cf = CashFlowBuilder(
        net_income=[100, 200],
        depreciation=[50, 50],
        revenue=[1000, 1000],
        cogs=[300, 300],
        dso_days=0, dpo_days=0,
        capex=[0, 0],
        funding_drawdowns=[0, 0],
        debt_drawdowns=[0, 0],
        debt_principal_repaid=[0, 0],
        origination_fees=[0, 0],
        initial_cash=500,
        period_days=30,
    ).build()
    assert cf["cfo"] == pytest.approx([150, 250])
    assert cf["cash"] == pytest.approx([650, 900])


def test_cashflow_funding_round_adds_to_cash():
    cf = CashFlowBuilder(
        net_income=[-100],
        depreciation=[0],
        revenue=[0], cogs=[0], dso_days=0, dpo_days=0,
        capex=[0],
        funding_drawdowns=[250_000],
        debt_drawdowns=[0],
        debt_principal_repaid=[0],
        origination_fees=[0],
        initial_cash=10_000,
        period_days=30,
    ).build()
    assert cf["cash"][0] == pytest.approx(259_900)


def test_cashflow_debt_drawdown_and_repayment():
    cf = CashFlowBuilder(
        net_income=[0, 0],
        depreciation=[0, 0],
        revenue=[0, 0], cogs=[0, 0], dso_days=0, dpo_days=0,
        capex=[0, 0],
        funding_drawdowns=[0, 0],
        debt_drawdowns=[100_000, 0],
        debt_principal_repaid=[0, 8_000],
        origination_fees=[1000, 0],
        initial_cash=0,
        period_days=30,
    ).build()
    assert cf["cff"][0] == pytest.approx(99_000)
    assert cf["cff"][1] == pytest.approx(-8_000)
