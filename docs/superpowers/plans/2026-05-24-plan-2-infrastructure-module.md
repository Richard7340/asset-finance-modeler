# Infrastructure Module Implementation Plan (Plan 2 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the InfrastructureModel that can model any physical asset (solar PV, wind, BESS, H2, biomethane, data centers) end-to-end: from YAML preset → FinancialOutput with P&L, Cash Flow, Balance Sheet, and ProjectKPIs.

**Architecture:** Discriminated unions for ProductionConfig, RevenueStream, DegradationCurve. Shared core engines (from Plan 1). InfrastructureModel implements FinancialModel protocol. Scenario refactored to dispatch by protocol.

**Tech Stack:** Python 3.12+, Pydantic v2, pytest, YAML presets

**Depends on:** Plan 1 (Core Foundation) — completed

---

## File Structure

```
src/asset_finance_modeler/assets/infrastructure/
  __init__.py
  schema.py           → All Pydantic models (ProductionConfig, RevenueStream, etc.)
  model.py            → InfrastructureModel(implements FinancialModel protocol)
  loader.py           → load_preset() for infrastructure YAML files
  engines/
    __init__.py
    production.py     → Production engines per technology type
    revenue.py        → RevenueEngine (processes list[RevenueStream])
    opex.py           → InfraOpexEngine
    capex.py          → InfraCapexEngine
  presets/
    solar_pv_50mw_spain.yaml
    bess_20mw_4h.yaml

src/asset_finance_modeler/core/
  scenario.py         ← MODIFY: protocol-based dispatch

tests/unit/
  test_infra_schema.py
  test_infra_production.py
  test_infra_revenue.py
  test_infra_opex.py
  test_infra_capex.py
  test_infra_model.py
  test_scenario_protocol.py
```

---

### Task 1: Infrastructure Schema — All Pydantic Models

**Files:**
- Create: `src/asset_finance_modeler/assets/infrastructure/__init__.py`
- Create: `src/asset_finance_modeler/assets/infrastructure/schema.py`
- Create: `src/asset_finance_modeler/assets/infrastructure/engines/__init__.py`
- Test: `tests/unit/test_infra_schema.py`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p src/asset_finance_modeler/assets/infrastructure/engines
mkdir -p src/asset_finance_modeler/assets/infrastructure/presets
touch src/asset_finance_modeler/assets/infrastructure/__init__.py
touch src/asset_finance_modeler/assets/infrastructure/engines/__init__.py
```

- [ ] **Step 2: Write schema tests**

```python
# tests/unit/test_infra_schema.py
import pytest
from pydantic import ValidationError

from asset_finance_modeler.assets.infrastructure.schema import (
    BESSProduction,
    CAPEXBreakdown,
    CashSweepConfig,
    CycleDegradation,
    DataCenterProduction,
    EquityConfig,
    H2Production,
    IncentiveItem,
    IncentivesConfig,
    InfraCapexItem,
    InfraOPEXConfig,
    InfrastructureModelConfig,
    MaintenanceEvent,
    MerchantStream,
    NoDegradation,
    PermitsTimeline,
    PPAStream,
    ProjectFinanceConfig,
    ReservesConfig,
    SeniorDebtConfig,
    SolarProduction,
    TimeDegradation,
    WindProduction,
)
from asset_finance_modeler.assets.saas.schema import (
    HorizonConfig,
    ModelMeta,
    TaxesConfig,
    ValuationConfig,
)
from datetime import date


def test_solar_production_defaults():
    sp = SolarProduction(capacity_mwp=50)
    assert sp.type == "solar_pv"
    assert sp.specific_yield_kwh_kwp == 1500
    assert sp.performance_ratio == 0.82


def test_bess_production_energy():
    bp = BESSProduction(power_mw=20, duration_hours=4)
    assert bp.type == "bess"
    assert bp.round_trip_efficiency == 0.88


def test_wind_production():
    wp = WindProduction(capacity_mw=30)
    assert wp.type == "wind_onshore"
    assert wp.capacity_factor == 0.28


def test_ppa_stream():
    ppa = PPAStream(price_eur_per_unit=45.0, volume_fraction=0.7)
    assert ppa.type == "ppa"
    assert ppa.escalation_pct_yr == 0.02


def test_merchant_stream():
    m = MerchantStream(base_price_eur_per_unit=50.0)
    assert m.type == "merchant"
    assert m.capture_ratio == 0.90


def test_time_degradation():
    td = TimeDegradation(annual_rate=0.005)
    assert td.type == "time_based"


