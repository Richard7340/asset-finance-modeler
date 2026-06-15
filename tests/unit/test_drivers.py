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


from asset_finance_modeler.core.drivers import CurvePhase, build_phased_curve


def test_phased_curve_year1_is_base():
    """Year 1 (index 0) is the base, no growth applied yet."""
    vals = build_phased_curve(82.0, [CurvePhase(7, 0.02)], periods=10)
    assert vals[0] == 82.0


def test_phased_curve_n_years_yields_n_compounding_steps():
    """A '7y +2%' phase produces 7 compounding steps: values[7] == base * 1.02**7.

    Convention: growth steps INTO each year of the phase, so after a phase
    declared 'N years at +g%' the value reaches base * (1+g)**N at index N
    (FIX 2 — previously this was off by one and only gave 6 steps)."""
    base = 82.0
    vals = build_phased_curve(base, [CurvePhase(7, 0.02), CurvePhase(8, 0.0)], periods=16)
    assert vals[7] == pytest.approx(base * 1.02 ** 7)
    # Flat phase: value holds after the +2% phase ends.
    assert vals[8] == pytest.approx(base * 1.02 ** 7)
    assert vals[15] == pytest.approx(base * 1.02 ** 7)


def test_phased_curve_matches_spread_da_es_library():
    """The spread_da_es library curve reaches base*1.02**7 at the end of its
    '7y +2%' phase (index 7)."""
    from asset_finance_modeler.core.curve_library import load_curve

    c = load_curve("spread_da_es")
    vals = c.to_list(30)
    assert vals[0] == pytest.approx(82.0)
    assert vals[7] == pytest.approx(82.0 * 1.02 ** 7)
