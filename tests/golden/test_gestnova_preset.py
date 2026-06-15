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
    # P2-5 golden move (legitimate): previously-dead SaaS params now take effect.
    # The gestnova preset sets price_escalation_annual=0.03 (revenue_end_period
    # rises 206,783 → 212,362), gross_revenue_retention=0.95, payroll_taxes_pct=
    # 0.30 (team cost +30%) and inflation_annual=0.025 (fixed opex escalates).
    # Net: ebitda_margin_end 0.80 → 0.77, cash_end and EV down (4.72M → 4.55M).
    # exit_multiple_arr=6 stays inert here because the preset explicitly chose
    # terminal_method=gordon. Snapshot refreshed to the post-wiring economics;
    # not a regression.
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