def test_cycle_degradation():
    cd = CycleDegradation(capacity_fade_per_cycle=0.00005)
    assert cd.type == "cycle_based"
    assert cd.eol_capacity_pct == 0.70


def test_no_degradation():
    nd = NoDegradation()
    assert nd.type == "none"


def test_capex_item():
    item = InfraCapexItem(
        name="Panels+BOS", amount_per_unit=0.45, unit="Wp",
        depreciation_years=25, depreciation_method="macrs", macrs_class=5,
    )
    assert item.residual_value_pct == 0


def test_maintenance_event():
    me = MaintenanceEvent(name="Inverter swap", period=144, cost=500_000)
    assert me.recurring_interval is None


def test_senior_debt_config():
    sd = SeniorDebtConfig()
    assert sd.tenor_years == 18
    assert sd.dscr_target == 1.30
    assert sd.auto_size is True


def test_full_config_solar():
    cfg = InfrastructureModelConfig(
        meta=ModelMeta(
            name="solar-test", horizon=HorizonConfig(periods=240, frequency="M"),
            start_date=date(2026, 1, 1), initial_cash=0,
        ),
        production=SolarProduction(capacity_mwp=50),
        revenue=[PPAStream(price_eur_per_unit=45.0, volume_fraction=0.7)],
        capex=CAPEXBreakdown(items=[
            InfraCapexItem(name="EPC", amount_per_unit=0.45, unit="Wp"),
        ]),
        opex=InfraOPEXConfig(om_fixed_eur_per_mw_yr=12_000),
        degradation=TimeDegradation(annual_rate=0.005),
        timeline=PermitsTimeline(),
        financing=ProjectFinanceConfig(),
        taxes=TaxesConfig(),
        valuation=ValuationConfig(discount_rate_annual=0.07),
    )
    assert cfg.production.type == "solar_pv"
    assert len(cfg.revenue) == 1


def test_full_config_bess():
    cfg = InfrastructureModelConfig(
        meta=ModelMeta(
            name="bess-test", horizon=HorizonConfig(periods=180, frequency="M"),
            start_date=date(2026, 1, 1), initial_cash=0,
        ),
        production=BESSProduction(power_mw=20, duration_hours=4),
        revenue=[
            PPAStream(name="Arbitrage-proxy", price_eur_per_unit=40.0, volume_fraction=1.0),
        ],
        capex=CAPEXBreakdown(items=[
            InfraCapexItem(name="Battery+BOS", amount_per_unit=250, unit="kWh"),
        ]),
        opex=InfraOPEXConfig(om_fixed_eur_per_mw_yr=8_000),
        degradation=CycleDegradation(capacity_fade_per_cycle=0.00005),
        timeline=PermitsTimeline(construction_months=6),
        financing=ProjectFinanceConfig(),
        taxes=TaxesConfig(),
        valuation=ValuationConfig(discount_rate_annual=0.08),
    )
    assert cfg.production.type == "bess"
```

- [ ] **Step 3: Write schema.py**

```python
# src/asset_finance_modeler/assets/infrastructure/schema.py
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from asset_finance_modeler.assets.saas.schema import (
    ExternalDataConfig,
    HorizonConfig,
    ModelMeta,
    TaxesConfig,
    ValuationConfig,
)


# === Production Config (discriminated union) ===

class SolarProduction(BaseModel):
    type: Literal["solar_pv"] = "solar_pv"
    capacity_mwp: float
    specific_yield_kwh_kwp: float = 1500
    performance_ratio: float = 0.82
    irradiation_profile: list[float] | None = None

class WindProduction(BaseModel):
    type: Literal["wind_onshore"] = "wind_onshore"
    capacity_mw: float
    capacity_factor: float = 0.28
    availability: float = 0.97
    wake_losses: float = 0.05
    production_profile: list[float] | None = None

class BESSProduction(BaseModel):
    type: Literal["bess"] = "bess"
    power_mw: float
    duration_hours: float = 4.0
    round_trip_efficiency: float = 0.88
    depth_of_discharge: float = 0.90
    cycles_per_day: float = 1.5
    price_profile: list[float] | None = None

class H2Production(BaseModel):
    type: Literal["hydrogen"] = "hydrogen"
    electrolyzer_mw: float
    efficiency_kwh_per_kg: float = 55
    stack_lifetime_hours: int = 80000
    availability: float = 0.95
    electricity_source: Literal["grid", "dedicated_re", "hybrid"] = "dedicated_re"
    electricity_cost_eur_mwh: float = 40.0

