from __future__ import annotations

from datetime import date

import pytest

from asset_finance_modeler.assets.saas.schema import (
    HorizonConfig,
    ModelMeta,
    TaxesConfig,
    ValuationConfig,
)

# ---------------------------------------------------------------------------
# Lazy import so the test file itself doesn't fail before schema.py exists
# ---------------------------------------------------------------------------

def _schema():
    from asset_finance_modeler.assets.infrastructure import schema as s
    return s


# ---------------------------------------------------------------------------
# 1. SolarProduction defaults
# ---------------------------------------------------------------------------

def test_solar_production_defaults():
    s = _schema()
    solar = s.SolarProduction(capacity_mwp=50.0)
    assert solar.type == "solar_pv"
    assert solar.specific_yield_kwh_kwp == 1500
    assert solar.performance_ratio == pytest.approx(0.82)
    assert solar.irradiation_profile is None


# ---------------------------------------------------------------------------
# 2. BESSProduction energy capacity
# ---------------------------------------------------------------------------

def test_bess_energy_capacity():
    s = _schema()
    bess = s.BESSProduction(power_mw=100.0, duration_hours=4.0)
    assert bess.type == "bess"
    assert bess.power_mw == 100.0
    assert bess.duration_hours == pytest.approx(4.0)
    assert bess.round_trip_efficiency == pytest.approx(0.88)
    assert bess.depth_of_discharge == pytest.approx(0.90)
    # Usable energy MWh: power × duration × DoD
    usable_mwh = bess.power_mw * bess.duration_hours * bess.depth_of_discharge
    assert usable_mwh == pytest.approx(360.0)


# ---------------------------------------------------------------------------
# 3. WindProduction defaults
# ---------------------------------------------------------------------------

def test_wind_production_defaults():
    s = _schema()
    wind = s.WindProduction(capacity_mw=200.0)
    assert wind.type == "wind_onshore"
    assert wind.capacity_factor == pytest.approx(0.28)
    assert wind.availability == pytest.approx(0.97)
    assert wind.wake_losses == pytest.approx(0.05)
    assert wind.production_profile is None


# ---------------------------------------------------------------------------
# 4. PPAStream defaults
# ---------------------------------------------------------------------------

def test_ppa_stream_defaults():
    s = _schema()
    ppa = s.PPAStream(price_eur_per_unit=55.0)
    assert ppa.type == "ppa"
    assert ppa.name == "PPA"
    assert ppa.volume_fraction == pytest.approx(0.7)
    assert ppa.escalation_pct_yr == pytest.approx(0.02)
    assert ppa.tenor_years == 15


# ---------------------------------------------------------------------------
# 5. MerchantStream defaults
# ---------------------------------------------------------------------------

def test_merchant_stream_defaults():
    s = _schema()
    merchant = s.MerchantStream(base_price_eur_per_unit=60.0)
    assert merchant.type == "merchant"
    assert merchant.name == "Merchant"
    assert merchant.volume_fraction == pytest.approx(0.3)
    assert merchant.capture_ratio == pytest.approx(0.90)
    assert merchant.price_curve is None
    assert merchant.escalation_pct_yr == pytest.approx(0.01)


# ---------------------------------------------------------------------------
# 6. TimeDegradation type
# ---------------------------------------------------------------------------

def test_time_degradation_type():
    s = _schema()
    deg = s.TimeDegradation()
    assert deg.type == "time_based"
    assert deg.annual_rate == pytest.approx(0.005)


# ---------------------------------------------------------------------------
# 7. CycleDegradation EOL
# ---------------------------------------------------------------------------

def test_cycle_degradation_eol():
    s = _schema()
    deg = s.CycleDegradation()
    assert deg.type == "cycle_based"
    assert deg.eol_capacity_pct == pytest.approx(0.70)
    assert deg.capacity_fade_per_cycle == pytest.approx(0.00005)
    assert deg.calendar_fade_annual == pytest.approx(0.02)


# ---------------------------------------------------------------------------
# 8. NoDegradation type
# ---------------------------------------------------------------------------

def test_no_degradation_type():
    s = _schema()
    deg = s.NoDegradation()
    assert deg.type == "none"


# ---------------------------------------------------------------------------
# 9. InfraCapexItem defaults
# ---------------------------------------------------------------------------

