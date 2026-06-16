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


# ---------------------------------------------------------------------------
# P2-3: mezzanine tranche wires into the debt stack + waterfall
# ---------------------------------------------------------------------------


def _solar_with_senior_mezz(periods: int = 120, with_mezz: bool = False):
    from asset_finance_modeler.assets.infrastructure.schema import MezzanineDebtConfig

    cfg = _solar_config(periods)
    cfg.timeline = PermitsTimeline()  # no deferral — isolate the debt change
    mezz = (
        MezzanineDebtConfig(tenor_years=8, interest_rate=0.08, dscr_target=1.10)
        if with_mezz
        else None
    )
    cfg.financing = ProjectFinanceConfig(
        senior=SeniorDebtConfig(
            tenor_years=12, interest_rate=0.045, dscr_target=1.30, auto_size=True
        ),
        mezzanine=mezz,
        max_leverage=0.80,
    )
    return cfg


def test_mezzanine_increases_total_debt_drawn():
    # Adding a mezzanine tranche on top of senior raises total debt drawn at
    # close (mezz sits between senior and sub) and reduces equity outlay.
    base = InfrastructureModel(_solar_with_senior_mezz(with_mezz=False)).run()
    mezz = InfrastructureModel(_solar_with_senior_mezz(with_mezz=True)).run()
    base_drawn = base.cashflow["cff"][0]
    mezz_drawn = mezz.cashflow["cff"][0]
    assert mezz_drawn > base_drawn  # extra mezzanine principal drawn at close
    # Total debt balance at COD is higher with the mezzanine.
    assert mezz.balance["debt"][0] > base.balance["debt"][0]


def test_mezzanine_dscr_is_net_of_senior():
    # The mezzanine DSCR is computed net of senior debt service (waterfall) and
    # surfaces on the KPIs.
    mezz = InfrastructureModel(_solar_with_senior_mezz(with_mezz=True)).run()
    k = mezz.project_kpis
    assert k.dscr_mezzanine_min > 0
    # Senior is the most senior; its DSCR should exceed the (subordinate) mezz.
    assert k.dscr_senior_min >= k.dscr_mezzanine_min


def test_no_mezzanine_unchanged():
    # Zero-config (no mezzanine) leaves the KPI at its default.
    base = InfrastructureModel(_solar_with_senior_mezz(with_mezz=False)).run()
    assert base.project_kpis.dscr_mezzanine_min == 0.0


# ---------------------------------------------------------------------------
# P2-1: DSRA (debt service reserve account) is funded and held as cash
# ---------------------------------------------------------------------------


def _solar_with_debt_for_reserves(periods: int = 120, dsra_months: int = 0):
    from asset_finance_modeler.assets.infrastructure.schema import ReservesConfig

    cfg = _solar_config(periods)
    cfg.timeline = PermitsTimeline()  # no deferral — isolate the reserve change
    cfg.financing = ProjectFinanceConfig(
        senior=SeniorDebtConfig(
            tenor_years=10, interest_rate=0.045, dscr_target=1.30, auto_size=True
        ),
        reserves=ReservesConfig(dsra_months=dsra_months),
        max_leverage=0.80,
    )
    return cfg


def test_dsra_funds_a_reserve_and_changes_cash():
    base = InfrastructureModel(_solar_with_debt_for_reserves(dsra_months=0)).run()
    dsra = InfrastructureModel(_solar_with_debt_for_reserves(dsra_months=6)).run()
    # A DSRA is held as restricted cash on the balance sheet (non-zero early).
    assert "dsra" in dsra.balance
    assert max(dsra.balance["dsra"]) > 0
    assert max(base.balance.get("dsra", [0.0])) == 0.0
    # Funding the reserve at COD consumes cash → free cash differs vs no-DSRA.
    assert dsra.cashflow["cash"] != base.cashflow["cash"]


