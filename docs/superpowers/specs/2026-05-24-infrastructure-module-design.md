# Infrastructure Module — Design Spec

**Date**: 2026-05-24
**Status**: Approved
**Scope**: Add multi-asset infrastructure modeling to asset-finance-modeler

## Overview

Extend asset-finance-modeler (currently SaaS-only, 30 MCP tools) with a unified infrastructure model that can evaluate any physical asset: renewable energy (solar PV, wind, BESS, hydrogen, biomethane), industrial (data centers, factories), and generic infrastructure. The same financial engine (P&L, Cash Flow, Balance Sheet, DCF) serves all asset types — only the production/revenue layer varies by technology.

**Approach**: Unified model with pluggable engines (Enfoque B). One `InfrastructureModel` class with discriminated unions for technology-specific config. Shared core for everything asset-agnostic.

**Integration**: Standalone project first. Gestnova integration via existing `financial-analysis` skill (just expose new tools).

**Output**: HTML artifacts (Chart.js dashboards) generated on-demand. Full dashboard + individual charts when the agent deems it useful.

**UX**: Complete wizard flow — agent always asks all configuration questions step by step. When user doesn't know a value, agent searches benchmarks and proposes.

## Architecture

### Protocol-Based Design

```python
# core/protocols.py
@runtime_checkable
class FinancialModel(Protocol):
    config_schema: type[BaseModel]
    def run(self) -> FinancialOutput: ...
```

Both `SaasModel` and `InfrastructureModel` implement this protocol. `scenario.py` operates on the protocol — never knows what asset type is underneath. No dispatcher, no if/else by type.

### Directory Structure

```
core/                              # Asset-agnostic (shared by SaaS + Infrastructure)
  protocols.py          → NEW: FinancialModel protocol + FinancialOutput
  statements.py         ← existing (P&L, CF, BS) — extend with DTA/DTL tracking
  valuation.py          ← existing — extend with IRR equity/project, LCOE/LCOS
  scenario.py           ← refactor: operate on FinancialModel protocol
  financing.py          → NEW: ProjectFinanceEngine (senior, mezz, equity, 
                          cash sweep, DSCR, DSRA, MRA, debt sizing solver)
                          + DebtEngine refactored from assets/saas/engines.py
  incentives.py         → NEW: IncentiveFramework (programs as config, not code)
  depreciation.py       → NEW: accelerated methods (MACRS, declining balance, SOYD)
  degradation.py        → NEW: DegradationEngine (time/cycle/usage → multiplier series)
  drivers.py            ← existing (growth curves, amortization) — already agnostic
  portfolio.py          → NEW: PortfolioModel (list[Asset] → combined CF)

assets/
  saas/                 ← existing — refactor DebtEngine out, implement Protocol
  infrastructure/       → NEW
    schema.py           → InfrastructureModelConfig (all Pydantic schemas)
    model.py            → InfrastructureModel (implements FinancialModel protocol)
    engines/
      production.py     → dispatch by type: solar, wind, bess, h2, biomethane,
                          datacenter, generic
                          (monthly with internal hourly profiles where applicable)
      revenue.py        → RevenueEngine (processes list[RevenueStream])
      opex.py           → InfraOpexEngine (O&M + insurance + land + maintenance events)
      capex.py          → InfraCapexEngine (technology CAPEX with lifecycle)
    presets/
      solar_pv_50mw_spain.yaml
      wind_onshore_30mw_spain.yaml
      bess_20mw_4h.yaml
      hydrogen_10mw_pem.yaml
      biomethane_500nm3h.yaml
      datacenter_10mw_tier3.yaml
    wizard/
      config.py         → WizardConfig per technology (order, dependencies, help text)
                          auto-reads Field metadata from schema, adds UX layer

intelligence/
  benchmarks/           → NEW
    engine.py           → BenchmarkLookup (IRENA, Lazard, BloombergNEF, ENTSO-E)
    sources.py          → Source definitions with confidence levels

mcp_server/tools/
  discover.py           ← extend: list_models includes infrastructure types
  execute.py            ← uses protocol, no type dispatcher
  wizard.py             → NEW: interactive wizard tools
  dashboard.py          → NEW: Chart.js HTML artifact generator
  benchmarks.py         → NEW: market data search tools
```

