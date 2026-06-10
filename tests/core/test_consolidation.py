from asset_finance_modeler.core.portfolio import consolidate_npv, consolidate_series


def test_consolidate_series_sums_aligned_and_pads():
    a = [10.0, 10.0, 10.0]
    b = [5.0, 5.0]
    assert consolidate_series([a, b]) == [15.0, 15.0, 10.0]


def test_consolidate_series_empty():
    assert consolidate_series([]) == []


def test_consolidate_npv_plain_discounted_with_year0():
    fcf = [-100.0, 60.0, 60.0]
    assert abs(consolidate_npv(fcf, 0.0) - 20.0) < 1e-9
    assert abs(consolidate_npv(fcf, 0.10) - (-100 + 60 / 1.1 + 60 / 1.21)) < 1e-6
