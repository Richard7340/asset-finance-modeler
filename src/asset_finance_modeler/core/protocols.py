from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from pydantic import BaseModel


@dataclass
class DebtSizingResult:
    max_debt: float
    dscr_series: list[float]
    dscr_min: float
    dscr_avg: float
    leverage_ratio: float
    equity_required: float
    feasible: bool
    reason: str


@dataclass
class ProjectKPIs:
    irr_project: float | None
    irr_equity: float | None
    npv: float
    lcoe: float | None
    lcos: float | None
    payback_years: float
    dscr_series: list[float]
    dscr_min: float
    dscr_avg: float
    discount_rate_used: float
    debt_sizing: DebtSizingResult | None
    npv_equity: float = 0.0
    dscr_senior_min: float = 0.0
    dscr_senior_avg: float = 0.0
    dscr_subordinated_min: float = 0.0
    dscr_subordinated_avg: float = 0.0
    moic_subordinated: float = 0.0
    recovery_going_concern: float = 0.0


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
    project_kpis: ProjectKPIs | None = field(default=None)


@runtime_checkable
class FinancialModel(Protocol):
    config_schema: type[BaseModel]

    def run(self) -> FinancialOutput: ...
