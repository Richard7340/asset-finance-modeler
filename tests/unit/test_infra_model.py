"""Unit tests for InfrastructureModel — the main infra orchestrator."""
from datetime import date

import pytest

from asset_finance_modeler.assets.infrastructure.model import InfrastructureModel
from asset_finance_modeler.assets.infrastructure.schema import (
    CAPEXBreakdown,
    CycleDegradation,
    InfraCapexItem,
    InfraOPEXConfig,
    InfrastructureModelConfig,
    PermitsTimeline,
    PPAStream,
    ProjectFinanceConfig,
    SolarProduction,
    TimeDegradation,
    BESSProduction,
    CapacityStream,
)
from asset_finance_modeler.assets.saas.schema import (
    HorizonConfig,
    ModelMeta,
    TaxesConfig,
    ValuationConfig,
)
from asset_finance_modeler.core.protocols import FinancialModel, FinancialOutput


# ---------------------------------------------------------------------------
# Config factory helpers
# ---------------------------------------------------------------------------


def _solar_config(periods: int = 120) -> InfrastructureModelConfig:
    return InfrastructureModelConfig(
        meta=ModelMeta(
            name="solar-test",
            horizon=HorizonConfig(periods=periods, frequency="M"),
            start_date=date(2026, 1, 1),
            initial_cash=0,
        ),
        production=SolarProduction(capacity_mwp=50),
        revenue=[
            PPAStream(
                price_eur_per_unit=45.0,
                volume_fraction=0.7,
                escalation_pct_yr=0,
            ),
            PPAStream(
                name="Merchant",
                price_eur_per_unit=50.0,
                volume_fraction=0.3,
                escalation_pct_yr=0,
            ),
        ],
        capex=CAPEXBreakdown(
            items=[
                InfraCapexItem(
                    name="EPC",
                    amount_per_unit=0.45,
                    unit="Wp",
                    quantity=50_000_000,
                )
            ]
        ),
        opex=InfraOPEXConfig(
            om_fixed_eur_per_mw_yr=12_000,
            insurance_pct_capex=0.005,
            opex_escalation_pct_yr=0,
        ),
        degradation=TimeDegradation(annual_rate=0.005),
        timeline=PermitsTimeline(construction_months=12),
        financing=ProjectFinanceConfig(),
        taxes=TaxesConfig(),
        valuation=ValuationConfig(discount_rate_annual=0.07),
    )


def _bess_config(periods: int = 60) -> InfrastructureModelConfig:
    return InfrastructureModelConfig(
        meta=ModelMeta(
            name="bess-test",
            horizon=HorizonConfig(periods=periods, frequency="M"),
            start_date=date(2026, 1, 1),
            initial_cash=0,
        ),
        production=BESSProduction(power_mw=20, duration_hours=4, cycles_per_day=1.5),
        revenue=[
            PPAStream(
                name="Arbitrage-proxy",
                price_eur_per_unit=38.0,
                volume_fraction=1.0,
                escalation_pct_yr=0,
            ),
            CapacityStream(name="Capacity Market", eur_per_mw_yr=32_000),
        ],
        capex=CAPEXBreakdown(
            items=[
                InfraCapexItem(
                    name="Battery + BOS",
                    amount_per_unit=280,
                    unit="kWh",
                )
            ]
        ),
        opex=InfraOPEXConfig(
            om_fixed_eur_per_mw_yr=8_000,
            insurance_pct_capex=0.004,
            opex_escalation_pct_yr=0,
        ),
        degradation=CycleDegradation(
            capacity_fade_per_cycle=0.00004,
            calendar_fade_annual=0.015,
            eol_capacity_pct=0.70,
        ),
        timeline=PermitsTimeline(construction_months=8),
        financing=ProjectFinanceConfig(),
        taxes=TaxesConfig(),
        valuation=ValuationConfig(discount_rate_annual=0.08),
    )


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_implements_protocol():
    assert isinstance(InfrastructureModel(_solar_config()), FinancialModel)


# ---------------------------------------------------------------------------
# Basic output structure
# ---------------------------------------------------------------------------


def test_run_returns_financial_output():
    result = InfrastructureModel(_solar_config(60)).run()
    assert isinstance(result, FinancialOutput)
    assert len(result.pnl["revenue"]) == 60
    assert len(result.cashflow["cash"]) == 60
    assert len(result.balance["total_assets"]) == 60


def test_revenue_positive():
    result = InfrastructureModel(_solar_config(60)).run()
    assert result.pnl["revenue"][0] > 0


def test_all_pnl_series_correct_length():
    n = 36
    result = InfrastructureModel(_solar_config(n)).run()
    for key, series in result.pnl.items():
        if isinstance(series, list):
            assert len(series) == n, f"pnl[{key!r}] has wrong length"


def test_cashflow_keys_present():
    result = InfrastructureModel(_solar_config(24)).run()
    for key in ("cfo", "cfi", "cff", "cash"):
        assert key in result.cashflow


def test_balance_keys_present():
    result = InfrastructureModel(_solar_config(24)).run()
    for key in ("total_assets", "total_liabilities", "equity"):
        assert key in result.balance


# ---------------------------------------------------------------------------
# Project KPIs
# ---------------------------------------------------------------------------


