from __future__ import annotations

from pydantic import BaseModel, Field

from asset_finance_modeler.assets.infrastructure.schema import (
    CapexEvent,
    SeniorDebtConfig,
    SubordinatedDebtConfig,
)
from asset_finance_modeler.assets.saas.schema import HorizonConfig

# ---------------------------------------------------------------------------
# Income-statement lines (extensible: the user adds revenue/opex/capex lines)
# ---------------------------------------------------------------------------


class RevenueLine(BaseModel):
    name: str
    year1_amount: float
    growth_pct_yr: float = 0.0


class OpexLine(BaseModel):
    name: str
    year1_amount: float
    # Per-line annual growth. When None (default) the line escalates by the
    # shared ``OpexConfigB.escalation_pct_yr``; when set (incl. 0.0) it overrides
    # the shared escalation for that line — mirrors the revenue side (E2).
    growth_pct_yr: float | None = None


class CapexItemB(BaseModel):
    name: str
    amount: float
    period: int = 0
    depreciation_years: int = 10


# ---------------------------------------------------------------------------
# Section configs
# ---------------------------------------------------------------------------


class CogsConfig(BaseModel):
    pct_of_revenue: float = 0.0


class OpexConfigB(BaseModel):
    fixed_lines: list[OpexLine] = Field(default_factory=list)
    variable_pct_of_revenue: float = 0.0
    escalation_pct_yr: float = 0.02


class CapexConfigB(BaseModel):
    items: list[CapexItemB] = Field(default_factory=list)
    events: list[CapexEvent] = Field(default_factory=list)


class WorkingCapitalB(BaseModel):
    receivable_days: float = 0.0
    payable_days: float = 0.0
    inventory_days: float = 0.0


class FinancingB(BaseModel):
    senior: SeniorDebtConfig | None = None
    subordinated: SubordinatedDebtConfig | None = None
    max_leverage: float = 0.0


class TaxesB(BaseModel):
    corporate_income_tax_rate: float = 0.25
    tax_loss_carryforward: bool = True


class ValuationB(BaseModel):
    discount_rate_annual: float = 0.10
    cost_of_equity_annual: float | None = None
    terminal_growth_rate: float = 0.0
    terminal_method: str = "gordon"
    # Residual / exit sale value of the underlying asset at the end of the
    # modelling horizon (e.g. a real-estate sale). Added as a discounted cash
    # inflow in the final valuation year, so finite-horizon asset-backed deals
    # recover their capital instead of showing a structurally negative VAN
    # (P0-7). None = no residual.
    residual_value: float | None = None


# ---------------------------------------------------------------------------
# Meta / root model
# ---------------------------------------------------------------------------


class BusinessMeta(BaseModel):
    name: str
    horizon: HorizonConfig
    base_currency: str = "EUR"
    start_date: str = "2026-01-01"


class BusinessModelConfig(BaseModel):
    meta: BusinessMeta
    revenue: list[RevenueLine] = Field(default_factory=list)
    cogs: CogsConfig = Field(default_factory=CogsConfig)
    opex: OpexConfigB = Field(default_factory=OpexConfigB)
    capex: CapexConfigB = Field(default_factory=CapexConfigB)
    working_capital: WorkingCapitalB = Field(default_factory=WorkingCapitalB)
    financing: FinancingB = Field(default_factory=FinancingB)
    taxes: TaxesB = Field(default_factory=TaxesB)
    valuation: ValuationB = Field(default_factory=ValuationB)
