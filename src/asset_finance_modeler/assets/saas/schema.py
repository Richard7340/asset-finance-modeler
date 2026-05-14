from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, NonNegativeFloat, NonNegativeInt, conlist, model_validator


class HorizonConfig(BaseModel):
    periods: int = Field(gt=0, description="Number of periods")
    frequency: Literal["M", "Q", "Y"] = Field(description="M=monthly, Q=quarterly, Y=annual")


class ModelMeta(BaseModel):
    name: str = Field(description="Model name (e.g. 'gestnova')")
    base_currency: str = Field(default="EUR", description="ISO 4217 base currency")
    fx_rates: dict[str, float] = Field(default_factory=dict, description="FX rates to base_currency keyed by ISO 4217")
    inflation_annual: float = Field(default=0.025, description="Annual inflation rate for real terms")
    horizon: HorizonConfig
    start_date: date = Field(description="First period start date")
    initial_cash: NonNegativeFloat = Field(description="Cash on hand at t=0")
    schema_version: int = Field(default=1, description="Schema version for forward compat")


class PricingConfig(BaseModel):
    per_unit_per_period: NonNegativeFloat = Field(description="Recurring price per unit (e.g. €/agent/month)")
    setup_one_time: NonNegativeFloat = Field(default=0, description="One-time setup fee per new customer")
    price_escalation_annual: float = Field(
        default=0, ge=0, le=1,
        description="Annual % price increase applied at year boundary",
    )


class AcquisitionConfig(BaseModel):
    new_units_per_period: list[float] | float = Field(
        description="New units added per period — list (per-period) or constant",
    )
    avg_units_per_customer: NonNegativeFloat = Field(default=1.0, description="Multiplier units per acquired customer")
    cac_per_customer: NonNegativeFloat = Field(description="Cost to acquire one customer (blended)")
    cac_payback_target_months: NonNegativeInt = Field(default=12, description="Informational only")


class RetentionConfig(BaseModel):
    monthly_churn_rate: float = Field(ge=0, le=1, description="Gross logo churn per month (0-1)")
    gross_revenue_retention: float = Field(default=1.0, ge=0, le=1)
    expansion_revenue_pct: float = Field(default=0, ge=0, description="Monthly expansion revenue % over existing base")


class RevenueSource(BaseModel):
    name: str
    pricing: PricingConfig
    acquisition: AcquisitionConfig
    retention: RetentionConfig


class RevenueConfig(BaseModel):
    sources: conlist(RevenueSource, min_length=1)  # type: ignore[valid-type]


class LLMTier(BaseModel):
    model: str = Field(description="Model identifier (e.g. 'sonnet-4-7')")
    eur_per_million_input: NonNegativeFloat
    eur_per_million_output: NonNegativeFloat
    avg_tokens_in_per_month: NonNegativeFloat
    avg_tokens_out_per_month: NonNegativeFloat

    def monthly_cost_eur(self) -> float:
        return (
            self.avg_tokens_in_per_month / 1_000_000 * self.eur_per_million_input
            + self.avg_tokens_out_per_month / 1_000_000 * self.eur_per_million_output
        )


class VoiceProviderCost(BaseModel):
    provider: str
    eur_per_minute: float | None = Field(default=None, description="STT pricing")
    eur_per_million_chars: float | None = Field(default=None, description="TTS pricing")
    monthly_usage: NonNegativeFloat = Field(description="Minutes (STT) or chars (TTS) per month per active unit")

    def monthly_cost_eur(self) -> float:
        if self.eur_per_minute is not None:
            return self.eur_per_minute * self.monthly_usage
        if self.eur_per_million_chars is not None:
            return self.monthly_usage / 1_000_000 * self.eur_per_million_chars
        return 0.0


class TwilioCost(BaseModel):
    whatsapp_eur_per_msg: NonNegativeFloat = 0
    voice_eur_per_min: NonNegativeFloat = 0
    msgs_per_month: NonNegativeFloat = 0
    min_per_month: NonNegativeFloat = 0

    def monthly_cost_eur(self) -> float:
        return self.whatsapp_eur_per_msg * self.msgs_per_month + self.voice_eur_per_min * self.min_per_month


class PerActiveUnitCosts(BaseModel):
    llm_tokens: list[LLMTier] = Field(default_factory=list)
    stt: VoiceProviderCost | None = None
    tts: VoiceProviderCost | None = None
    twilio: TwilioCost | None = None
    infra_eur: NonNegativeFloat = 0

    def monthly_cost_eur(self) -> float:
        total = sum(t.monthly_cost_eur() for t in self.llm_tokens) + self.infra_eur
        if self.stt:
            total += self.stt.monthly_cost_eur()
        if self.tts:
            total += self.tts.monthly_cost_eur()
        if self.twilio:
            total += self.twilio.monthly_cost_eur()
        return total


class PerActiveCustomerCosts(BaseModel):
    support_eur: NonNegativeFloat = 0
    onboarding_one_time_eur: NonNegativeFloat = 0


class COGSConfig(BaseModel):
    per_active_unit: PerActiveUnitCosts
    per_active_customer: PerActiveCustomerCosts