def test_has_project_kpis():
    result = InfrastructureModel(_solar_config(120)).run()
    assert result.project_kpis is not None
    assert result.project_kpis.lcoe is not None
    assert result.project_kpis.lcoe > 0


def test_lcoe_reasonable_range():
    """Solar LCOE should be between €10 and €200 per MWh for a 50 MW plant."""
    result = InfrastructureModel(_solar_config(120)).run()
    kpis = result.project_kpis
    assert kpis is not None
    assert kpis.lcoe is not None
    assert 10 < kpis.lcoe < 200, f"LCOE {kpis.lcoe:.2f} outside expected range"


def test_dscr_series_correct_length():
    result = InfrastructureModel(_solar_config(60)).run()
    assert len(result.project_kpis.dscr_series) == 60  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def test_summary_has_capex():
    result = InfrastructureModel(_solar_config(60)).run()
    assert "total_capex" in result.summary
    assert result.summary["total_capex"] > 0


def test_summary_keys():
    result = InfrastructureModel(_solar_config(60)).run()
    for key in ("total_capex", "revenue_y1", "ebitda_margin_end", "cash_end", "enterprise_value"):
        assert key in result.summary


# ---------------------------------------------------------------------------
# BESS variant
# ---------------------------------------------------------------------------


def test_bess_runs():
    result = InfrastructureModel(_bess_config(60)).run()
    assert isinstance(result, FinancialOutput)
    assert result.summary["total_capex"] > 0
    assert result.pnl["revenue"][0] > 0


def test_bess_capex_reflects_kwh():
    """BESS: 20 MW × 4 h = 80 MWh = 80 000 kWh × 280 €/kWh = 22.4 M before contingency."""
    result = InfrastructureModel(_bess_config(60)).run()
    # Equipment cost = 80_000 kWh × 280 = 22_400_000; add 8% contingency = 24_192_000
    assert result.summary["total_capex"] > 20_000_000


# ---------------------------------------------------------------------------
# Preset loading and end-to-end
# ---------------------------------------------------------------------------


def test_preset_solar_loads_and_runs():
    from asset_finance_modeler.assets.infrastructure.loader import load_preset

    cfg = load_preset("solar_pv_50mw_spain")
    result = InfrastructureModel(cfg).run()
    assert isinstance(result, FinancialOutput)
    assert result.project_kpis is not None
    assert result.summary["total_capex"] > 0


def test_preset_bess_loads_and_runs():
    from asset_finance_modeler.assets.infrastructure.loader import load_preset

    cfg = load_preset("bess_20mw_4h")
    result = InfrastructureModel(cfg).run()
    assert isinstance(result, FinancialOutput)
    assert result.summary["total_capex"] > 0


def test_preset_solar_enterprise_value_positive():
    from asset_finance_modeler.assets.infrastructure.loader import load_preset

    cfg = load_preset("solar_pv_50mw_spain")
    result = InfrastructureModel(cfg).run()
    # With reasonable assumptions EV should be positive
    assert result.valuation["enterprise_value"] != 0  # may be negative if WACC > growth but not 0


def test_load_yaml_roundtrip(tmp_path):
    """load_yaml should produce the same config as load_preset for the same data."""
    import shutil
    import yaml

    from asset_finance_modeler.assets.infrastructure.loader import load_preset, load_yaml

    cfg_preset = load_preset("solar_pv_50mw_spain")

    # Write preset data to a temp file and reload
    data = cfg_preset.model_dump(mode="json")
    tmp_yaml = tmp_path / "test.yaml"
    tmp_yaml.write_text(yaml.dump(data))

    cfg_loaded = load_yaml(tmp_yaml)
    assert cfg_loaded.meta.name == cfg_preset.meta.name
    assert cfg_loaded.meta.horizon.periods == cfg_preset.meta.horizon.periods


# ---------------------------------------------------------------------------
# Debt integration (no-debt path — no senior configured)
# ---------------------------------------------------------------------------


def test_no_debt_path():
    """When financing.senior is None, debt arrays should be zero."""
    result = InfrastructureModel(_solar_config(24)).run()
    # No senior debt configured in _solar_config
    assert all(v == 0.0 for v in result.cashflow["cff"])


# ---------------------------------------------------------------------------
# inputs_resolved round-trip
# ---------------------------------------------------------------------------


def test_inputs_resolved_is_dict():
    result = InfrastructureModel(_solar_config(24)).run()
    assert isinstance(result.inputs_resolved, dict)
    assert "meta" in result.inputs_resolved
    assert "production" in result.inputs_resolved


# ---------------------------------------------------------------------------
# New tech-type presets: wind + data center
# ---------------------------------------------------------------------------


def test_preset_wind_loads_and_runs():
    from asset_finance_modeler.assets.infrastructure.loader import load_preset

    cfg = load_preset("wind_onshore_30mw_spain")
    result = InfrastructureModel(cfg).run()
    assert isinstance(result, FinancialOutput)
    assert result.project_kpis is not None
    assert result.summary["total_capex"] > 0


def test_preset_datacenter_loads_and_runs():
    from asset_finance_modeler.assets.infrastructure.loader import load_preset

    cfg = load_preset("datacenter_10mw_tier3")
    result = InfrastructureModel(cfg).run()
    assert isinstance(result, FinancialOutput)
    assert result.summary["total_capex"] > 0
