
import pytest

from asset_finance_modeler.core.valuation import (
    compute_dcf,
    compute_discounted_payback,
    compute_irr,
    compute_lcoe,
    compute_lcos,
    compute_sensitivity_grid,
)


def test_dcf_gordon_simple():
    result = compute_dcf(
        fcf_series=[100] * 5,
        wacc_annual=0.10,
        terminal_growth=0.02,
        periods_per_year=1,
        terminal_method="gordon",
    )
    expected_pv = sum(100 / (1.1 ** t) for t in range(1, 6))
    terminal = 100 * 1.02 / (0.10 - 0.02)
    pv_terminal = terminal / (1.1 ** 5)
    assert result["pv_explicit"] == pytest.approx(expected_pv, rel=1e-3)
    assert result["pv_terminal"] == pytest.approx(pv_terminal, rel=1e-3)
    assert result["enterprise_value"] == pytest.approx(expected_pv + pv_terminal, rel=1e-3)


def test_dcf_exit_multiple_terminal():
    result = compute_dcf(
        fcf_series=[100, 200, 300, 400, 500],
        wacc_annual=0.20,
        terminal_growth=0,
        periods_per_year=1,
        terminal_method="exit_multiple",
        exit_arr=2000,
        exit_multiple_arr=6,
    )
    expected_terminal = 12000 / (1.20 ** 5)
    assert result["pv_terminal"] == pytest.approx(expected_terminal, rel=1e-3)


def test_dcf_handles_negative_growth():
    result = compute_dcf(
        fcf_series=[100, 100, 100],
        wacc_annual=0.10,
        terminal_growth=-0.01,
        periods_per_year=1,
        terminal_method="gordon",
    )
    assert result["enterprise_value"] > 0


def test_dcf_gordon_invalid_when_wacc_le_g():
    with pytest.raises(ValueError):
        compute_dcf(
            fcf_series=[100],
            wacc_annual=0.05,
            terminal_growth=0.10,
            periods_per_year=1,
            terminal_method="gordon",
        )


def test_sensitivity_grid_2d():
    grid = compute_sensitivity_grid(
        fcf_series=[100] * 5,
        wacc_values=[0.10, 0.15],
        growth_values=[0.02, 0.03],
        periods_per_year=1,
        terminal_method="gordon",
    )
    assert len(grid) == 2
    assert len(grid[0]) == 2
    assert grid[0][0] > grid[1][0]
    assert grid[0][1] > grid[0][0]


def test_compute_irr_basic():
    cashflows = [-1_000_000] + [150_000] * 12
    irr = compute_irr(cashflows, periods_per_year=1)
    assert 0.05 < irr < 0.15


def test_compute_irr_monthly():
    cashflows = [-500_000] + [10_000] * 120
    irr = compute_irr(cashflows, periods_per_year=12)
    assert irr > 0


def test_compute_lcoe():
    lcoe = compute_lcoe(total_costs_pv=50_000_000, total_energy_pv=1_200_000)
    assert lcoe == pytest.approx(41.67, abs=0.01)


def test_compute_lcos():
    lcos = compute_lcos(total_costs_pv=20_000_000, total_energy_discharged_pv=500_000)
    assert lcos == pytest.approx(40.0)


def test_discounted_payback():
    cashflows = [-1_000_000] + [200_000] * 10
    pb = compute_discounted_payback(cashflows, discount_rate=0.08, periods_per_year=1)
    assert 5 < pb < 8


def test_discounted_payback_never():
    cashflows = [-1_000_000] + [10_000] * 10
    pb = compute_discounted_payback(cashflows, discount_rate=0.10, periods_per_year=1)
    assert pb == float("inf")
