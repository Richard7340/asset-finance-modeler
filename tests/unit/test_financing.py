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


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------


def test_size_debt_zero_capex():
    """When total_capex is 0, max_debt should be 0 and infeasible."""
    cfads = [100_000.0] * 120
    result = size_debt(
        cfads=cfads, dscr_target=1.30, dscr_mode="min",
        interest_rate=0.05, tenor_periods=120,
        periods_per_year=12, max_leverage=0.80,
        total_capex=0, amortization="french", grace_periods=0,
    )
    assert result.max_debt == 0
    assert result.feasible is False


def test_size_debt_negative_cashflows():
    """Negative cash flows yield no debt capacity."""
    cfads = [-10_000.0] * 120
    result = size_debt(
        cfads=cfads, dscr_target=1.30, dscr_mode="min",
        interest_rate=0.05, tenor_periods=120,
        periods_per_year=12, max_leverage=0.80,
        total_capex=5_000_000, amortization="french", grace_periods=0,
    )
    assert result.feasible is False
    assert result.max_debt == 0


def test_size_debt_very_low_dscr_target():
    """Lower DSCR target (1.05) should allow at least as much debt as 1.30."""
    cfads = [100_000.0] * 180
    result_high = size_debt(
        cfads=cfads, dscr_target=1.30, dscr_mode="min",
        interest_rate=0.045, tenor_periods=180,
        periods_per_year=12, max_leverage=0.90,
        total_capex=10_000_000, amortization="french", grace_periods=0,
    )
    result_low = size_debt(
        cfads=cfads, dscr_target=1.05, dscr_mode="min",
        interest_rate=0.045, tenor_periods=180,
        periods_per_year=12, max_leverage=0.90,
        total_capex=10_000_000, amortization="french", grace_periods=0,
    )
    if result_high.feasible and result_low.feasible:
        assert result_low.max_debt >= result_high.max_debt


def test_size_debt_with_grace_period():
    """Grace periods reduce initial debt service and should allow at least as much debt."""
    cfads = [80_000.0] * 180
    result_no_grace = size_debt(
        cfads=cfads, dscr_target=1.20, dscr_mode="min",
        interest_rate=0.05, tenor_periods=180,
        periods_per_year=12, max_leverage=0.80,
        total_capex=10_000_000, amortization="french", grace_periods=0,
    )
    result_with_grace = size_debt(
        cfads=cfads, dscr_target=1.20, dscr_mode="min",
        interest_rate=0.05, tenor_periods=180,
        periods_per_year=12, max_leverage=0.80,
        total_capex=10_000_000, amortization="french", grace_periods=12,
    )
    if result_no_grace.feasible and result_with_grace.feasible:
        assert result_with_grace.max_debt >= result_no_grace.max_debt


def test_size_debt_avg_mode_vs_min():
    """Average DSCR mode should allow at least as much debt as min DSCR mode."""
    cfads = [100_000.0] * 180
    result_min = size_debt(
        cfads=cfads, dscr_target=1.30, dscr_mode="min",
        interest_rate=0.045, tenor_periods=180,
        periods_per_year=12, max_leverage=0.80,
        total_capex=10_000_000, amortization="french", grace_periods=0,
    )
    result_avg = size_debt(
        cfads=cfads, dscr_target=1.30, dscr_mode="avg",
        interest_rate=0.045, tenor_periods=180,
        periods_per_year=12, max_leverage=0.80,
        total_capex=10_000_000, amortization="french", grace_periods=0,
    )
    if result_min.feasible and result_avg.feasible:
        assert result_avg.max_debt >= result_min.max_debt


def test_size_debt_bullet_amortization():
    """Bullet amortization (all principal at maturity) must not crash and return a valid result."""
    cfads = [50_000.0] * 60
    result = size_debt(
        cfads=cfads, dscr_target=1.20, dscr_mode="min",
        interest_rate=0.06, tenor_periods=60,
        periods_per_year=12, max_leverage=0.70,
        total_capex=5_000_000, amortization="bullet", grace_periods=0,
    )
    assert isinstance(result.feasible, bool)
    if result.feasible:
        assert result.max_debt > 0


def test_size_debt_equity_required_correct():
    """equity_required must equal total_capex minus max_debt when feasible."""
    cfads = [100_000.0] * 180
    total_capex = 10_000_000
    result = size_debt(
        cfads=cfads, dscr_target=1.30, dscr_mode="min",
        interest_rate=0.045, tenor_periods=180,
        periods_per_year=12, max_leverage=0.80,
        total_capex=total_capex, amortization="french", grace_periods=0,
    )
    if result.feasible:
        assert result.equity_required == pytest.approx(total_capex - result.max_debt)
