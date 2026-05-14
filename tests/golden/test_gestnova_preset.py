import pytest

from asset_finance_modeler.assets.saas.loader import load_preset
from asset_finance_modeler.assets.saas.model import SaasModel


def test_gestnova_preset_loads():
    cfg = load_preset("gestnova")
    assert cfg.meta.name == "gestnova"
    assert cfg.meta.horizon.periods == 60


def test_gestnova_preset_runs_no_errors():
    cfg = load_preset("gestnova")
    results = SaasModel(cfg).run()
    assert len(results.pnl["revenue"]) == 60
    assert results.summary["revenue_y1"] > 0


def test_gestnova_preset_summary_shape(snapshot):
    cfg = load_preset("gestnova")
    results = SaasModel(cfg).run()
    rounded_summary = {
        k: (round(v, 2) if isinstance(v, float) else v)
        for k, v in results.summary.items()
    }
    snapshot.assert_match(str(rounded_summary), "gestnova_summary.txt")


def test_gestnova_balance_identity_holds():
    cfg = load_preset("gestnova")
    results = SaasModel(cfg).run()
    for t in range(len(results.balance["total_assets"])):
        assets = results.balance["total_assets"][t]
        liab = results.balance["total_liabilities"][t]
        eq = results.balance["equity"][t]
        assert assets == pytest.approx(liab + eq, abs=0.01)
