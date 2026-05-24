import pytest

from asset_finance_modeler.core.financing import compute_cash_sweep, compute_dsra, size_debt
from asset_finance_modeler.core.protocols import DebtSizingResult


def test_dsra_6_months():
    debt_service = [10_000.0] * 24
    dsra = compute_dsra(debt_service, dsra_months=6, periods_per_year=12)
    assert len(dsra) == 24
    assert dsra[0] == pytest.approx(60_000)
    assert dsra[-1] == pytest.approx(0)


def test_dsra_zero_months():
    debt_service = [10_000.0] * 12
    dsra = compute_dsra(debt_service, dsra_months=0, periods_per_year=12)
    assert all(d == 0 for d in dsra)


def test_cash_sweep_above_trigger():
    excess_cash = [50_000.0] * 12
    dscr = [1.5] * 12
    swept = compute_cash_sweep(excess_cash, dscr, trigger_dscr=1.40, sweep_pct=0.50)
    assert all(s == pytest.approx(25_000) for s in swept)


def test_cash_sweep_below_trigger_no_sweep():
    excess_cash = [50_000.0] * 12
    dscr = [1.2] * 12
    swept = compute_cash_sweep(excess_cash, dscr, trigger_dscr=1.40, sweep_pct=0.50)
    assert all(s == 0 for s in swept)


def test_cash_sweep_mixed():
    excess_cash = [50_000.0] * 6
    dscr = [1.5, 1.3, 1.6, 1.1, 1.45, 1.0]
    swept = compute_cash_sweep(excess_cash, dscr, trigger_dscr=1.40, sweep_pct=0.50)
    assert swept[0] == pytest.approx(25_000)
    assert swept[1] == 0
    assert swept[2] == pytest.approx(25_000)
    assert swept[3] == 0
    assert swept[4] == pytest.approx(25_000)
    assert swept[5] == 0


def test_size_debt_feasible():
    cfads = [100_000.0] * 180
    result = size_debt(
        cfads=cfads, dscr_target=1.30, dscr_mode="min",
        interest_rate=0.045, tenor_periods=180,
        periods_per_year=12, max_leverage=0.80,
        total_capex=10_000_000, amortization="french", grace_periods=0,
    )
    assert isinstance(result, DebtSizingResult)
    assert result.feasible is True
    assert result.max_debt > 0
    assert result.dscr_min >= 1.29
    assert result.leverage_ratio <= 0.80
    assert result.equity_required > 0


def test_size_debt_infeasible():
    cfads = [1_000.0] * 60
    result = size_debt(
        cfads=cfads, dscr_target=1.30, dscr_mode="min",
        interest_rate=0.10, tenor_periods=60,
        periods_per_year=12, max_leverage=0.80,
        total_capex=10_000_000, amortization="french", grace_periods=0,
    )
    assert result.feasible is False
    assert result.max_debt == 0


def test_size_debt_leverage_cap():
    cfads = [500_000.0] * 240
    result = size_debt(
        cfads=cfads, dscr_target=1.10, dscr_mode="min",
        interest_rate=0.03, tenor_periods=240,
        periods_per_year=12, max_leverage=0.70,
        total_capex=20_000_000, amortization="french", grace_periods=0,
    )
    assert result.feasible is True
    assert result.max_debt <= 20_000_000 * 0.70 + 1