class BiomethaneProduction(BaseModel):
    type: Literal["biomethane"] = "biomethane"
    capacity_nm3_h: float
    biogas_yield_nm3_ton: float = 150
    methane_content: float = 0.55
    upgrading_efficiency: float = 0.98
    operating_hours_yr: int = 8000

class DataCenterProduction(BaseModel):
    type: Literal["data_center"] = "data_center"
    it_capacity_mw: float
    pue: float = 1.3
    rack_density_kw: float = 10
    redundancy: Literal["N", "N+1", "2N", "2N+1"] = "N+1"
    tier: Literal[1, 2, 3, 4] = 3

class GenericProduction(BaseModel):
    type: Literal["generic"] = "generic"
    units: float
    output_per_unit_per_period: float
    output_unit: str = "MWh"

ProductionConfig = Annotated[
    SolarProduction | WindProduction | BESSProduction | H2Production
    | BiomethaneProduction | DataCenterProduction | GenericProduction,
    Field(discriminator="type"),
]


# === Revenue Streams (composable list) ===

class PPAStream(BaseModel):
    type: Literal["ppa"] = "ppa"
    name: str = "PPA"
    price_eur_per_unit: float
    volume_fraction: float = 0.7
    escalation_pct_yr: float = 0.02
    tenor_years: int = 15

class MerchantStream(BaseModel):
    type: Literal["merchant"] = "merchant"
    name: str = "Merchant"
    base_price_eur_per_unit: float
    volume_fraction: float = 0.3
    capture_ratio: float = 0.90
    price_curve: list[float] | None = None
    escalation_pct_yr: float = 0.01

class ArbitrageStream(BaseModel):
    type: Literal["arbitrage"] = "arbitrage"
    name: str = "Arbitrage"
    avg_spread_eur_mwh: float = 40
    cycles_per_day: float = 1.5
    spread_capture_ratio: float = 0.75

class AncillaryStream(BaseModel):
    type: Literal["ancillary"] = "ancillary"
    name: str = "Ancillary Services"
    fcr_eur_mw_yr: float = 0
    afrr_eur_mw_yr: float = 0
    mfrr_eur_mw_yr: float = 0

class CapacityStream(BaseModel):
    type: Literal["capacity"] = "capacity"
    name: str = "Capacity Payment"
    eur_per_mw_yr: float

class OfftakeStream(BaseModel):
    type: Literal["offtake"] = "offtake"
    name: str = "Offtake"
    price_eur_per_unit: float
    volume_fraction: float = 1.0
    escalation_pct_yr: float = 0.02
    tenor_years: int = 15

class CertificateStream(BaseModel):
    type: Literal["certificate"] = "certificate"
    name: str = "Green Certificates"
    price_eur_per_unit: float
    eligible_fraction: float = 1.0
    certificate_type: Literal["go", "rec", "rfnbo", "carbon_credit"] = "go"

class RentalStream(BaseModel):
    type: Literal["rental"] = "rental"
    name: str = "Rental"
    price_per_unit_period: float
    occupancy_rate: float = 0.95
    escalation_pct_yr: float = 0.02

class SLAStream(BaseModel):
    type: Literal["sla"] = "sla"
    name: str = "SLA Hosting"
    price_per_mw_month: float
    uptime_target: float = 0.999

RevenueStream = Annotated[
    PPAStream | MerchantStream | ArbitrageStream | AncillaryStream
    | CapacityStream | OfftakeStream | CertificateStream
    | RentalStream | SLAStream,
    Field(discriminator="type"),
]


# === Degradation (discriminated union) ===

class TimeDegradation(BaseModel):
    type: Literal["time_based"] = "time_based"
    annual_rate: float = 0.005

class CycleDegradation(BaseModel):
    type: Literal["cycle_based"] = "cycle_based"
    capacity_fade_per_cycle: float = 0.00005
    calendar_fade_annual: float = 0.02
    eol_capacity_pct: float = 0.70

class UsageDegradation(BaseModel):
    type: Literal["usage_based"] = "usage_based"
    efficiency_loss_per_1000h: float = 0.001
    stack_replacement_hours: int = 80000

class NoDegradation(BaseModel):
    type: Literal["none"] = "none"

DegradationCurve = Annotated[
    TimeDegradation | CycleDegradation | UsageDegradation | NoDegradation,
    Field(discriminator="type"),
]


# === CAPEX ===

