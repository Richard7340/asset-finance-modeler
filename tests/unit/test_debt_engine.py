import pytest

from asset_finance_modeler.core.financing import DebtEngine
from asset_finance_modeler.assets.saas.schema import DebtInstrument


def test_single_french_loan():
    d = DebtInstrument(
        name="enisa", principal=100_000, drawdown_period=0,
        interest_rate_annual=0.06, term_months=12, amortization="french",
    )
    eng = DebtEngine([d], periods=24, periods_per_year=12)
    out = eng.compute()
    assert out["interest_expense"][0] > 0
    assert out["interest_expense"][12] == pytest.approx(0)
    assert out["principal_repaid"][0] > 0
    assert out["balance_outstanding"][11] == pytest.approx(0, abs=0.01)
    assert out["drawdowns"][0] == pytest.approx(100_000)


def test_origination_fee_modeled_as_period_0_cost():
    d = DebtInstrument(
        name="enisa", principal=100_000, drawdown_period=2,
        interest_rate_annual=0.05, term_months=12, amortization="bullet",
        origination_fee_pct=0.02,
    )
    eng = DebtEngine([d], periods=24, periods_per_year=12)
    out = eng.compute()
    assert out["origination_fees"][2] == pytest.approx(2000)
    assert out["drawdowns"][2] == pytest.approx(100_000)


def test_drawdown_timing_shifts_schedule():
    d = DebtInstrument(
        name="late", principal=50_000, drawdown_period=6,
        interest_rate_annual=0.06, term_months=12, amortization="french",
    )
    eng = DebtEngine([d], periods=24, periods_per_year=12)
    out = eng.compute()
    assert all(out["interest_expense"][t] == 0 for t in range(6))
    assert out["interest_expense"][6] > 0
