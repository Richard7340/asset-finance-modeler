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
