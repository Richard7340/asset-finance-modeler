import pytest

from asset_finance_modeler.core.drivers import AmortizationSchedule


def test_bullet_amortization():
    s = AmortizationSchedule(
        principal=100_000, annual_rate=0.05, term_periods=12,
        periods_per_year=12, kind="bullet",
    )
    rows = s.rows()
    assert len(rows) == 12
    expected_interest = 100_000 * 0.05 / 12
    assert rows[0]["interest"] == pytest.approx(expected_interest)
    assert rows[0]["principal_payment"] == 0
    assert rows[11]["principal_payment"] == 100_000
    assert rows[11]["balance_end"] == pytest.approx(0)


def test_linear_amortization():
    s = AmortizationSchedule(
        principal=120_000, annual_rate=0.06, term_periods=12,
        periods_per_year=12, kind="linear",
    )
    rows = s.rows()
    assert all(r["principal_payment"] == pytest.approx(10_000) for r in rows)
    assert rows[11]["balance_end"] == pytest.approx(0)


def test_french_amortization_constant_payment():
    s = AmortizationSchedule(
        principal=100_000, annual_rate=0.06, term_periods=12,
        periods_per_year=12, kind="french",
    )
    rows = s.rows()
    payments = {round(r["total_payment"], 2) for r in rows}
    assert len(payments) == 1
    assert rows[11]["balance_end"] == pytest.approx(0, abs=0.01)


def test_grace_period_only_interest():
    s = AmortizationSchedule(
        principal=100_000, annual_rate=0.06, term_periods=24,
        periods_per_year=12, kind="french", grace_periods=6,
    )
    rows = s.rows()
    for i in range(6):
        assert rows[i]["principal_payment"] == 0
        assert rows[i]["interest"] > 0
    assert rows[23]["balance_end"] == pytest.approx(0, abs=0.01)
