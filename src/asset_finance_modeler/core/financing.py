from dataclasses import dataclass

from asset_finance_modeler.assets.saas.schema import DebtInstrument
from asset_finance_modeler.core.drivers import AmortizationSchedule
from asset_finance_modeler.core.protocols import DebtSizingResult


@dataclass
class DebtEngine:
    instruments: list[DebtInstrument]
    periods: int
    periods_per_year: int

    def compute(self) -> dict[str, list[float]]:
        interest = [0.0] * self.periods
        principal_repaid = [0.0] * self.periods
        drawdowns = [0.0] * self.periods
        origination_fees = [0.0] * self.periods
        balance = [0.0] * self.periods

        for inst in self.instruments:
            t0 = inst.drawdown_period
            if t0 >= self.periods:
                continue
            drawdowns[t0] += inst.principal
            origination_fees[t0] += inst.principal * inst.origination_fee_pct
            sched = AmortizationSchedule(
                principal=inst.principal,
                annual_rate=inst.interest_rate_annual,
                term_periods=inst.term_months,
                periods_per_year=self.periods_per_year,
                kind=inst.amortization,
                grace_periods=inst.grace_period_months,
                custom_schedule=inst.custom_schedule,
                idc_periods=inst.idc_periods,
                deferral_periods=inst.deferral_periods,
            ).rows()
            for i, row in enumerate(sched):
                t = t0 + i
                if t >= self.periods:
                    break
                interest[t] += row["interest"]
                principal_repaid[t] += row["principal_payment"]
                balance[t] += row["balance_end"]

        return {
            "drawdowns": drawdowns,
            "origination_fees": origination_fees,
            "interest_expense": interest,
            "principal_repaid": principal_repaid,
            "balance_outstanding": balance,
        }


def compute_dsra(
    debt_service: list[float],
    dsra_months: int,
    periods_per_year: int,
) -> list[float]:
    if dsra_months <= 0:
        return [0.0] * len(debt_service)
    n = len(debt_service)
    result: list[float] = []
    for t in range(n):
        # DSRA at period t = reserve for NEXT dsra_months periods (t+1 onwards)
        lookahead_start = t + 1
        lookahead_end = min(lookahead_start + dsra_months, n)
        remaining_ds = sum(debt_service[lookahead_start:lookahead_end])
        result.append(remaining_ds)
    return result


def compute_cash_sweep(
    excess_cash: list[float],
    dscr_series: list[float],
    trigger_dscr: float,
    sweep_pct: float,
) -> list[float]:
    return [
        excess_cash[t] * sweep_pct if dscr_series[t] >= trigger_dscr else 0.0
        for t in range(len(excess_cash))
    ]


def _compute_dscr_for_debt(
    cfads: list[float],
    debt_amount: float,
    interest_rate: float,
    tenor_periods: int,
    periods_per_year: int,
    amortization: str,
    grace_periods: int,
    deferral_periods: int = 0,
) -> list[float]:
    if debt_amount <= 0:
        return [float("inf")] * len(cfads)
    sched = AmortizationSchedule(
        principal=debt_amount,
        annual_rate=interest_rate,
        term_periods=tenor_periods,
        periods_per_year=periods_per_year,
        kind=amortization,
        grace_periods=grace_periods,
        deferral_periods=deferral_periods,
    ).rows()
    n = len(cfads)
    dscr: list[float] = []
    for t in range(n):
        if t < len(sched):
            ds = sched[t]["total_payment"]
            if ds <= 0:
                dscr.append(float("inf"))
            elif cfads[t] <= 0:
                dscr.append(0.0)
            else:
                dscr.append(cfads[t] / ds)
        else:
            dscr.append(float("inf"))
    return dscr


def size_debt(
    cfads: list[float],
    dscr_target: float,
    dscr_mode: str,
    interest_rate: float,
    tenor_periods: int,
    periods_per_year: int,
    max_leverage: float,
    total_capex: float,
    amortization: str,
    grace_periods: int,
    deferral_periods: int = 0,
) -> DebtSizingResult:
    max_debt_by_leverage = total_capex * max_leverage
    lo, hi = 0.0, max_debt_by_leverage
    # DSCR is scored over the OPERATING window only: amortization runs from COD
    # (after deferral_periods of construction) for tenor_periods.
    op_end = deferral_periods + tenor_periods

    for _ in range(50):
        mid = (lo + hi) / 2
        if mid < 1:
            break
        dscr = _compute_dscr_for_debt(
            cfads, mid, interest_rate, tenor_periods,
            periods_per_year, amortization, grace_periods, deferral_periods,
        )
        active_dscr = [d for d in dscr[deferral_periods:op_end] if 0 < d < float("inf")]
        if not active_dscr:
            hi = mid
            continue
        check = min(active_dscr) if dscr_mode == "min" else sum(active_dscr) / len(active_dscr)
        if check >= dscr_target:
            lo = mid
        else:
            hi = mid

    final_debt = lo
    # Infeasible if achievable debt is negligible (< 1% of capex or < 1)
    min_viable_debt = max(1.0, total_capex * 0.01)
    if final_debt < min_viable_debt:
        return DebtSizingResult(
            max_debt=0, dscr_series=[], dscr_min=0, dscr_avg=0,
            leverage_ratio=0, equity_required=total_capex,
            feasible=False, reason="DSCR target unreachable with given cash flows",
        )

    final_dscr = _compute_dscr_for_debt(
        cfads, final_debt, interest_rate, tenor_periods,
        periods_per_year, amortization, grace_periods, deferral_periods,
    )
    active = [d for d in final_dscr[deferral_periods:op_end] if d < float("inf")]
    return DebtSizingResult(
        max_debt=final_debt,
        dscr_series=final_dscr,
        dscr_min=min(active) if active else 0,
        dscr_avg=sum(active) / len(active) if active else 0,
        leverage_ratio=final_debt / total_capex if total_capex > 0 else 0,
        equity_required=total_capex - final_debt,
        feasible=True,
        reason="ok",
    )


def compute_waterfall_dscr(
    cfads: list[float],
    tranche_debt_service: list[list[float]],
) -> list[list[float]]:
    """Per-tranche DSCR in seniority order (most senior first).

    Each tranche's DSCR uses CFADS net of ALL more-senior tranches' debt
    service: DSCR_k[t] = (cfads[t] - sum(ds_j[t] for j<k)) / ds_k[t].
    Zero service -> inf (no obligation that period); non-positive available
    cash with positive service -> 0.0.
    """
    n = len(cfads)
    results: list[list[float]] = []
    for idx, ds in enumerate(tranche_debt_service):
        dscr: list[float] = []
        for t in range(n):
            senior_ds = sum(tranche_debt_service[j][t] for j in range(idx))
            available = cfads[t] - senior_ds
            service = ds[t]
            if service <= 0:
                dscr.append(float("inf"))
            elif available <= 0:
                dscr.append(0.0)
            else:
                dscr.append(available / service)
        results.append(dscr)
    return results