class InfraCapexItem(BaseModel):
    name: str
    amount_per_unit: float
    unit: str = "MW"
    quantity: float | None = None
    depreciation_years: int = 20
    depreciation_method: Literal[
        "straight_line", "declining_balance", "macrs", "soyd", "custom",
    ] = "straight_line"
    macrs_class: int | None = None
    residual_value_pct: float = 0

class CAPEXBreakdown(BaseModel):
    items: list[InfraCapexItem]
    contingency_pct: float = 0.10
    development_cost: float = 0
    grid_connection_cost: float = 0
    land_acquisition: float = 0


# === OPEX ===

class MaintenanceEvent(BaseModel):
    name: str
    period: int
    cost: float
    recurring_interval: int | None = None

class InfraOPEXConfig(BaseModel):
    om_fixed_eur_per_mw_yr: float = 0
    om_variable_eur_per_mwh: float = 0
    insurance_pct_capex: float = 0.005
    land_lease_eur_yr: float = 0
    management_fee_eur_yr: float = 0
    other_fixed_eur_yr: float = 0
    major_maintenance: list[MaintenanceEvent] = Field(default_factory=list)
    opex_escalation_pct_yr: float = 0.02


# === Timeline ===

class PermitsTimeline(BaseModel):
    development_months: int = 12
    permitting_months: int = 18
    construction_months: int = 12
    grid_connection_months: int = 6
    construction_drawdown_schedule: list[float] | None = None


# === Project Finance ===

class SeniorDebtConfig(BaseModel):
    tenor_years: int = 18
    interest_rate: float = 0.045
    grace_period_months: int = 0
    amortization: Literal["french", "bullet", "linear"] = "french"
    dscr_target: float = 1.30
    dscr_mode: Literal["min", "avg"] = "min"
    auto_size: bool = True

class MezzanineDebtConfig(BaseModel):
    tenor_years: int = 12
    interest_rate: float = 0.08
    dscr_target: float = 1.10
    pik_interest: bool = False

class EquityConfig(BaseModel):
    target_irr: float = 0.12
    distribution_lock_years: int = 0

class ReservesConfig(BaseModel):
    dsra_months: int = 6
    mra_eur: float = 0
    working_capital_eur: float = 0

class CashSweepConfig(BaseModel):
    enabled: bool = False
    trigger_dscr: float = 1.40
    sweep_pct: float = 0.50

class ProjectFinanceConfig(BaseModel):
    senior: SeniorDebtConfig | None = None
    mezzanine: MezzanineDebtConfig | None = None
    equity: EquityConfig = Field(default_factory=EquityConfig)
    reserves: ReservesConfig = Field(default_factory=ReservesConfig)
    cash_sweep: CashSweepConfig = Field(default_factory=CashSweepConfig)
    construction_facility: bool = True
    max_leverage: float = 0.80


# === Incentives ===

class IncentiveItem(BaseModel):
    name: str
    type: Literal[
        "tax_credit", "production_subsidy", "capex_grant",
        "feed_in_tariff", "carbon_credit", "rfnbo_premium",
    ]
    value: float
    duration_years: int | None = None
    start_year: int = 0

class IncentivesConfig(BaseModel):
    items: list[IncentiveItem] = Field(default_factory=list)


# === Root Config ===

class InfrastructureModelConfig(BaseModel):
    meta: ModelMeta
    production: ProductionConfig
    revenue: list[RevenueStream]
    capex: CAPEXBreakdown
    opex: InfraOPEXConfig
    degradation: DegradationCurve
    timeline: PermitsTimeline
    financing: ProjectFinanceConfig
    incentives: IncentivesConfig = Field(default_factory=IncentivesConfig)
    taxes: TaxesConfig = Field(default_factory=TaxesConfig)
    valuation: ValuationConfig
    external_data: ExternalDataConfig = Field(default_factory=ExternalDataConfig)
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/unit/test_infra_schema.py -v`
Expected: All passed

- [ ] **Step 5: Commit**

```bash
git add src/asset_finance_modeler/assets/infrastructure/ tests/unit/test_infra_schema.py
git commit -m "feat(infra): add InfrastructureModelConfig schema — 3 discriminated unions, 7 tech types"
```

---

### Task 2: Production Engines

**Files:**
- Create: `src/asset_finance_modeler/assets/infrastructure/engines/production.py`
- Test: `tests/unit/test_infra_production.py`

Each production engine takes its config + degradation multipliers + number of periods → returns `dict` with `production_mwh` (or equivalent unit) per period, plus `capacity_mw` for OPEX/revenue calculations.

- [ ] **Step 1: Write tests**

```python
# tests/unit/test_infra_production.py
import pytest

