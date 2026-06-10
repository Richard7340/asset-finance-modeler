from asset_finance_modeler.core.financing import compute_waterfall_dscr


def test_waterfall_two_tranches():
    cfads = [200.0, 200.0]
    senior_ds = [100.0, 100.0]
    sub_ds = [50.0, 50.0]
    senior_dscr, sub_dscr = compute_waterfall_dscr(cfads, [senior_ds, sub_ds])
    assert senior_dscr == [2.0, 2.0]
    assert sub_dscr == [2.0, 2.0]


def test_waterfall_sub_is_thinner_than_senior():
    s, sub = compute_waterfall_dscr([150.0], [[100.0], [40.0]])
    assert s == [1.5]
    assert sub == [1.25]


def test_waterfall_zero_service_is_inf_and_negative_avail_is_zero():
    s, sub = compute_waterfall_dscr([90.0], [[100.0], [0.0]])
    assert sub == [float("inf")]
    assert s == [0.9]
    s2, sub2 = compute_waterfall_dscr([90.0], [[100.0], [50.0]])
    assert sub2 == [0.0]
