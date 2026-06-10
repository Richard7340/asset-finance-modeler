from asset_finance_modeler.assets.infrastructure.loader import load_preset
from asset_finance_modeler.assets.infrastructure.model import InfrastructureModel


def test_svj_presets_load_and_run():
    fv = InfrastructureModel(load_preset("svj_fv_cordoba")).run()
    bess_cfg = load_preset("svj_bess_cordoba")
    bess = InfrastructureModel(bess_cfg).run()
    assert 3.6e6 < fv.summary["total_capex"] < 5.2e6
    # The headline total_capex folds in lifecycle capex_events (the year-15
    # repowering injection). The build-cost bound applies to the initial build,
    # so net out the events before checking the range.
    bess_events = sum(e.amount for e in bess_cfg.capex_events)
    bess_initial_build = bess.summary["total_capex"] - bess_events
    assert 1.5e6 < bess_initial_build < 2.2e6