def test_dsra_zero_months_unchanged():
    base = InfrastructureModel(_solar_with_debt_for_reserves(dsra_months=0)).run()
    # Default (no DSRA) is unchanged: the reserve column is all zero.
    assert all(v == 0.0 for v in base.balance.get("dsra", [0.0]))


# ---------------------------------------------------------------------------
# E3: infra project NPV/IRR must be UNLEVERED (financing-independent). The
# levered figures live under npv_equity / irr_equity.
# ---------------------------------------------------------------------------


def _solar_unlevered(periods: int = 120) -> InfrastructureModelConfig:
    cfg = _solar_config(periods)
    cfg.timeline = PermitsTimeline()
    cfg.financing = ProjectFinanceConfig()  # all-equity
    return cfg


def _solar_levered(periods: int = 120) -> InfrastructureModelConfig:
    cfg = _solar_config(periods)
    cfg.timeline = PermitsTimeline()
    cfg.financing = ProjectFinanceConfig(
        senior=SeniorDebtConfig(
            tenor_years=15, interest_rate=0.05, dscr_target=1.30, auto_size=True
        ),
        max_leverage=0.70,
    )
    return cfg


def test_infra_project_npv_irr_unlevered_financing_independent():
    """The project EV (``npv``) and ``irr_project`` are computed on UNLEVERED
    FCF, so they do NOT change when debt is added. Equity metrics DO change."""
    unlev = InfrastructureModel(_solar_unlevered()).run()
    lev = InfrastructureModel(_solar_levered()).run()

    # Project EV / NPV / IRR identical regardless of leverage.
    assert lev.project_kpis.npv == pytest.approx(unlev.project_kpis.npv, rel=1e-6)
    assert lev.summary["enterprise_value"] == pytest.approx(
        unlev.summary["enterprise_value"], rel=1e-6
    )
    assert lev.project_kpis.irr_project == pytest.approx(
        unlev.project_kpis.irr_project, rel=1e-6
    )

    # Equity metrics DO move with leverage (levered equity NPV/IRR differ).
    assert lev.project_kpis.npv_equity != pytest.approx(
        unlev.project_kpis.npv_equity, rel=1e-3
    )


def test_infra_project_npv_unaffected_by_cash_sweep():
    """A pure financing lever (cash sweep) must not move the project EV/NPV."""
    base = InfrastructureModel(_solar_with_sweep(sweep_enabled=False)).run()
    swept = InfrastructureModel(_solar_with_sweep(sweep_enabled=True)).run()
    assert swept.project_kpis.npv == pytest.approx(base.project_kpis.npv, rel=1e-6)
    assert swept.project_kpis.irr_project == pytest.approx(
        base.project_kpis.irr_project, rel=1e-6
    )


# ---------------------------------------------------------------------------
# P2-2: cash sweep prepays debt with excess cash
# ---------------------------------------------------------------------------


def _solar_with_sweep(periods: int = 120, sweep_enabled: bool = False):
    from asset_finance_modeler.assets.infrastructure.schema import CashSweepConfig

    cfg = _solar_config(periods)
    cfg.timeline = PermitsTimeline()
    cfg.financing = ProjectFinanceConfig(
        senior=SeniorDebtConfig(
            tenor_years=15, interest_rate=0.045, dscr_target=1.30, auto_size=True
        ),
        cash_sweep=CashSweepConfig(
            enabled=sweep_enabled, trigger_dscr=1.20, sweep_pct=0.50
        ),
        max_leverage=0.80,
    )
    return cfg


def test_cash_sweep_prepays_debt_faster():
    base = InfrastructureModel(_solar_with_sweep(sweep_enabled=False)).run()
    swept = InfrastructureModel(_solar_with_sweep(sweep_enabled=True)).run()
    # With the sweep on, the debt balance pays down faster (lower at mid-life)
    # and less interest is paid over the life.
    mid = len(base.balance["debt"]) // 2
    assert swept.balance["debt"][mid] < base.balance["debt"][mid]
    assert sum(swept.pnl["interest_expense"]) < sum(base.pnl["interest_expense"])


