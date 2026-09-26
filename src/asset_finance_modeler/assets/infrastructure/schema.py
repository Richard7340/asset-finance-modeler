from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from asset_finance_modeler.assets.saas.schema import (
    ExternalDataConfig,
    ModelMeta,
    TaxesConfig,
    ValuationConfig,
)

# ---------------------------------------------------------------------------
# Production configs — discriminated union on "type"
# ---------------------------------------------------------------------------


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
    stack_lifetime_hours: float = 80000
    availability: float = 0.95
    electricity_source: Literal["grid", "dedicated_re", "hybrid"] = "dedicated_re"
    electricity_cost_eur_mwh: float = 40.0


class BiomethaneProduction(BaseModel):
    type: Literal["biomethane"] = "biomethane"
    capacity_nm3_h: float
    biogas_yield_nm3_ton: float = 150
    methane_content: float = 0.55
    upgrading_efficiency: float = 0.98
    operating_hours_yr: float = 8000


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
    SolarProduction
    | WindProduction
    | BESSProduction
    | H2Production
    | BiomethaneProduction
    | DataCenterProduction
    | GenericProduction,
    Field(discriminator="type"),
]

# ---------------------------------------------------------------------------
# Revenue streams — discriminated union on "type"
# ---------------------------------------------------------------------------


class PPAStream(BaseModel):
    type: Literal["ppa"] = "ppa"
    name: str = "PPA"
    price_eur_per_unit: float
    volume_fraction: float = 0.7
    escalation_pct_yr: float = 0.02
    tenor_years: int = 15
    # Curve-driven contract price (EUR/unit) per year. Same pattern as merchant:
    # library curve > explicit points > base × escalation. A curve embeds the
    # consultant price path, so escalation is NOT re-applied on top of it.
    # volume_fraction (a volume factor) is always applied.
    price_curve_name: str | None = None
    price_points: list[float] | None = None


class MerchantStream(BaseModel):
    type: Literal["merchant"] = "merchant"
    name: str = "Merchant"
    base_price_eur_per_unit: float
    volume_fraction: float = 0.3
    capture_ratio: float = 0.90
    # Curve-driven realized capture price (EUR/MWh) per year. When set, the
    # per-year price comes from the curve directly (it already embeds the
    # capture effect), overriding base_price × capture_ratio × escalation.
    # `price_curve_name` references a library curve (e.g. solar_capture_es) and
    # surfaces in the CurvesPanel with its consultant source; `price_points`
    # carries explicit per-year values (e.g. a user-edited override). The legacy
    # `price_curve` is kept as an alias for explicit points.
    price_curve_name: str | None = None
    price_points: list[float] | None = None
    price_curve: list[float] | None = None
    escalation_pct_yr: float = 0.01


class ArbitrageStream(BaseModel):
    type: Literal["arbitrage"] = "arbitrage"
    name: str = "Arbitrage"
    avg_spread_eur_mwh: float = 40
    cycles_per_day: float = 1.5
    spread_capture_ratio: float = 0.75
    spread_curve_name: str | None = None
    spread_points: list[float] | None = None


class AncillaryStream(BaseModel):
    type: Literal["ancillary"] = "ancillary"
    name: str = "Ancillary Services"
    fcr_eur_mw_yr: float = 0
    afrr_eur_mw_yr: float = 0
    mfrr_eur_mw_yr: float = 0
    curve_points: list[float] | None = None


class CapacityStream(BaseModel):
    type: Literal["capacity"] = "capacity"
    name: str = "Capacity Payment"
    eur_per_mw_yr: float
    # Curve-driven capacity price (EUR/MW·yr) per year: library curve > points >
    # flat scalar. Curve embeds the price path (capacity-market auction clears).
    price_curve_name: str | None = None
    price_points: list[float] | None = None


class OfftakeStream(BaseModel):
    type: Literal["offtake"] = "offtake"
    name: str = "Offtake"
    price_eur_per_unit: float
    volume_fraction: float = 1.0
    escalation_pct_yr: float = 0.02
    tenor_years: int = 15
    # Curve-driven offtake price (EUR/unit — e.g. EUR/kg H2, EUR/MWh biomethane)
    # per year: library curve > points > base × escalation (no double-escalation).
    price_curve_name: str | None = None
    price_points: list[float] | None = None


