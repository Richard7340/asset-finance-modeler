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
    SeniorDebtConfig,
    SolarProduction,
    SubordinatedDebtConfig,
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
# P1-4: construction / permitting timeline defers production & revenue
# ---------------------------------------------------------------------------


def _zero_timeline_solar(periods: int = 120) -> InfrastructureModelConfig:
    cfg = _solar_config(periods)
    cfg.timeline = PermitsTimeline(
        development_months=0,
        permitting_months=0,
        construction_months=0,
        grid_connection_months=0,
    )
    return cfg


def test_timeline_defers_production_and_revenue():
    # 6 months total COD offset (only construction set; others zeroed).
    cfg = _solar_config(60)
    cfg.timeline = PermitsTimeline(
        development_months=0,
        permitting_months=0,
        construction_months=6,
        grid_connection_months=0,
    )
    result = InfrastructureModel(cfg).run()
    rev = result.pnl["revenue"]
    rb = result.revenue_breakdown["total"]
    # Revenue is zero during the 6 construction months, positive once COD hits.
    assert all(rev[t] == 0 for t in range(6))
    assert all(rb[t] == 0 for t in range(6))
    assert rev[6] > 0


def test_zero_timeline_no_deferral():
    # A fully-zero timeline = no offset: production/revenue start at period 0.
    result = InfrastructureModel(_zero_timeline_solar(60)).run()
    assert result.pnl["revenue"][0] > 0


def test_timeline_spreads_capex_over_construction():
    # CAPEX is spread across the construction window instead of all at t=0.
    cfg = _solar_config(60)
    cfg.timeline = PermitsTimeline(
        development_months=0,
        permitting_months=0,
        construction_months=4,
        grid_connection_months=0,
    )
    result = InfrastructureModel(cfg).run()
    # CFI = -capex_spend (no other investing flows here).
    capex_spend = [-v for v in result.cashflow["cfi"]]
    # Spread over the 4 construction months (not a single period-0 lump).
    assert capex_spend[0] > 0
    assert capex_spend[3] > 0
    total = result.summary["total_capex"]
    assert sum(capex_spend) == pytest.approx(total, rel=1e-9)


# ---------------------------------------------------------------------------
# Debt aligns to COD (interest capitalized during construction; DSCR over
# operating periods only) — standard project finance.
# ---------------------------------------------------------------------------


def _solar_with_debt(periods: int = 120) -> InfrastructureModelConfig:
    cfg = _solar_config(periods)
    cfg.financing = ProjectFinanceConfig(
        senior=SeniorDebtConfig(
            tenor_years=10, interest_rate=0.04, dscr_target=1.30, auto_size=False
        ),
        subordinated=SubordinatedDebtConfig(
            principal=2_000_000.0, interest_rate=0.085, tenor_years=7
        ),
        max_leverage=0.7,
    )
    return cfg


def test_debt_service_starts_at_cod_not_period_zero():
    """With a construction timeline, the debt-service series carries NO payment
    during the construction window (interest capitalized = IDC) and the first
    debt service lands at COD."""
    cfg = _solar_with_debt(120)
    cfg.timeline = PermitsTimeline(
        development_months=0, permitting_months=0,
        construction_months=12, grid_connection_months=0,
    )  # COD = 12 monthly periods
    result = InfrastructureModel(cfg).run()
    ds = result.debt_metrics["dscr"]
    # Construction periods (no revenue) are NOT scored as DSCR < 1 — they carry
    # no debt service, so DSCR there is inf (no obligation) and is excluded.
    interest = result.pnl["interest_expense"]
    principal = result.cashflow.get("debt_principal_repaid")
    # No interest OR principal paid in the construction window (IDC capitalized).
    assert all(interest[t] == 0.0 for t in range(12))
    if principal is not None:
        assert all(principal[t] == 0.0 for t in range(12))
    # First debt service lands at COD.
    assert interest[12] > 0.0
    # DSCR min is measured over operating periods → no spurious sub-1.0 from a
    # zero-revenue construction period.
    kpis = result.project_kpis
    assert kpis.dscr_senior_min > 0.0
    del ds


def test_zero_timeline_debt_service_unchanged():
    """A zero-timeline asset (COD = period 0) produces the SAME debt service as
    before the COD alignment — no regression."""
    base = _solar_with_debt(120)
    base.timeline = PermitsTimeline()  # all zero → COD = 0
    result = InfrastructureModel(base).run()
    interest = result.pnl["interest_expense"]
    # Debt service starts at period 0 (drawdown + first amortization), exactly
    # as the legacy behaviour.
    assert interest[0] > 0.0
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
    # P1-4: _solar_config declares a timeline (construction_months=12 plus the
    # schema defaults dev=12/permit=18/grid=6 => 48-month COD offset), so period
    # 0 is now during construction (revenue=0). Revenue is positive once the
    # plant reaches commercial operation. Use a zero-timeline config to assert
    # the operating revenue itself is positive.
    result = InfrastructureModel(_zero_timeline_solar(60)).run()
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


def test_finite_life_preset_no_terminal_value():
    """P0-3: finite-life infra presets carry no Gordon perpetuity in their EV.

    The EV must equal the PV of the explicit FCF only (no terminal value).
    """
    from asset_finance_modeler.assets.infrastructure.loader import load_preset

    for name in ("solar_pv_50mw_spain", "wind_onshore_30mw_spain", "bess_20mw_4h", "datacenter_10mw_tier3"):
        cfg = load_preset(name)
        result = InfrastructureModel(cfg).run()
        val = result.valuation
        assert val["terminal_value"] == 0.0, name
        assert val["pv_terminal"] == 0.0, name
        assert val["enterprise_value"] == pytest.approx(val["pv_explicit"]), name


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
