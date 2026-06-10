from asset_finance_modeler.assets.infrastructure.loader import load_preset
from asset_finance_modeler.assets.infrastructure.model import InfrastructureModel


def test_npv_equity_present_and_higher_ke_reduces_it():
    out = InfrastructureModel(load_preset("solar_pv_50mw_spain")).run()
    assert hasattr(out.project_kpis, "npv_equity")
    cfg2 = load_preset("solar_pv_50mw_spain")
    cfg2.valuation.cost_of_equity_annual = cfg2.valuation.discount_rate_annual + 0.03
    out2 = InfrastructureModel(cfg2).run()
    assert out2.project_kpis.npv_equity < out.project_kpis.npv_equity