class CertificateStream(BaseModel):
    type: Literal["certificate"] = "certificate"
    name: str = "Green Certificates"
    price_eur_per_unit: float
    eligible_fraction: float = 1.0
    certificate_type: Literal["go", "rec", "rfnbo", "carbon_credit"] = "go"
    # Curve-driven certificate price (EUR/unit) per year: library curve > points
    # > flat scalar. Certificate prices (GO/REC/carbon) are notoriously volatile,
    # so a consultant curve is the realistic input.
    price_curve_name: str | None = None
    price_points: list[float] | None = None


class RentalStream(BaseModel):
    type: Literal["rental"] = "rental"
    name: str = "Rental"
    price_per_unit_period: float
    occupancy_rate: float = 0.95
    escalation_pct_yr: float = 0.02
    # Curve-driven rent (per unit) per year: library curve > points > base ×
    # escalation. occupancy_rate (a volume factor) is always applied; the curve
    # supplies the price path so escalation is NOT re-applied on top of it.
    price_curve_name: str | None = None
    price_points: list[float] | None = None


class SLAStream(BaseModel):
    type: Literal["sla"] = "sla"
    name: str = "SLA Hosting"
    price_per_mw_month: float
    uptime_target: float = 0.999
    # Curve-driven hosting price (EUR/MW·month) per year: library curve > points
    # > flat scalar. Lets colocation price step-downs/escalators be modelled.
    price_curve_name: str | None = None
    price_points: list[float] | None = None


RevenueStream = Annotated[
    PPAStream
    | MerchantStream
    | ArbitrageStream
    | AncillaryStream
    | CapacityStream
    | OfftakeStream
    | CertificateStream
    | RentalStream
    | SLAStream,
    Field(discriminator="type"),
]

# ---------------------------------------------------------------------------
# Degradation curves — discriminated union on "type"
# ---------------------------------------------------------------------------


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
    stack_replacement_hours: float = 80000


class NoDegradation(BaseModel):
    type: Literal["none"] = "none"


DegradationCurve = Annotated[
    TimeDegradation | CycleDegradation | UsageDegradation | NoDegradation,
    Field(discriminator="type"),
]

# ---------------------------------------------------------------------------
# CAPEX
# ---------------------------------------------------------------------------


class InfraCapexItem(BaseModel):
    name: str
    amount_per_unit: float
    unit: str = "MW"
    quantity: float | None = None
    depreciation_years: int = 20
    depreciation_method: Literal["straight_line", "declining_balance", "macrs", "soyd", "custom"] = "straight_line"
    macrs_class: int | None = None
    residual_value_pct: float = 0


class CAPEXBreakdown(BaseModel):
    items: list[InfraCapexItem]
    contingency_pct: float = 0.10
    development_cost: float = 0
    grid_connection_cost: float = 0
    land_acquisition: float = 0


# ---------------------------------------------------------------------------
# OPEX
# ---------------------------------------------------------------------------


class MaintenanceEvent(BaseModel):
    name: str
    period: int
    cost: float
    recurring_interval: int | None = None


class OpexLine(BaseModel):
    """Una linea de coste propia (26-sep): representacion de mercado, seguridad,
    IBI/IAE, vigilancia… fija al anio, por MW o por MWh, con su propia subida
    (None = la subida comun de la OPEX)."""

    name: str
    eur_yr: float = 0.0
    eur_per_mw_yr: float = 0.0
    eur_per_mwh: float = 0.0
    escalation_pct_yr: float | None = None


class Decommissioning(BaseModel):
    """Desmantelamiento al final de la vida: se dota a partes iguales en los
    ultimos `accrue_years` anios del horizonte (gasto y salida de caja)."""

    cost_eur: float = 0.0
    accrue_years: int = Field(5, ge=1, le=30)


