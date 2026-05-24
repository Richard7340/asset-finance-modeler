import pytest

from asset_finance_modeler.core.degradation import (
    degradation_cycle_based,
    degradation_none,
    degradation_time_based,
    degradation_usage_based,
)


def test_time_based_basic():
    mults = degradation_time_based(periods=240, annual_rate=0.005, periods_per_year=12)
    assert len(mults) == 240
    assert mults[0] == pytest.approx(1.0)
    assert mults[11] == pytest.approx(1 - 0.005 * (11 / 12), abs=0.001)
    assert mults[239] < mults[0]


def test_time_based_20yr_end_value():
    mults = degradation_time_based(periods=240, annual_rate=0.005, periods_per_year=12)
    assert mults[-1] == pytest.approx(1 - 0.005 * 20, abs=0.01)


def test_cycle_based_declines():
    mults = degradation_cycle_based(
        periods=120, cycles_per_period=45, fade_per_cycle=0.00005,
        calendar_fade_annual=0.02, periods_per_year=12, eol_pct=0.70,
    )
    assert len(mults) == 120
    assert mults[0] == pytest.approx(1.0)
    assert mults[-1] < mults[0]


def test_cycle_based_clamps_at_eol():
    mults = degradation_cycle_based(
        periods=360, cycles_per_period=90, fade_per_cycle=0.001,
        calendar_fade_annual=0.05, periods_per_year=12, eol_pct=0.70,
    )
    assert all(m >= 0.70 for m in mults)


def test_usage_based():
    mults = degradation_usage_based(
        periods=120, hours_per_period=720, loss_per_1000h=0.001,
    )
    assert mults[0] == pytest.approx(1.0)
    assert mults[-1] < 1.0
    assert all(mults[i] >= mults[i + 1] for i in range(len(mults) - 1))


def test_none_returns_ones():
    mults = degradation_none(periods=60)
    assert mults == [1.0] * 60
