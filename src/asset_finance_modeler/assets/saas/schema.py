from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, NonNegativeFloat


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