### Time Granularity

Monthly model with internal hourly profiles. Production engines (especially BESS arbitrage) can simulate at hourly resolution internally using price/irradiation profiles, but output monthly aggregated revenue. The financial model (P&L, CF, BS) runs monthly — consistent with existing SaaS model and standard project finance practice.

### Time Series Type

`list[float]` internally (existing codebase is 100% list[float], 3,587 LOC + 2,736 LOC tests). Lazy conversion to `pd.DataFrame` at output layer for dashboards and exports. pandas is an optional dependency for the presentation layer, not a core requirement.

```python
@dataclass
class FinancialOutput:
    pnl: dict[str, list[float]]
    cashflow: dict[str, list[float]]
    balance: dict[str, list[float]]
    debt_metrics: dict[str, list[float]]
    revenue_breakdown: dict[str, list[float]]
    valuation: dict[str, float]
    sensitivity: list[list[float]] | None
    summary: dict[str, float | int]
    inputs_resolved: dict[str, object]
    project_kpis: ProjectKPIs | None = None  # None for SaaS

    def to_dataframe(self, freq="M", start="2026-01") -> pd.DataFrame:
        """Lazy conversion for dashboards and exports."""
        ...

@dataclass
class ProjectKPIs:
    irr_project: float        # unlevered
    irr_equity: float         # levered
    npv: float
    lcoe: float | None        # $/MWh (energy assets)
    lcos: float | None        # $/MWh (storage assets)
    payback_years: float
    dscr_series: list[float]
    dscr_min: float
    dscr_avg: float
    discount_rate_used: float
    debt_sizing: DebtSizingResult | None
```

## Schema: InfrastructureModelConfig

### Discriminated Union 1: ProductionConfig

What the asset physically produces. Each variant has technology-specific parameters. Optional hourly profiles (8760 values) for detailed merchant/arbitrage revenue.

```python
ProductionConfig = Annotated[
    SolarProduction | WindProduction | BESSProduction
    | H2Production | BiomethaneProduction
    | DataCenterProduction | GenericProduction,
    Field(discriminator="type")
]
```

| Type | Key Fields | Default Yield |
|------|-----------|---------------|
| `solar_pv` | capacity_mwp, specific_yield_kwh_kwp, performance_ratio | 1500 kWh/kWp/yr |
| `wind_onshore` | capacity_mw, capacity_factor, availability, wake_losses | CF 0.28 |
| `bess` | power_mw, duration_hours, round_trip_efficiency, dod, cycles_per_day | RTE 0.88 |
| `hydrogen` | electrolyzer_mw, efficiency_kwh_per_kg, stack_lifetime_hours | 55 kWh/kg |
| `biomethane` | capacity_nm3_h, feedstock_mix, biogas_yield, methane_content | 150 Nm3/ton |
| `data_center` | it_capacity_mw, pue, rack_density_kw, tier, redundancy | PUE 1.3 |
| `generic` | units, output_per_unit_per_period, output_unit | user-defined |

### Discriminated Union 2: RevenueStream (composable list)

Revenue is a `list[RevenueStream]` — projects can stack multiple streams. E.g., BESS = arbitrage + ancillary + capacity. Solar = 70% PPA + 30% merchant + certificates.

```python
RevenueStream = Annotated[
    PPAStream | MerchantStream | ArbitrageStream
    | AncillaryStream | CapacityStream | OfftakeStream
    | CertificateStream | RentalStream | SLAStream,
    Field(discriminator="type")
]
```

