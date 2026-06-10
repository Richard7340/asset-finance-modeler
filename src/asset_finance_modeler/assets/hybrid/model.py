from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from asset_finance_modeler.assets.infrastructure.model import InfrastructureModel
from asset_finance_modeler.assets.infrastructure.schema import (
    InfrastructureModelConfig,
)
from asset_finance_modeler.core.drivers import AmortizationSchedule, AmortKind
from asset_finance_modeler.core.financing import compute_waterfall_dscr
from asset_finance_modeler.core.portfolio import (
    consolidate_npv,
    consolidate_series,
)
from asset_finance_modeler.core.protocols import FinancialOutput
from asset_finance_modeler.core.valuation import (
    compute_irr,
    compute_moic,
    compute_recovery_multiple,
)

# Periods-per-year by horizon frequency (mirrors InfrastructureModel._PPY).
_PPY = {"M": 12, "Q": 4, "Y": 1}


@dataclass
class TrancheSpec:
    principal: float
    interest_rate: float
    tenor_years: int
    amortization: str = "french"


@dataclass
class HybridResult:
    consolidated_fcf: list[float]
    consolidated_revenue: list[float]
    total_capex: float
    asset_total_capex: list[float]
    npv: float
    irr: float
    consolidated_ebitda: list[float] | None = None
    dscr_senior_min: float = 0.0
    dscr_senior_avg: float = 0.0
    dscr_subordinated_min: float = 0.0
    dscr_subordinated_avg: float = 0.0
    moic_subordinated: float = 0.0
    recovery_going_concern: float = 0.0


class HybridProject:
    """Runs several infrastructure assets and consolidates their cash flows
    into a single hybrid/portfolio result (summed FCF, combined NPV/IRR)."""

    def __init__(
        self,
        configs: list[InfrastructureModelConfig],
        discount_rate_annual: float = 0.06,
        senior: TrancheSpec | None = None,
        subordinated: TrancheSpec | None = None,
    ) -> None:
        self.configs = configs
        self.discount_rate_annual = discount_rate_annual
        self.senior = senior
        self.subordinated = subordinated

    def run(self) -> HybridResult:
        fcfs: list[list[float]] = []
        revs: list[list[float]] = []
        ebitdas: list[list[float]] = []
        capexes: list[float] = []
        for cfg in self.configs:
            ppy = _PPY[cfg.meta.horizon.frequency]
            out = InfrastructureModel(cfg).run()
            fcfs.append(self._annual_project_fcf(out, ppy))
            revs.append(self._annual_revenue(out, ppy))
            ebitdas.append(self._annual_ebitda(out, ppy))
            capexes.append(float(out.summary["total_capex"]))
        cons_fcf = consolidate_series(fcfs)
        cons_rev = consolidate_series(revs)
        cons_ebitda = consolidate_series(ebitdas)

        result = HybridResult(
            consolidated_fcf=cons_fcf,
            consolidated_revenue=cons_rev,
            total_capex=sum(capexes),
            asset_total_capex=capexes,
            npv=consolidate_npv(cons_fcf, self.discount_rate_annual),
            irr=compute_irr(cons_fcf, 1),
            consolidated_ebitda=cons_ebitda,
        )

        # Optional consolidated debt: senior + subordinated tranches served on
        # the consolidated annual EBITDA (CFADS proxy) via the seniority
        # waterfall. The subordinated tranche's DSCR is therefore measured net
        # of senior service at the consolidated level.
        if self.senior is None and self.subordinated is None:
            return result

        horizon = len(cons_ebitda)
        tranches: list[list[float]] = []
        senior_ds: list[float] = []
        if self.senior is not None:
            senior_ds = self._tranche_debt_service(self.senior, horizon)
            tranches.append(senior_ds)
        sub_ds: list[float] = []
        if self.subordinated is not None:
            sub_ds = self._tranche_debt_service(self.subordinated, horizon)
            tranches.append(sub_ds)

        dscrs = compute_waterfall_dscr(cons_ebitda, tranches)

        idx = 0
        if self.senior is not None:
            result.dscr_senior_min, result.dscr_senior_avg = _reduce(dscrs[idx])
            idx += 1
        if self.subordinated is not None:
            result.dscr_subordinated_min, result.dscr_subordinated_avg = _reduce(
                dscrs[idx]
            )
            result.moic_subordinated = compute_moic(
                sub_ds, self.subordinated.principal
            )
            result.recovery_going_concern = compute_recovery_multiple(
                cons_ebitda,
                from_period=self.subordinated.tenor_years,
                discount_rate_annual=self.discount_rate_annual,
                periods_per_year=1,
                outstanding_principal=self.subordinated.principal,
            )

        return result

    @staticmethod
    def _tranche_debt_service(spec: TrancheSpec, horizon: int) -> list[float]:
        """Build the ANNUAL debt-service series for a tranche, padded with 0.0
        to the consolidated horizon length. periods_per_year=1 +
        term_periods=tenor_years -> one row per year."""
        if spec.principal <= 0:
            return [0.0] * horizon
        rows = AmortizationSchedule(
            principal=spec.principal,
            annual_rate=spec.interest_rate,
            term_periods=spec.tenor_years,
            periods_per_year=1,
            kind=cast(AmortKind, spec.amortization),
            grace_periods=0,
        ).rows()
        ds = [float(row["total_payment"]) for row in rows]
        if len(ds) < horizon:
            ds = ds + [0.0] * (horizon - len(ds))
        return ds[:horizon]

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

    @staticmethod
    def _annual_ebitda(out: FinancialOutput, ppy: int) -> list[float]:
        """Aggregate the per-period EBITDA (pnl['ebitda']) to annual buckets."""
        return _to_annual(out.pnl["ebitda"], ppy)


def _reduce(series: list[float]) -> tuple[float, float]:
    """Min/avg over positive, finite DSCR values (mirrors InfrastructureModel)."""
    active = [d for d in series if 0 < d < float("inf")]
    if not active:
        return 0.0, 0.0
    return min(active), sum(active) / len(active)


def _to_annual(series: list[float], ppy: int) -> list[float]:
    n = len(series)
    years = n // ppy
    if years <= 0:
        return list(series)
    return [sum(series[y * ppy : (y + 1) * ppy]) for y in range(years)]
