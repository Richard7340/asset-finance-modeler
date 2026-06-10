from asset_finance_modeler.assets.hybrid.model import HybridProject
from asset_finance_modeler.assets.infrastructure.loader import load_preset


def test_hybrid_consolidates_two_assets():
    hp = HybridProject(
        [load_preset("solar_pv_50mw_spain"), load_preset("bess_20mw_4h")],
        discount_rate_annual=0.06,
    )
    res = hp.run()
    assert abs(res.total_capex - sum(res.asset_total_capex)) < 1.0
    assert len(res.asset_total_capex) == 2
    assert len(res.consolidated_fcf) >= 2
    assert isinstance(res.npv, float) and isinstance(res.irr, float)
    # consolidated FCF year-0 should be negative (combined capex outlay)
    assert res.consolidated_fcf[0] < 0