| Type | Use Case | Key Fields |
|------|----------|------------|
| `ppa` | Fixed-price energy offtake | price, volume_fraction, escalation, tenor |
| `merchant` | Market-price exposure | base_price, capture_ratio, price_curve |
| `arbitrage` | BESS spread capture | avg_spread, cycles_per_day, capture_ratio |
| `ancillary` | Grid services (FCR/aFRR/mFRR) | per-service €/MW/yr |
| `capacity` | Capacity market payments | €/MW/yr |
| `offtake` | H2/biomethane contracts | price_per_unit, volume, escalation |
| `certificate` | GO, REC, RFNBO, carbon | price_per_unit, eligible_fraction, cert_type |
| `rental` | Real estate, co-location | price_per_unit, occupancy_rate |
| `sla` | Data center hosting | price_per_mw_month, uptime_target |

### Discriminated Union 3: DegradationCurve

How the asset ages. The degradation engine produces a `list[float]` of multipliers (1.0 → declining) that the production engine applies to output.

```python
DegradationCurve = Annotated[
    TimeDegradation | CycleDegradation
    | UsageDegradation | NoDegradation,
    Field(discriminator="type")
]
```

| Type | Use Case | Key Fields |
|------|----------|------------|
| `time_based` | Solar PV (-0.5%/yr), Wind (-0.3%/yr) | annual_rate |
| `cycle_based` | BESS (capacity fade per cycle + calendar) | fade_per_cycle, calendar_fade, eol_pct |
| `usage_based` | H2 electrolyzer (efficiency loss per 1000h) | loss_per_1000h, stack_replacement_hours |
| `none` | Data centers, generic | (no fields) |

### CAPEX Breakdown

Technology CAPEX with per-unit costs, multiple depreciation methods, and lifecycle items.

```python
class InfraCapexItem(BaseModel):
    name: str
    amount_per_unit: float         # €/Wp, €/MW, €/kWh — technology dependent
    unit: str                      # "Wp", "MW", "kWh", "Nm3_h", "rack"
    quantity: float | None = None  # None = derive from ProductionConfig capacity
    depreciation_years: int = 20
    depreciation_method: Literal[
        "straight_line", "declining_balance", "macrs", "soyd", "custom"
    ] = "straight_line"
    macrs_class: int | None = None # 5, 7, 15, 20 year MACRS
    residual_value_pct: float = 0

class CAPEXBreakdown(BaseModel):
    items: list[InfraCapexItem]
    contingency_pct: float = 0.10
    development_cost: float = 0    # permits, engineering, legal
    grid_connection_cost: float = 0
    land_acquisition: float = 0    # if purchased (not leased)
```

### OPEX — Generic with MaintenanceEvent

Common structure for all technologies. Major maintenance as discrete scheduled events.

```python
class MaintenanceEvent(BaseModel):
    name: str
    period: int                    # month from COD
    cost: float
    recurring_interval: int | None = None  # repeats every N months

class InfraOPEXConfig(BaseModel):
    om_fixed_eur_per_mw_yr: float = 0
    om_variable_eur_per_mwh: float = 0
    insurance_pct_capex: float = 0.005
    land_lease_eur_yr: float = 0
    management_fee_eur_yr: float = 0
    other_fixed_eur_yr: float = 0
    major_maintenance: list[MaintenanceEvent] = []
    opex_escalation_pct_yr: float = 0.02
```

### Permits Timeline

Same structure for all technologies — presets set different defaults.

```python
class PermitsTimeline(BaseModel):
    development_months: int = 12
    permitting_months: int = 18
    construction_months: int = 12
    grid_connection_months: int = 6
    construction_drawdown_schedule: list[float] | None = None  # % of CAPEX per month
```

### Project Finance

Full project finance with debt sizing solver, reserves, and cash sweep.