from asset_finance_modeler.assets.infrastructure.engines.production import compute_production
from asset_finance_modeler.assets.infrastructure.schema import (
    BESSProduction,
    DataCenterProduction,
    GenericProduction,
    H2Production,
    SolarProduction,
    WindProduction,
)


def test_solar_production_annual():
    cfg = SolarProduction(capacity_mwp=50)
    deg = [1.0] * 240
    out = compute_production(cfg, deg, periods=240, periods_per_year=12)
    monthly_mwh = cfg.capacity_mwp * 1000 * cfg.specific_yield_kwh_kwp * cfg.performance_ratio / 1000 / 12
    assert out["production_mwh"][0] == pytest.approx(monthly_mwh, rel=0.01)
    assert out["capacity_mw"] == pytest.approx(50)
    assert len(out["production_mwh"]) == 240


def test_solar_production_with_degradation():
    cfg = SolarProduction(capacity_mwp=10)
    deg = [1.0] * 12 + [0.995] * 12
    out = compute_production(cfg, deg, periods=24, periods_per_year=12)
    assert out["production_mwh"][12] < out["production_mwh"][0]


def test_wind_production():
    cfg = WindProduction(capacity_mw=30)
    deg = [1.0] * 120
    out = compute_production(cfg, deg, periods=120, periods_per_year=12)
    hours_per_month = 8760 / 12
    expected = cfg.capacity_mw * cfg.capacity_factor * cfg.availability * (1 - cfg.wake_losses) * hours_per_month
    assert out["production_mwh"][0] == pytest.approx(expected, rel=0.01)
    assert out["capacity_mw"] == 30


def test_bess_production():
    cfg = BESSProduction(power_mw=20, duration_hours=4, cycles_per_day=1.5)
    deg = [1.0] * 120
    out = compute_production(cfg, deg, periods=120, periods_per_year=12)
    energy_capacity = cfg.power_mw * cfg.duration_hours
    daily_discharge = energy_capacity * cfg.depth_of_discharge * cfg.round_trip_efficiency * cfg.cycles_per_day
    monthly = daily_discharge * 30
    assert out["production_mwh"][0] == pytest.approx(monthly, rel=0.05)
    assert out["capacity_mw"] == 20
    assert "energy_capacity_mwh" in out


def test_h2_production():
    cfg = H2Production(electrolyzer_mw=10, efficiency_kwh_per_kg=55, availability=0.95)
    deg = [1.0] * 120
    out = compute_production(cfg, deg, periods=120, periods_per_year=12)
    assert "production_kg" in out
    assert out["production_kg"][0] > 0
    assert out["capacity_mw"] == 10


def test_datacenter_production():
    cfg = DataCenterProduction(it_capacity_mw=10, pue=1.3)
    deg = [1.0] * 60
    out = compute_production(cfg, deg, periods=60, periods_per_year=12)
    assert "capacity_mw_it" in out
    assert out["capacity_mw"] == pytest.approx(10 * 1.3)


def test_generic_production():
    cfg = GenericProduction(units=100, output_per_unit_per_period=50)
    deg = [1.0] * 60
    out = compute_production(cfg, deg, periods=60, periods_per_year=12)
    assert out["production_mwh"][0] == pytest.approx(5000)
```

- [ ] **Step 2: Write production.py**

```python
# src/asset_finance_modeler/assets/infrastructure/engines/production.py
from __future__ import annotations

from typing import Any

from asset_finance_modeler.assets.infrastructure.schema import (
    BESSProduction,
    BiomethaneProduction,
    DataCenterProduction,
    GenericProduction,
    H2Production,
    SolarProduction,
    WindProduction,
)

_HOURS_PER_MONTH = 8760 / 12
_DAYS_PER_MONTH = 30


def compute_production(
    config: Any,
    degradation: list[float],
    periods: int,
    periods_per_year: int,
) -> dict[str, Any]:
    if isinstance(config, SolarProduction):
        return _solar(config, degradation, periods, periods_per_year)
    if isinstance(config, WindProduction):
        return _wind(config, degradation, periods, periods_per_year)
    if isinstance(config, BESSProduction):
        return _bess(config, degradation, periods, periods_per_year)
    if isinstance(config, H2Production):
        return _h2(config, degradation, periods, periods_per_year)
    if isinstance(config, BiomethaneProduction):
        return _biomethane(config, degradation, periods, periods_per_year)
    if isinstance(config, DataCenterProduction):
        return _datacenter(config, degradation, periods, periods_per_year)
    if isinstance(config, GenericProduction):
        return _generic(config, degradation, periods, periods_per_year)
    raise ValueError(f"Unknown production config type: {type(config)}")


