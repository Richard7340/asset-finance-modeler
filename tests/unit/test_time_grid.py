from datetime import date

import pytest

from asset_finance_modeler.core.time_grid import TimeGrid


def test_monthly_grid_basic():
    g = TimeGrid(periods=12, frequency="M", start_date=date(2026, 1, 1))
    assert g.periods == 12
    assert g.dates[0] == date(2026, 1, 1)
    assert g.dates[11] == date(2026, 12, 1)


def test_quarterly_grid():
    g = TimeGrid(periods=4, frequency="Q", start_date=date(2026, 1, 1))
    assert [d.month for d in g.dates] == [1, 4, 7, 10]


def test_annual_grid():
    g = TimeGrid(periods=3, frequency="Y", start_date=date(2026, 1, 1))
    assert [d.year for d in g.dates] == [2026, 2027, 2028]


def test_periods_per_year():
    assert TimeGrid(periods=12, frequency="M", start_date=date(2026, 1, 1)).periods_per_year == 12
    assert TimeGrid(periods=4, frequency="Q", start_date=date(2026, 1, 1)).periods_per_year == 4
    assert TimeGrid(periods=3, frequency="Y", start_date=date(2026, 1, 1)).periods_per_year == 1


def test_invalid_frequency():
    with pytest.raises(ValueError):
        TimeGrid(periods=12, frequency="X", start_date=date(2026, 1, 1))