def test_infra_capex_item_defaults():
    s = _schema()
    item = s.InfraCapexItem(name="Panels", amount_per_unit=500_000.0)
    assert item.unit == "MW"
    assert item.depreciation_years == 20
    assert item.depreciation_method == "straight_line"
    assert item.macrs_class is None
    assert item.residual_value_pct == 0
    assert item.quantity is None


# ---------------------------------------------------------------------------
# 10. MaintenanceEvent defaults (no extra defaults beyond required fields)
# ---------------------------------------------------------------------------

def test_maintenance_event_defaults():
    s = _schema()
    evt = s.MaintenanceEvent(name="Major overhaul", period=5, cost=200_000.0)
    assert evt.recurring_interval is None


# ---------------------------------------------------------------------------
# 11. SeniorDebtConfig defaults
# ---------------------------------------------------------------------------

def test_senior_debt_defaults():
    s = _schema()
    debt = s.SeniorDebtConfig()
    assert debt.tenor_years == 18
    assert debt.interest_rate == pytest.approx(0.045)
    assert debt.grace_period_months == 0
    assert debt.amortization == "french"
    assert debt.dscr_target == pytest.approx(1.30)
    assert debt.dscr_mode == "min"
    assert debt.auto_size is True


# ---------------------------------------------------------------------------
# 12. Full InfrastructureModelConfig with SolarProduction
# ---------------------------------------------------------------------------

def _base_meta() -> ModelMeta:
    return ModelMeta(
        name="test-solar",
        horizon=HorizonConfig(periods=240, frequency="M"),
        start_date=date(2025, 1, 1),
        initial_cash=0.0,
    )


def _solar_capex(s) -> s.CAPEXBreakdown:
    return s.CAPEXBreakdown(
        items=[
            s.InfraCapexItem(
                name="Panels",
                amount_per_unit=600_000.0,
                quantity=100.0,
            )
        ]
    )


def test_full_config_solar():
    s = _schema()
    cfg = s.InfrastructureModelConfig(
        meta=_base_meta(),
        production=s.SolarProduction(capacity_mwp=100.0),
        revenue=[s.PPAStream(price_eur_per_unit=55.0)],
        capex=_solar_capex(s),
        opex=s.InfraOPEXConfig(),
        degradation=s.TimeDegradation(),
        timeline=s.PermitsTimeline(),
        financing=s.ProjectFinanceConfig(),
        valuation=ValuationConfig(discount_rate_annual=0.08),
    )
    assert cfg.production.type == "solar_pv"
    assert cfg.production.capacity_mwp == 100.0
    assert len(cfg.revenue) == 1
    assert cfg.revenue[0].type == "ppa"
    assert isinstance(cfg.taxes, TaxesConfig)
    assert cfg.incentives.items == []


# ---------------------------------------------------------------------------
# 13. Full InfrastructureModelConfig with BESSProduction
# ---------------------------------------------------------------------------

def test_full_config_bess():
    s = _schema()
    cfg = s.InfrastructureModelConfig(
        meta=_base_meta(),
        production=s.BESSProduction(power_mw=50.0),
        revenue=[
            s.ArbitrageStream(),
            s.AncillaryStream(),
        ],
        capex=s.CAPEXBreakdown(
            items=[
                s.InfraCapexItem(
                    name="Battery packs",
                    amount_per_unit=350_000.0,
                    quantity=50.0,
                )
            ]
        ),
        opex=s.InfraOPEXConfig(
            om_fixed_eur_per_mw_yr=15_000.0,
            major_maintenance=[
                s.MaintenanceEvent(name="Stack replacement", period=10, cost=5_000_000.0)
            ],
        ),
        degradation=s.CycleDegradation(),
        timeline=s.PermitsTimeline(construction_months=18),
        financing=s.ProjectFinanceConfig(
            senior=s.SeniorDebtConfig(tenor_years=15),
        ),
        valuation=ValuationConfig(discount_rate_annual=0.09),
    )
    assert cfg.production.type == "bess"
    assert cfg.production.power_mw == 50.0
    assert len(cfg.revenue) == 2
    assert cfg.revenue[0].type == "arbitrage"
    assert cfg.revenue[1].type == "ancillary"
    assert cfg.opex.om_fixed_eur_per_mw_yr == pytest.approx(15_000.0)
    assert len(cfg.opex.major_maintenance) == 1
    assert cfg.financing.senior is not None
    assert cfg.financing.senior.tenor_years == 15
    assert cfg.degradation.type == "cycle_based"