def _solar(
    cfg: SolarProduction, deg: list[float], periods: int, ppy: int,
) -> dict[str, Any]:
    annual_mwh = cfg.capacity_mwp * 1000 * cfg.specific_yield_kwh_kwp * cfg.performance_ratio / 1000
    monthly_mwh = annual_mwh / ppy
    return {
        "production_mwh": [monthly_mwh * deg[t] for t in range(periods)],
        "capacity_mw": cfg.capacity_mwp,
    }


def _wind(
    cfg: WindProduction, deg: list[float], periods: int, ppy: int,
) -> dict[str, Any]:
    hours = 8760 / ppy
    monthly_mwh = cfg.capacity_mw * cfg.capacity_factor * cfg.availability * (1 - cfg.wake_losses) * hours
    return {
        "production_mwh": [monthly_mwh * deg[t] for t in range(periods)],
        "capacity_mw": cfg.capacity_mw,
    }


def _bess(
    cfg: BESSProduction, deg: list[float], periods: int, ppy: int,
) -> dict[str, Any]:
    energy_cap = cfg.power_mw * cfg.duration_hours
    daily_discharge = energy_cap * cfg.depth_of_discharge * cfg.round_trip_efficiency * cfg.cycles_per_day
    days = 365 / ppy
    return {
        "production_mwh": [daily_discharge * days * deg[t] for t in range(periods)],
        "capacity_mw": cfg.power_mw,
        "energy_capacity_mwh": energy_cap,
    }


def _h2(
    cfg: H2Production, deg: list[float], periods: int, ppy: int,
) -> dict[str, Any]:
    hours = 8760 / ppy
    mwh_input = cfg.electrolyzer_mw * cfg.availability * hours
    kg_per_period = mwh_input * 1000 / cfg.efficiency_kwh_per_kg
    return {
        "production_kg": [kg_per_period * deg[t] for t in range(periods)],
        "production_mwh": [mwh_input * deg[t] for t in range(periods)],
        "capacity_mw": cfg.electrolyzer_mw,
    }


def _biomethane(
    cfg: BiomethaneProduction, deg: list[float], periods: int, ppy: int,
) -> dict[str, Any]:
    hours = cfg.operating_hours_yr / ppy
    nm3_per_period = cfg.capacity_nm3_h * hours * cfg.methane_content * cfg.upgrading_efficiency
    mwh_per_period = nm3_per_period * 0.01  # ~10 kWh/Nm3 biomethane
    return {
        "production_nm3": [nm3_per_period * deg[t] for t in range(periods)],
        "production_mwh": [mwh_per_period * deg[t] for t in range(periods)],
        "capacity_mw": cfg.capacity_nm3_h * 0.01,
    }


def _datacenter(
    cfg: DataCenterProduction, deg: list[float], periods: int, ppy: int,
) -> dict[str, Any]:
    total_mw = cfg.it_capacity_mw * cfg.pue
    racks = cfg.it_capacity_mw * 1000 / cfg.rack_density_kw
    return {
        "production_mwh": [0.0] * periods,
        "capacity_mw": total_mw,
        "capacity_mw_it": cfg.it_capacity_mw,
        "rack_count": racks,
    }


def _generic(
    cfg: GenericProduction, deg: list[float], periods: int, ppy: int,
) -> dict[str, Any]:
    output = cfg.units * cfg.output_per_unit_per_period
    return {
        "production_mwh": [output * deg[t] for t in range(periods)],
        "capacity_mw": cfg.units,
    }
