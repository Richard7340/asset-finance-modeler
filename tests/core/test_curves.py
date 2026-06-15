from asset_finance_modeler.core.drivers import CurvePhase, build_phased_curve


def test_build_phased_curve_three_phases():
    # SVJ spread: base 82, +2%/yr (y1-7), 0% (y8-15), -2%/yr (y16-30).
    # FIX 2: a "7y +2%" phase yields 7 compounding steps, so vals[7] == base*1.02**7
    # (previously off-by-one gave only 6 steps; vals[7] wrongly == vals[6]).
    phases = [CurvePhase(7, 0.02), CurvePhase(8, 0.0), CurvePhase(15, -0.02)]
    vals = build_phased_curve(82.0, phases, 30)
    assert len(vals) == 30
    assert vals[0] == 82.0
    assert abs(vals[1] - 82.0 * 1.02) < 1e-9
    assert abs(vals[7] - 82.0 * 1.02**7) < 1e-9
    # The 0% phase (years 8-15) holds the value flat after the +2% phase ends.
    assert abs(vals[15] - 82.0 * 1.02**7) < 1e-9
    assert vals[29] < vals[15]


def test_build_phased_curve_pads_when_phases_short():
    vals = build_phased_curve(100.0, [CurvePhase(2, 0.10)], 5)
    assert len(vals) == 5
    assert abs(vals[4] - 100.0 * 1.10**4) < 1e-6


from asset_finance_modeler.core.curves import Curve


def test_curve_from_points_and_at():
    c = Curve.from_points([10, 20, 30], name="x", source="test")
    assert c.at(0) == 10
    assert c.at(1) == 20
    assert c.at(5) == 30          # clamps to last
    assert c.to_list(4) == [10, 20, 30, 30]


def test_curve_from_phases():
    from asset_finance_modeler.core.drivers import CurvePhase
    c = Curve.from_phases(82.0, [CurvePhase(7, 0.02), CurvePhase(23, 0.0)], 30)
    assert len(c.to_list(30)) == 30
    assert c.at(0) == 82.0


def test_curve_from_growth():
    c = Curve.from_growth(100.0, 0.05, 3)
    assert abs(c.at(2) - 100.0 * 1.05**2) < 1e-9
