import math
from dataclasses import dataclass


@dataclass
class PnLBuilder:
    revenue: list[float]
    cogs: list[float]
    opex: list[float]
    depreciation: list[float]
    interest_expense: list[float]
    corporate_tax_rate: float
    carryforward_enabled: bool = True

    def build(self) -> dict[str, list[float]]:
        n = len(self.revenue)
        gross_profit = [self.revenue[t] - self.cogs[t] for t in range(n)]
        ebitda = [gross_profit[t] - self.opex[t] for t in range(n)]
        ebit = [ebitda[t] - self.depreciation[t] for t in range(n)]
        ebt = [ebit[t] - self.interest_expense[t] for t in range(n)]

        tax = [0.0] * n
        net_income = [0.0] * n
        loss_carry = 0.0

        for t in range(n):
            if ebt[t] >= 0:
                taxable = ebt[t]
                if self.carryforward_enabled and loss_carry > 0:
                    used = min(loss_carry, taxable)
                    taxable -= used
                    loss_carry -= used
                tax[t] = taxable * self.corporate_tax_rate
                net_income[t] = ebt[t] - tax[t]
            else:
                tax[t] = 0
                net_income[t] = ebt[t]
                if self.carryforward_enabled:
                    loss_carry += -ebt[t]

        return {
            "revenue": list(self.revenue),
            "cogs": list(self.cogs),
            "gross_profit": gross_profit,
            "opex": list(self.opex),
            "ebitda": ebitda,
            "depreciation": list(self.depreciation),
            "ebit": ebit,
            "interest_expense": list(self.interest_expense),
            "ebt": ebt,
            "tax": tax,
            "net_income": net_income,
        }


@dataclass
class CashFlowBuilder:
    net_income: list[float]
    depreciation: list[float]
    revenue: list[float]
    cogs: list[float]
    dso_days: int
    dpo_days: int
    capex: list[float]
    funding_drawdowns: list[float]
    debt_drawdowns: list[float]
    debt_principal_repaid: list[float]
    origination_fees: list[float]
    initial_cash: float
    period_days: int

    def build(self) -> dict[str, list[float]]:
        n = len(self.net_income)
        ar = [self.revenue[t] * self.dso_days / self.period_days for t in range(n)]
        ap = [self.cogs[t] * self.dpo_days / self.period_days for t in range(n)]
        delta_ar = [ar[t] - (ar[t - 1] if t > 0 else 0) for t in range(n)]
        delta_ap = [ap[t] - (ap[t - 1] if t > 0 else 0) for t in range(n)]

        cfo = [
            self.net_income[t] + self.depreciation[t] - delta_ar[t] + delta_ap[t]
            for t in range(n)
        ]
        cfi = [-self.capex[t] for t in range(n)]
        cff = [
            self.funding_drawdowns[t]
            + self.debt_drawdowns[t]
            - self.debt_principal_repaid[t]
            - self.origination_fees[t]
            for t in range(n)
        ]

        cash = [0.0] * n
        cash[0] = self.initial_cash + cfo[0] + cfi[0] + cff[0]
        for t in range(1, n):
            cash[t] = cash[t - 1] + cfo[t] + cfi[t] + cff[t]

        return {
            "delta_ar": delta_ar,
            "delta_ap": delta_ap,
            "cfo": cfo,
            "cfi": cfi,
            "cff": cff,
            "cash": cash,
            "ar_balance": ar,
            "ap_balance": ap,
        }