```

- [ ] **Step 3: Run tests + commit**

```bash
.venv/bin/pytest tests/unit/test_infra_production.py -v
git add src/asset_finance_modeler/assets/infrastructure/engines/production.py tests/unit/test_infra_production.py
git commit -m "feat(infra): add production engines — solar, wind, BESS, H2, biomethane, datacenter, generic"
```

---

### Task 3: Revenue, OPEX, and CAPEX Engines

**Files:**
- Create: `src/asset_finance_modeler/assets/infrastructure/engines/revenue.py`
- Create: `src/asset_finance_modeler/assets/infrastructure/engines/opex.py`
- Create: `src/asset_finance_modeler/assets/infrastructure/engines/capex.py`
- Test: `tests/unit/test_infra_revenue.py`
- Test: `tests/unit/test_infra_opex.py`
- Test: `tests/unit/test_infra_capex.py`

Revenue engine processes `list[RevenueStream]` + production output → revenue breakdown per period.
OPEX engine computes fixed O&M, insurance, land, maintenance events.
CAPEX engine resolves quantity from production config, computes total CAPEX + depreciation.

Tests and implementations follow the same pattern as Tasks 1-2. Key formulas:

**Revenue:**
- PPA: `production_mwh[t] * volume_fraction * price * (1 + escalation)^(t/ppy)`
- Merchant: `production_mwh[t] * volume_fraction * base_price * capture_ratio * (1 + esc)^(t/ppy)`
- Arbitrage: `energy_cap * dod * rte * cycles * days * spread * capture`
- Ancillary: `(fcr + afrr + mfrr) * capacity_mw / ppy`
- Capacity: `eur_per_mw_yr * capacity_mw / ppy`
- SLA: `price_per_mw_month * capacity_mw_it`

**OPEX:**
- Fixed O&M: `om_fixed * capacity_mw / ppy * (1 + esc)^(t/ppy)`
- Variable O&M: `om_variable * production_mwh[t]`
- Insurance: `insurance_pct * total_capex / ppy`
- Maintenance events at scheduled periods

**CAPEX:**
- For each item: `amount_per_unit * quantity` where quantity defaults from production capacity
- Total = sum(items) * (1 + contingency) + development + grid + land
- Depreciation via `core.depreciation.compute_depreciation()`

- [ ] **Steps: Write tests → implement → verify → commit (3 commits, one per engine)**

Commit messages:
- `feat(infra): add RevenueEngine — PPA, merchant, arbitrage, ancillary, capacity, SLA`
- `feat(infra): add InfraOpexEngine — fixed/variable O&M, insurance, maintenance events`
- `feat(infra): add InfraCapexEngine — technology CAPEX with depreciation dispatch`

---

### Task 4: InfrastructureModel + Loader + Presets

**Files:**
- Create: `src/asset_finance_modeler/assets/infrastructure/model.py`
- Create: `src/asset_finance_modeler/assets/infrastructure/loader.py`
- Create: `src/asset_finance_modeler/assets/infrastructure/presets/solar_pv_50mw_spain.yaml`
- Create: `src/asset_finance_modeler/assets/infrastructure/presets/bess_20mw_4h.yaml`
- Test: `tests/unit/test_infra_model.py`

The `InfrastructureModel` implements the `FinancialModel` protocol. Its `run()` method orchestrates all engines in order and returns `FinancialOutput` with `ProjectKPIs`.

The loader reads YAML presets and validates them against `InfrastructureModelConfig`.

- [ ] **Step 1: Write model test**

```python
# tests/unit/test_infra_model.py
from datetime import date

import pytest

from asset_finance_modeler.assets.infrastructure.model import InfrastructureModel
from asset_finance_modeler.assets.infrastructure.schema import (
    CAPEXBreakdown,
    InfraCapexItem,
    InfraOPEXConfig,
    InfrastructureModelConfig,
    PermitsTimeline,
    PPAStream,
    ProjectFinanceConfig,
    SolarProduction,
    TimeDegradation,
)
from asset_finance_modeler.assets.saas.schema import (
    HorizonConfig,
    ModelMeta,
    TaxesConfig,
    ValuationConfig,
)
from asset_finance_modeler.core.protocols import FinancialModel, FinancialOutput


def _solar_config(periods: int = 240) -> InfrastructureModelConfig:
    return InfrastructureModelConfig(
        meta=ModelMeta(
            name="solar-test",
            horizon=HorizonConfig(periods=periods, frequency="M"),
            start_date=date(2026, 1, 1),
            initial_cash=0,
        ),
        production=SolarProduction(capacity_mwp=50),
        revenue=[
            PPAStream(price_eur_per_unit=45.0, volume_fraction=0.7),
            PPAStream(name="Merchant-proxy", price_eur_per_unit=50.0, volume_fraction=0.3),
        ],
        capex=CAPEXBreakdown(items=[
            InfraCapexItem(name="EPC", amount_per_unit=0.45, unit="Wp", quantity=50_000_000),
        ]),
        opex=InfraOPEXConfig(om_fixed_eur_per_mw_yr=12_000, insurance_pct_capex=0.005),
        degradation=TimeDegradation(annual_rate=0.005),
        timeline=PermitsTimeline(construction_months=12),
        financing=ProjectFinanceConfig(),
        taxes=TaxesConfig(),
        valuation=ValuationConfig(discount_rate_annual=0.07),
    )


