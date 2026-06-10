from asset_finance_modeler.assets.hybrid.model import HybridProject, TrancheSpec
from asset_finance_modeler.assets.infrastructure.loader import load_preset


def test_consolidated_debt_waterfall():
    fv = load_preset("svj_fv_cordoba")
    bess = load_preset("svj_bess_cordoba")
    hp = HybridProject(
        [fv, bess], discount_rate_annual=0.0537,
        senior=TrancheSpec(principal=2_220_000, interest_rate=0.032, tenor_years=10),
        subordinated=TrancheSpec(principal=1_841_000, interest_rate=0.085, tenor_years=7),
    )
    res = hp.run()
    assert res.dscr_subordinated_min > 0
    assert res.dscr_subordinated_min < res.dscr_senior_min   # waterfall
    assert res.moic_subordinated > 1.0
    assert res.recovery_going_concern > 0.0


def test_no_debt_is_backward_compatible():
    hp = HybridProject([load_preset("svj_bess_cordoba")], discount_rate_annual=0.0537)
    res = hp.run()
    assert res.dscr_subordinated_min == 0.0
    assert res.moic_subordinated == 0.0