class TeamRole(BaseModel):
    role: str
    monthly_cost: NonNegativeFloat = Field(description="Gross + employer SS per person")
    headcount: int | None = Field(default=None, ge=0)
    headcount_schedule: list[int] | None = Field(default=None, description="Per-period headcount (ramp)")
    start_period: NonNegativeInt = 0
    end_period: int | None = None

    @model_validator(mode="after")
    def _validate_headcount(self) -> "TeamRole":
        if self.headcount is None and self.headcount_schedule is None:
            raise ValueError("Either 'headcount' or 'headcount_schedule' must be set")
        if self.headcount is not None and self.headcount_schedule is not None:
            raise ValueError("'headcount' and 'headcount_schedule' are mutually exclusive")
        return self

    def headcount_at_period(self, period: int) -> int:
        if period < self.start_period:
            return 0
        if self.end_period is not None and period >= self.end_period:
            return 0
        if self.headcount is not None:
            return self.headcount
        assert self.headcount_schedule is not None
        idx = period - self.start_period
        if idx < 0:
            return 0
        if idx >= len(self.headcount_schedule):
            return self.headcount_schedule[-1]
        return self.headcount_schedule[idx]


class OpexConfig(BaseModel):
    team: list[TeamRole]
    infra_fixed_eur: NonNegativeFloat | list[NonNegativeFloat] = 0
    marketing_eur: NonNegativeFloat | list[NonNegativeFloat] = 0
    legal_admin_eur: NonNegativeFloat | list[NonNegativeFloat] = 0
    other_eur: NonNegativeFloat | list[NonNegativeFloat] = 0


class WorkingCapital(BaseModel):
    days_sales_outstanding: NonNegativeInt = 30
    days_payable_outstanding: NonNegativeInt = 30
    days_inventory: NonNegativeInt = 0


class FundingRound(BaseModel):
    period: NonNegativeInt
    amount: NonNegativeFloat
    type: str
    dilution: float = Field(ge=0, le=1)
    valuation_pre: NonNegativeFloat | None = None


class CapExItem(BaseModel):
    name: str
    amount: NonNegativeFloat
    period: NonNegativeInt
    depreciation_years: int = Field(gt=0)


class DebtInstrument(BaseModel):
    name: str
    principal: NonNegativeFloat
    drawdown_period: NonNegativeInt
    interest_rate_annual: float = Field(ge=0)
    term_months: int = Field(gt=0)
    grace_period_months: NonNegativeInt = 0
    amortization: Literal["french", "bullet", "linear", "custom"] = "french"
    custom_schedule: list[float] | None = None
    origination_fee_pct: float = Field(default=0, ge=0, le=1)

    @model_validator(mode="after")
    def _validate_custom(self) -> "DebtInstrument":
        if self.amortization == "custom" and self.custom_schedule is None:
            raise ValueError("custom amortization requires custom_schedule")
        if self.amortization == "custom":
            assert self.custom_schedule is not None
            expected = self.term_months - self.grace_period_months
            if len(self.custom_schedule) != expected:
                raise ValueError(f"custom_schedule length {len(self.custom_schedule)} != {expected}")
        return self


class CapitalConfig(BaseModel):
    working_capital: WorkingCapital
    capex_schedule: list[CapExItem] = Field(default_factory=list)
    funding_rounds: list[FundingRound] = Field(default_factory=list)
    debt: list[DebtInstrument] = Field(default_factory=list)


class TaxesConfig(BaseModel):
    corporate_income_tax_rate: float = Field(default=0.25, ge=0, le=1)
    vat_rate: float = Field(default=0.21, ge=0, le=1)
    payroll_taxes_pct: float = Field(default=0.30, ge=0, le=1)
    r_and_d_deduction_pct: float = Field(default=0, ge=0, le=1)
    tax_loss_carryforward: bool = True


class SensitivityGrid(BaseModel):
    wacc: list[float]
    growth: list[float]


class ValuationConfig(BaseModel):
    discount_rate_annual: float = Field(gt=0, description="WACC for DCF")
    terminal_growth_rate: float = Field(default=0.025, ge=0)
    exit_multiple_arr: float | None = None
    exit_multiple_ebitda: float | None = None
    terminal_method: Literal["gordon", "exit_multiple"] = "gordon"
    sensitivity_grid: SensitivityGrid | None = None


class ExternalValue(BaseModel):
    value: float
    source: str | None = None
    fetched_at: datetime | None = None
    confidence: Literal["low", "medium", "high"] = "medium"


class ExternalDataConfig(BaseModel):
    benchmarks: dict[str, ExternalValue] = Field(default_factory=dict)
    fx_source: str | None = None
    bond_yields_source: str | None = None


class SaasModelConfig(BaseModel):
    meta: ModelMeta
    revenue: RevenueConfig
    cost_of_revenue: COGSConfig
    operating_expenses: OpexConfig
    capital: CapitalConfig
    taxes: TaxesConfig = Field(default_factory=TaxesConfig)
    valuation: ValuationConfig
    external_data: ExternalDataConfig = Field(default_factory=ExternalDataConfig)