class InfraOPEXConfig(BaseModel):
    om_fixed_eur_per_mw_yr: float = 0
    om_variable_eur_per_mwh: float = 0
    insurance_pct_capex: float = 0.005
    land_lease_eur_yr: float = 0
    management_fee_eur_yr: float = 0
    other_fixed_eur_yr: float = 0
    major_maintenance: list[MaintenanceEvent] = Field(default_factory=list)
    opex_escalation_pct_yr: float = 0.02
    other_lines: list[OpexLine] = Field(default_factory=list)
    # Impuesto sobre el valor de la produccion de energia electrica (IVPEE, 7 %
    # en Espana) sobre los ingresos por venta de energia. 0 = no se aplica.
    generation_tax_pct: float = Field(0.0, ge=0, le=0.5)
    decommissioning: Decommissioning | None = None


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------


class PermitsTimeline(BaseModel):
    # Defaults are ZERO so the construction/permitting deferral is strictly
    # opt-in: only the phases a preset/config explicitly declares defer the
    # commercial-operation date (COD) and spread capex. This avoids silently
    # inventing a multi-year deferral for any config that omits a phase (e.g. a
    # preset that only sets construction_months would otherwise inherit a large
    # development+permitting offset it never asked for).
    development_months: int = 0
    permitting_months: int = 0
    construction_months: int = 0
    grid_connection_months: int = 0
    construction_drawdown_schedule: list[float] | None = None


# ---------------------------------------------------------------------------
# Project Finance
# ---------------------------------------------------------------------------


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


class SubordinatedDebtConfig(BaseModel):
    """Fixed-ticket subordinated tranche (e.g. an investor's committed amount)."""

    principal: float
    interest_rate: float = 0.085
    tenor_years: int = 7
    grace_period_months: int = 0
    amortization: Literal["french", "bullet", "linear"] = "french"
    drawdown_period: int = 0


class EquityConfig(BaseModel):
    target_irr: float = 0.12
    # Sin reparto al socio los primeros N anios (la caja queda en el proyecto).
    distribution_lock_years: int = 0
    # Covenant de lock-up: el anio en que el DSCR baja de este nivel no se
    # reparte; lo retenido se paga el primer anio que se cumpla (o al final).
    lockup_dscr: float | None = None


class ReservesConfig(BaseModel):
    dsra_months: int = 6
    mra_eur: float = 0
    working_capital_eur: float = 0


class CashSweepConfig(BaseModel):
    enabled: bool = False
    trigger_dscr: float = 1.40
    sweep_pct: float = 0.50


class LossesConfig(BaseModel):
    """Recortes de produccion (curtailment: la red o el precio obligan a parar).
    `curtailment_pct` fijo, o `curtailment_curve` por anio (manda si existe)."""

    curtailment_pct: float = Field(0.0, ge=0, le=1)
    curtailment_curve: list[float] | None = None


class ProjectFinanceConfig(BaseModel):
    senior: SeniorDebtConfig | None = None
    mezzanine: MezzanineDebtConfig | None = None
    subordinated: SubordinatedDebtConfig | None = None
    equity: EquityConfig = Field(default_factory=EquityConfig)
    reserves: ReservesConfig = Field(default_factory=ReservesConfig)
    cash_sweep: CashSweepConfig = Field(default_factory=CashSweepConfig)
    construction_facility: bool = True
    max_leverage: float = 0.80
    # Comision de apertura sobre toda la deuda dispuesta (gasto y caja al disponer).
    upfront_fee_pct: float = Field(0.0, ge=0, le=0.1)


# ---------------------------------------------------------------------------
# Incentives
# ---------------------------------------------------------------------------


class IncentiveItem(BaseModel):
    name: str
    type: Literal["tax_credit", "production_subsidy", "capex_grant", "feed_in_tariff", "carbon_credit", "rfnbo_premium"]
    value: float
    duration_years: int | None = None
    start_year: int = 0


class IncentivesConfig(BaseModel):
    items: list[IncentiveItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Capex events / repowering
# ---------------------------------------------------------------------------


class CapexEvent(BaseModel):
    year: int  # 0-based model year of the event
    amount: float  # capex injection, same units as CAPEX
    resets_degradation: bool = False  # if True, capacity returns to nameplate
    label: str = ""


# ---------------------------------------------------------------------------
# Root model
# ---------------------------------------------------------------------------


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
    capex_events: list[CapexEvent] = Field(default_factory=list)
    losses: LossesConfig = Field(default_factory=LossesConfig)
