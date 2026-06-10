from asset_finance_modeler.assets.infrastructure.loader import load_preset
from asset_finance_modeler.assets.infrastructure.model import InfrastructureModel
from asset_finance_modeler.assets.infrastructure.schema import SubordinatedDebtConfig


def test_model_exposes_subordinated_dscr_below_senior():
    cfg = load_preset("bess_20mw_4h")
    # 4,000,000 is feasible for the bess preset cash flows: it yields a
    # positive subordinated DSCR (~0.67) that sits below the senior min (~1.29)
    # because the subordinated tranche sees cash net of senior debt service.
    cfg.financing.subordinated = SubordinatedDebtConfig(
        principal=4_000_000.0, interest_rate=0.085, tenor_years=7, amortization="french"
    )
    out = InfrastructureModel(cfg).run()
    k = out.project_kpis
    assert k is not None
    assert k.dscr_subordinated_min > 0
    assert k.dscr_subordinated_min < k.dscr_senior_min
