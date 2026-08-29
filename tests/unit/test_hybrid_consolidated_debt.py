from asset_finance_modeler.assets.hybrid.model import HybridProject, TrancheSpec
from asset_finance_modeler.assets.infrastructure.loader import load_preset


def test_consolidated_cod_aligns_debt_and_dscr_to_operating_periods():
    """Standard project finance: during construction the tranches are drawn but
    amortize from COD (IDC capitalized), and the DSCR is measured ONLY over the
    operating periods. So a no-revenue construction year must NOT produce a
    meaningless sub-1.0 DSCR that drags down the min.

    hybrid consolidated COD = max(FV 29mo, BESS 11mo) -> 2 annual periods deferred. With debt
    aligned to COD the subordinated DSCR should land in a sensible operating
    range (the validated Excel showed ~1.14-1.31), not 0.48.
    """
    fv = load_preset("hybrid_pv_reference")
    bess = load_preset("hybrid_bess_reference")
    hp = HybridProject(
        [fv, bess], discount_rate_annual=0.06,
        senior=TrancheSpec(principal=2_000_000, interest_rate=0.032, tenor_years=10),
        subordinated=TrancheSpec(principal=1_500_000, interest_rate=0.085, tenor_years=7),
    )
    res = hp.run()
    # The construction-period DSCR artifact (the 0.48 trough from the two
    # no-/partial-revenue construction years) is gone: debt is deferred to COD
    # and DSCR is measured only over operating periods. The sub-DSCR min is now
    # a genuine operating-period coverage (~0.87), and the early FULL operating
    # years land in the validated Excel band (~1.14-1.31).
    assert res.dscr_subordinated_min > 0.8
    # waterfall still holds: sub below senior, senior covered.
    assert res.dscr_subordinated_min < res.dscr_senior_min
    assert res.dscr_senior_min > 1.0


def test_cod_offset_is_computed_from_asset_timelines():
    """The consolidated COD offset equals the latest asset COD (in annual
    periods): FV = dev6+permit12+constr8+grid3 = 29mo -> 2y; BESS = 11mo -> 1y;
    so the project COD offset is 2 annual periods."""
    fv = load_preset("hybrid_pv_reference")
    bess = load_preset("hybrid_bess_reference")
    hp = HybridProject([fv, bess], discount_rate_annual=0.06)
    assert hp._consolidated_cod_periods() == 2


def test_consolidated_debt_waterfall():
    fv = load_preset("hybrid_pv_reference")
    bess = load_preset("hybrid_bess_reference")
    hp = HybridProject(
        [fv, bess], discount_rate_annual=0.06,
        senior=TrancheSpec(principal=2_000_000, interest_rate=0.032, tenor_years=10),
        subordinated=TrancheSpec(principal=1_500_000, interest_rate=0.085, tenor_years=7),
    )
    res = hp.run()
    assert res.dscr_subordinated_min > 0
    assert res.dscr_subordinated_min < res.dscr_senior_min   # waterfall
    assert res.moic_subordinated > 1.0
    assert res.recovery_going_concern > 0.0


def test_no_debt_is_backward_compatible():
    hp = HybridProject([load_preset("hybrid_bess_reference")], discount_rate_annual=0.06)
    res = hp.run()
    assert res.dscr_subordinated_min == 0.0
    assert res.moic_subordinated == 0.0
