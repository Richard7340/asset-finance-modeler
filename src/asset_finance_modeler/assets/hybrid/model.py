from __future__ import annotations

from dataclasses import dataclass

from asset_finance_modeler.assets.infrastructure.model import InfrastructureModel
from asset_finance_modeler.assets.infrastructure.schema import (
    InfrastructureModelConfig,
)
from asset_finance_modeler.core.portfolio import (
    consolidate_npv,
    consolidate_series,
)
from asset_finance_modeler.core.protocols import FinancialOutput
from asset_finance_modeler.core.valuation import compute_irr

# Periods-per-year by horizon frequency (mirrors InfrastructureModel._PPY).
_PPY = {"M": 12, "Q": 4, "Y": 1}


@dataclass
class HybridResult:
    consolidated_fcf: list[float]
    consolidated_revenue: list[float]
    total_capex: float
    asset_total_capex: list[float]
    npv: float
    irr: float


class HybridProject:
    """Runs several infrastructure assets and consolidates their cash flows
    into a single hybrid/portfolio result (summed FCF, combined NPV/IRR)."""

    def __init__(
        self,
        configs: list[InfrastructureModelConfig],
        discount_rate_annual: float = 0.06,
    ) -> None:
        self.configs = configs
        self.discount_rate_annual = discount_rate_annual

    def run(self) -> HybridResult:
        fcfs: list[list[float]] = []
        revs: list[list[float]] = []
        capexes: list[float] = []
        for cfg in self.configs:
            ppy = _PPY[cfg.meta.horizon.frequency]
            out = InfrastructureModel(cfg).run()
            fcfs.append(self._annual_project_fcf(out, ppy))
            revs.append(self._annual_revenue(out, ppy))
            capexes.append(float(out.summary["total_capex"]))
        cons_fcf = consolidate_series(fcfs)
        cons_rev = consolidate_series(revs)
        return HybridResult(
            consolidated_fcf=cons_fcf,
            consolidated_revenue=cons_rev,
            total_capex=sum(capexes),
            asset_total_capex=capexes,
            npv=consolidate_npv(cons_fcf, self.discount_rate_annual),
            irr=compute_irr(cons_fcf, 1),
        )

    @staticmethod
    def _annual_project_fcf(out: FinancialOutput, ppy: int) -> list[float]:
        """Reconstruct the annual project free-cash-flow series.

        Mirrors InfrastructureModel.run(): per-period project FCF = cfo + cfi
        (CFI carries the year-0 capex outlay), aggregated to annual buckets.
        """
        cfo = out.cashflow["cfo"]
        cfi = out.cashflow["cfi"]
        n = len(cfo)
        fcf = [cfo[t] + cfi[t] for t in range(n)]
        return _to_annual(fcf, ppy)

    @staticmethod
    def _annual_revenue(out: FinancialOutput, ppy: int) -> list[float]:
        """Aggregate the per-period revenue (pnl['revenue']) to annual buckets."""
        return _to_annual(out.pnl["revenue"], ppy)


def _to_annual(series: list[float], ppy: int) -> list[float]:
    n = len(series)
    years = n // ppy
    if years <= 0:
        return list(series)
    return [sum(series[y * ppy : (y + 1) * ppy]) for y in range(years)]
