import pytest

from asset_finance_modeler.core.drivers import GrowthCurve, expand_growth


def test_constant_value_expands():
    assert expand_growth(5.0, periods=4) == [5.0, 5.0, 5.0, 5.0]


def test_list_value_passes_through():
    assert expand_growth([1.0, 2.0, 3.0], periods=3) == [1.0, 2.0, 3.0]


def test_list_value_shorter_pads_with_last():
    assert expand_growth([1.0, 2.0], periods=4) == [1.0, 2.0, 2.0, 2.0]


def test_list_value_longer_than_periods_raises():
    with pytest.raises(ValueError):
        expand_growth([1.0, 2.0, 3.0, 4.0], periods=3)


def test_growth_curve_linear():
    c = GrowthCurve(kind="linear", start=10, end=20, periods=5)
    assert c.values() == [10.0, 12.5, 15.0, 17.5, 20.0]


def test_growth_curve_geometric():
    c = GrowthCurve(kind="geometric", start=10, rate=0.10, periods=4)
    vals = c.values()
    assert vals[0] == 10
    assert vals[1] == pytest.approx(11.0)
    assert vals[3] == pytest.approx(13.31)


def test_growth_curve_step():
    c = GrowthCurve(kind="step", values=[0, 0, 5, 10, 10], periods=5)
    assert c.values() == [0.0, 0.0, 5.0, 10.0, 10.0]