```python
class SeniorDebtConfig(BaseModel):
    tenor_years: int = 18
    interest_rate: float = 0.045
    grace_period_months: int = 0
    amortization: Literal["french", "bullet", "linear", "sculpted"] = "french"
    dscr_target: float = 1.30
    dscr_mode: Literal["min", "avg"] = "min"
    auto_size: bool = True         # True = debt sizing solver

class MezzanineDebtConfig(BaseModel):
    tenor_years: int = 12
    interest_rate: float = 0.08
    dscr_target: float = 1.10
    pik_interest: bool = False

class EquityConfig(BaseModel):
    target_irr: float = 0.12
    distribution_lock_years: int = 0

class ReservesConfig(BaseModel):
    dsra_months: int = 6           # Debt Service Reserve Account
    mra_eur: float = 0             # Maintenance Reserve Account
    working_capital_eur: float = 0

class CashSweepConfig(BaseModel):
    enabled: bool = False
    trigger_dscr: float = 1.40
    sweep_pct: float = 0.50

class ProjectFinanceConfig(BaseModel):
    senior: SeniorDebtConfig | None = None
    mezzanine: MezzanineDebtConfig | None = None
    equity: EquityConfig = EquityConfig()
    reserves: ReservesConfig = ReservesConfig()
    cash_sweep: CashSweepConfig = CashSweepConfig()
    construction_facility: bool = True
    max_leverage: float = 0.80
```

### Incentives — All via IncentiveItem (no hardcoded fields)

Programs (IRA, REPowerEU, PNIEC) delivered as preset YAML factories that generate IncentiveItems.

```python
class IncentiveItem(BaseModel):
    name: str
    type: Literal[
        "tax_credit", "production_subsidy", "capex_grant",
        "feed_in_tariff", "carbon_credit", "rfnbo_premium"
    ]
    value: float                   # % for tax_credit/grant, €/unit for production
    duration_years: int | None = None
    start_year: int = 0

class IncentivesConfig(BaseModel):
    items: list[IncentiveItem] = []
```

### Root Config

```python
class InfrastructureModelConfig(BaseModel):
    meta: ModelMeta               # reused (currency, horizon, start_date)
    production: ProductionConfig  # discriminated union
    revenue: list[RevenueStream]  # composable list of unions
    capex: CAPEXBreakdown
    opex: InfraOPEXConfig
    degradation: DegradationCurve # discriminated union
    timeline: PermitsTimeline
    financing: ProjectFinanceConfig
    incentives: IncentivesConfig = IncentivesConfig()
    taxes: TaxesConfig            # reused (extended with accel. depreciation)
    valuation: ValuationConfig    # reused (extended with IRR/LCOE)
    external_data: ExternalDataConfig = ExternalDataConfig()
```

## Core Extensions

### Accelerated Depreciation + DTA/DTL

`core/depreciation.py` adds methods: `declining_balance`, `macrs` (IRS tables), `soyd`, `custom_schedule`. Returns book vs tax depreciation series. `PnLBuilder` extended with dual tracking: book depreciation for P&L reporting, tax depreciation for tax calculation. Difference generates DTA/DTL entries in `BalanceBuilder`.

### Project Finance Engine (core/financing.py)

Refactors existing `DebtEngine` from `assets/saas/engines.py` into core. Adds:

- **Debt sizing solver**: `size_debt(dscr_target, mode, max_leverage, tenor) → DebtSizingResult`. Secant method. Returns `max_debt`, `dscr_series`, `min_dscr`, `avg_dscr`, `leverage_ratio`, `equity_required`, `feasible: bool`, `reason: str`.
- **Cash sweep**: tiered or binary, excess cash to debt repayment above DSCR trigger.
- **DSRA/MRA**: Reserve accounts that affect cash available for distribution.
- **Construction facility**: Separate construction loan that converts to term loan at COD.
- **Sculpted amortization**: Debt repayment shaped to match project cash flow profile (constant DSCR).

### Degradation Engine (core/degradation.py)

Takes a `DegradationCurve` config and number of periods. Returns `list[float]` of multipliers (1.0 at t=0, declining). Production engine applies these to raw output. For cycle-based (BESS), also tracks remaining capacity and EOL flag.

### Valuation Extensions (core/valuation.py)

- **IRR project** (unlevered): IRR of project cash flows (CAPEX → operating CF)
- **IRR equity** (levered): IRR of equity cash flows (equity invested → dividends received)
- **LCOE**: Total lifecycle cost / total energy produced (€/MWh)
- **LCOS**: Levelized cost of storage (BESS-specific)
- **Discounted payback**: Years until cumulative discounted CF ≥ 0

### Portfolio Model (core/portfolio.py)

