from asset_finance_modeler.core.valuation import compute_moic, compute_recovery_multiple


def test_moic_basic():
    assert abs(compute_moic([200.0] * 7, 1000.0) - 1.4) < 1e-9


def test_moic_zero_principal():
    assert compute_moic([100.0], 0.0) == 0.0


def test_recovery_multiple_pv_over_principal():
    cfads = [0.0] * 5 + [100.0] * 5
    rec = compute_recovery_multiple(cfads, from_period=5, discount_rate_annual=0.0,
                                    periods_per_year=1, outstanding_principal=250.0)
    assert abs(rec - 2.0) < 1e-9


def test_recovery_discounted_and_zero_principal():
    cfads = [100.0, 100.0]
    rec = compute_recovery_multiple(cfads, 0, 0.10, 1, 100.0)
    assert abs(rec - (100 + 100 / 1.1) / 100) < 1e-6
    assert compute_recovery_multiple([100.0], 0, 0.0, 1, 0.0) == float("inf")
