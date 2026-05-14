from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, NonNegativeFloat, NonNegativeInt
from pydantic import conlist


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
    price_escalation_annual: float = Field(default=0, ge=0, le=1, description="Annual % price increase applied at year boundary")


class AcquisitionConfig(BaseModel):
    new_units_per_period: list[float] | float = Field(description="New units added per period — list (per-period) or constant")
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