def test_infra_model_implements_protocol():
    model = InfrastructureModel(_solar_config())
    assert isinstance(model, FinancialModel)


def test_infra_model_run_returns_financial_output():
    model = InfrastructureModel(_solar_config(periods=120))
    result = model.run()
    assert isinstance(result, FinancialOutput)
    assert len(result.pnl["revenue"]) == 120
    assert len(result.cashflow["cash"]) == 120
    assert len(result.balance["total_assets"]) == 120
    assert "enterprise_value" in result.valuation


def test_infra_model_revenue_positive():
    model = InfrastructureModel(_solar_config(periods=60))
    result = model.run()
    assert result.pnl["revenue"][0] > 0


def test_infra_model_has_project_kpis():
    model = InfrastructureModel(_solar_config(periods=120))
    result = model.run()
    assert result.project_kpis is not None
    assert result.project_kpis.lcoe is not None
    assert result.project_kpis.lcoe > 0
    assert result.project_kpis.irr_project != 0


def test_infra_model_summary():
    model = InfrastructureModel(_solar_config(periods=60))
    result = model.run()
    assert "revenue_y1" in result.summary or "total_capex" in result.summary
```

- [ ] **Step 2: Write model.py, loader.py, presets**

The model orchestrates: degradation → production → revenue → CAPEX → OPEX → incentives → P&L → debt → cash flow → balance → debt metrics → valuation → KPIs.

- [ ] **Step 3: Run tests + commit**

```bash
git commit -m "feat(infra): add InfrastructureModel + loader + solar/BESS presets"
```

---

### Task 5: Scenario Protocol Refactor

**Files:**
- Modify: `src/asset_finance_modeler/core/scenario.py`
- Modify: `src/asset_finance_modeler/mcp_server/tools/discover.py`
- Modify: `src/asset_finance_modeler/mcp_server/tools/execute.py`
- Test: `tests/unit/test_scenario_protocol.py`

Refactor `scenario.py` so `run_scenario()` dispatches by asset type using the model registry pattern. Update discover.py to list infrastructure models. Update execute.py to use the new dispatcher.

- [ ] **Step 1: Write test**

```python
# tests/unit/test_scenario_protocol.py
from asset_finance_modeler.core.scenario import run_scenario, Scenario, new_scenario_id


def test_run_scenario_saas():
    """Existing SaaS scenarios still work."""
    scenario = Scenario(
        id=new_scenario_id(), name="test-saas",
        base_model="gestnova", overrides={},
    )
    results = run_scenario(scenario)
    assert "revenue" in results.pnl


def test_run_scenario_solar():
    scenario = Scenario(
        id=new_scenario_id(), name="test-solar",
        base_model="solar_pv_50mw_spain", overrides={},
    )
    results = run_scenario(scenario)
    assert "revenue" in results.pnl
    assert results.project_kpis is not None
```

- [ ] **Step 2: Refactor scenario.py**

Add a model registry that maps preset names to their model class + loader:

```python
_MODEL_REGISTRY = {
    "gestnova": ("saas", load_saas_preset),
    "solar_pv_50mw_spain": ("infrastructure", load_infra_preset),
    "bess_20mw_4h": ("infrastructure", load_infra_preset),
}

def run_scenario(scenario: Scenario) -> FinancialOutput:
    asset_type, loader = _MODEL_REGISTRY[scenario.base_model]
    base_cfg = loader(scenario.base_model)
    resolved = apply_overrides(base_cfg.model_dump(mode="json"), scenario.overrides)
    if asset_type == "saas":
        model = SaasModel(SaasModelConfig.model_validate(resolved))
    else:
        model = InfrastructureModel(InfrastructureModelConfig.model_validate(resolved))
    return model.run()
```

- [ ] **Step 3: Run ALL tests + commit**

```bash
.venv/bin/pytest tests/ --tb=short
git commit -m "refactor: scenario.py dispatches by model registry, supports infra + saas"
```

---

## Final Verification

```bash
.venv/bin/pytest tests/ -v --tb=short
.venv/bin/ruff check src/
```

Expected: All tests pass, no lint errors.

**Total new files:** ~12 (schema, 4 engines, model, loader, 2 presets, 6 test files)
**Total commits:** ~7