`PortfolioModel` takes `list[InfrastructureModelConfig]` and produces combined financial outputs. Assets in a portfolio can share infrastructure costs (grid connection, land) and have correlated production profiles (FV+BESS power-to-X).

## MCP Tools — New

### Wizard Tools (mcp_server/tools/wizard.py)

- `finance.wizard.start` — Start wizard for a technology type. Returns first question batch.
- `finance.wizard.answer` — Submit answer, get next question(s). Handles dependencies (only ask PPA price if PPA selected as revenue stream).
- `finance.wizard.complete` — Finalize wizard, create scenario with all answers.
- `finance.wizard.suggest_benchmark` — For a given field, suggest a benchmark value with source and confidence.

Questions auto-generated from Pydantic Field metadata (description, default, examples). Ordering and dependencies from per-technology `WizardConfig`.

### Dashboard Tools (mcp_server/tools/dashboard.py)

- `finance.dashboard.generate` — Generate full HTML dashboard for a scenario. Includes:
  - Executive summary KPIs (IRR, NPV, LCOE, DSCR min, payback)
  - FCF waterfall chart
  - P&L stacked bars (revenue, COGS, OPEX, EBITDA, net income)
  - Cash flow timeline (operating, investing, financing, cumulative)
  - DSCR timeline with covenant threshold line
  - Sensitivity heatmap (WACC × growth or price × capacity factor)
  - Revenue breakdown pie/stacked (by stream)
  - Balance sheet evolution
  - Degradation curve overlay on production
  - Input summary table
- `finance.dashboard.chart` — Generate a single chart by type (for agent to show individually).

All charts: Chart.js, self-contained HTML, shareable by URL/link.

### Benchmark Tools (mcp_server/tools/benchmarks.py)

- `finance.benchmarks.search` — Search for market data (LCOE by technology, PPA prices, CAPEX benchmarks, capacity factors by region). Returns value + source + confidence + date.
- `finance.benchmarks.sources` — List available benchmark sources and their coverage.

Sources: IRENA Power Generation Costs, Lazard LCOE/LCOS, BloombergNEF, ENTSO-E (spot prices), national regulators (CNMC Spain, FERC USA).

## Validation Test: BESS + Data Center in Same Schema

**BESS 20MW/4h** — fits cleanly:
```yaml
production: {type: bess, power_mw: 20, duration_hours: 4, round_trip_efficiency: 0.88}
revenue:
  - {type: arbitrage, avg_spread_eur_mwh: 40, cycles_per_day: 1.5}
  - {type: ancillary, fcr_eur_mw_yr: 25000}
  - {type: capacity, eur_per_mw_yr: 35000}
degradation: {type: cycle_based, capacity_fade_per_cycle: 0.00005, eol_capacity_pct: 0.70}
```

**Data Center 10MW Tier 3** — fits cleanly:
```yaml
production: {type: data_center, it_capacity_mw: 10, pue: 1.3, tier: 3}
revenue:
  - {type: sla, price_per_mw_month: 150000, uptime_target: 0.999}
degradation: {type: none}
```

Both compose naturally in the same schema without contortions.

## Post-MVP Gaps (documented for v2 iteration)

1. **PPA/Offtake shape**: Add `shape: Literal["fixed","cfd","indexed","virtual","collar"]` + `floor_eur_mwh` / `ceiling_eur_mwh` to PPAStream and OfftakeStream
2. **Floating rate debt**: `rate_type: Literal["fixed","floating"]`, `base_rate`, `spread_bps`, `commitment_fee_pct`, `arrangement_fee_pct` in SeniorDebtConfig
3. **Cash sweep tiers**: Replace binary trigger with `tiers: list[SweepTier]` for graduated sweep
4. **Decommissioning reserve**: Regulatory requirement in many jurisdictions (~30-80k€/MW for FV/wind)
5. **Solar tracker/bifacial**: `tracker_type` and `bifacial_gain` in SolarProduction (+15-25% yield)
6. **BESS dynamic cycling**: Derive cycles from price profile instead of fixed input