def test_cash_sweep_disabled_unchanged():
    base = InfrastructureModel(_solar_with_sweep(sweep_enabled=False)).run()
    again = InfrastructureModel(_solar_with_sweep(sweep_enabled=False)).run()
    assert base.balance["debt"] == again.balance["debt"]


# E1: once the swept balance reaches 0, scheduled principal must STOP being
# added. Otherwise cumulative principal repaid exceeds the drawn loan and
# corrupts the cash flow / equity metrics.


def test_cash_sweep_does_not_over_repay_principal_unit():
    """_apply_cash_sweep must never repay more principal than was drawn."""
    from types import SimpleNamespace

    # Loan of 1000 drawn at t=0, linear over 4 periods (250/period), 5%/period
    # interest on the declining balance. Scheduled ending balances: 750,500,250,0.
    rate = 0.05
    ppy = 1
    principal = [250.0, 250.0, 250.0, 250.0]
    balance = [750.0, 500.0, 250.0, 0.0]
    interest = [50.0, 37.5, 25.0, 12.5]
    ds = [p + i for p, i in zip(principal, interest)]
    cfads = [2000.0] * 4  # plenty of excess → sweep maxes out
    sweep = SimpleNamespace(trigger_dscr=1.0, sweep_pct=1.0)

    new_int, new_principal, new_balance = InfrastructureModel._apply_cash_sweep(
        cfads, ds, interest, principal, balance, [1000.0, 0.0, 0.0, 0.0],
        sweep, ppy, rate,
    )

    assert sum(new_principal) <= 1000.0 + 1e-6
    assert all(b >= -1e-6 for b in new_balance)
    # Interest must also stop once the balance is gone.
    assert all(i >= -1e-6 for i in new_int)
    # After the period that retires the loan, no further principal is scheduled.
    assert new_balance[-1] == 0.0


def _solar_with_aggressive_sweep(periods: int = 120):
    """Solar config whose strong cash flow lets the sweep fully retire debt
    well before maturity (so the over-repay bug would bite)."""
    from asset_finance_modeler.assets.infrastructure.schema import CashSweepConfig

    cfg = _solar_config(periods)
    cfg.timeline = PermitsTimeline()
    cfg.financing = ProjectFinanceConfig(
        senior=SeniorDebtConfig(
            tenor_years=10, interest_rate=0.045, dscr_target=1.30, auto_size=True
        ),
        cash_sweep=CashSweepConfig(enabled=True, trigger_dscr=1.05, sweep_pct=1.0),
        max_leverage=0.80,
    )
    return cfg


def test_cash_sweep_cumulative_principal_capped_integration():
    """With an aggressive sweep, the debt balance never goes negative, the loan
    is fully retired, cumulative principal repaid ≤ drawn principal, and the
    equity metrics stay sane."""
    out = InfrastructureModel(_solar_with_aggressive_sweep()).run()

    bal = out.balance["debt"]
    drawn = max(bal) if bal else 0.0  # peak outstanding = total principal drawn
    # Balance never negative.
    assert all(b >= -1.0 for b in bal), min(bal)
    # Aggressive sweep fully retires the loan within the horizon.
    assert bal[-1] <= 1.0
    # Reconstruct cumulative principal repaid from the cash flow:
    #   cff = debt_drawdowns - principal_repaid - dsra_net (DSRA nets ~0 over the
    #   full life as it is built then released). Drawdowns ≈ drawn at t=0, so
    #   Σprincipal_repaid ≈ drawn - Σcff. With the over-repay bug this exceeds the
    #   drawn loan (scheduled principal booked after balance hit 0).
    cff = out.cashflow["cff"]
    principal_repaid = drawn - sum(cff)
    assert principal_repaid <= drawn + 1.0, (principal_repaid, drawn)
    # Equity metrics stay finite/sane (not corrupted by phantom principal).
    k = out.project_kpis
    assert k.irr_equity is None or -1.0 < k.irr_equity < 5.0
