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
