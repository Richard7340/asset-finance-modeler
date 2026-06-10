from asset_finance_modeler.core.drivers import CurvePhase, build_phased_curve


def test_build_phased_curve_three_phases():
    # SVJ spread: base 82, +2%/yr (y1-7), 0% (y8-15), -2%/yr (y16-30)
    phases = [CurvePhase(7, 0.02), CurvePhase(8, 0.0), CurvePhase(15, -0.02)]
    vals = build_phased_curve(82.0, phases, 30)
    assert len(vals) == 30
    assert vals[0] == 82.0
    assert abs(vals[1] - 82.0 * 1.02) < 1e-9
    assert abs(vals[6] - 82.0 * 1.02**6) < 1e-9
    assert abs(vals[7] - vals[6]) < 1e-9
    assert vals[29] < vals[14]


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
