from asset_finance_modeler.assets.infrastructure.loader import load_preset
from asset_finance_modeler.assets.infrastructure.model import InfrastructureModel
from asset_finance_modeler.assets.infrastructure.schema import SubordinatedDebtConfig


def test_moic_and_recovery_for_subordinated():
    cfg = load_preset("bess_20mw_4h")
    cfg.financing.subordinated = SubordinatedDebtConfig(
        principal=4_000_000.0, interest_rate=0.085, tenor_years=7, amortization="french"
    )
    k = InfrastructureModel(cfg).run().project_kpis
    assert k.moic_subordinated > 1.0
    assert k.recovery_going_concern > 0.0


def test_moic_recovery_zero_without_subordinated():
    k = InfrastructureModel(load_preset("bess_20mw_4h")).run().project_kpis
    assert k.moic_subordinated == 0.0
    assert k.recovery_going_concern == 0.0
