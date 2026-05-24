from dataclasses import dataclass

from asset_finance_modeler.core.drivers import AmortizationSchedule
from asset_finance_modeler.assets.saas.schema import DebtInstrument


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
