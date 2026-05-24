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
    tax_depreciation: list[float] | None = None

    def build(self) -> dict[str, list[float]]:
        n = len(self.revenue)
        gross_profit = [self.revenue[t] - self.cogs[t] for t in range(n)]
        ebitda = [gross_profit[t] - self.opex[t] for t in range(n)]
        ebit = [ebitda[t] - self.depreciation[t] for t in range(n)]
        ebt = [ebit[t] - self.interest_expense[t] for t in range(n)]

        # When tax_depreciation is provided, compute tax EBT using tax depreciation
        # instead of book depreciation, and track DTA/DTL per period.
        if self.tax_depreciation is not None:
            tax_dep = self.tax_depreciation
            dta_dtl = [
                (tax_dep[t] - self.depreciation[t]) * self.corporate_tax_rate
                for t in range(n)
            ]
            # Tax EBT replaces book depreciation with tax depreciation
            tax_ebt = [
                ebt[t] - (tax_dep[t] - self.depreciation[t])
                for t in range(n)
            ]
        else:
            dta_dtl = None
            tax_ebt = ebt

        tax = [0.0] * n
        net_income = [0.0] * n
        loss_carry = 0.0

        for t in range(n):
            if tax_ebt[t] >= 0:
                taxable = tax_ebt[t]
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
                    loss_carry += -tax_ebt[t]

        result = {
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

        if self.tax_depreciation is not None:
            result["tax_depreciation"] = list(self.tax_depreciation)
            result["dta_dtl"] = dta_dtl  # type: ignore[assignment]

        return result


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


@dataclass
class BalanceBuilder:
    cash: list[float]
    ar_balance: list[float]
    fixed_assets_net: list[float]
    debt_outstanding: list[float]
    ap_balance: list[float]
    equity_initial: float
    dta_balance: list[float] | None = None

    def build(self) -> dict[str, list[float]]:
        n = len(self.cash)
        if self.dta_balance is not None:
            total_assets = [
                self.cash[t] + self.ar_balance[t] + self.fixed_assets_net[t] + self.dta_balance[t]
                for t in range(n)
            ]
        else:
            total_assets = [
                self.cash[t] + self.ar_balance[t] + self.fixed_assets_net[t]
                for t in range(n)
            ]
        total_liabilities = [self.debt_outstanding[t] + self.ap_balance[t] for t in range(n)]
        equity = [total_assets[t] - total_liabilities[t] for t in range(n)]
        result = {
            "cash": list(self.cash),
            "ar": list(self.ar_balance),
            "fixed_assets_net": list(self.fixed_assets_net),
            "total_assets": total_assets,
            "debt": list(self.debt_outstanding),
            "ap": list(self.ap_balance),
            "total_liabilities": total_liabilities,
            "equity": equity,
        }
        if self.dta_balance is not None:
            result["dta"] = list(self.dta_balance)
        return result


def compute_unit_economics(
    revenue: list[float],
    cogs: list[float],
    cac_spend: list[float],
    active_customers: list[float],
    new_customers: list[float],
    monthly_churn: float,
    periods_per_year: int,
) -> dict[str, list[float]]:
    n = len(revenue)
    arpu = [revenue[t] / active_customers[t] if active_customers[t] > 0 else 0 for t in range(n)]
    gross_margin = [(revenue[t] - cogs[t]) / revenue[t] if revenue[t] > 0 else 0 for t in range(n)]
    cac = [cac_spend[t] / new_customers[t] if new_customers[t] > 0 else 0 for t in range(n)]
    ltv = [
        (arpu[t] * gross_margin[t]) / monthly_churn if monthly_churn > 0 else math.inf
        for t in range(n)
    ]
    ltv_cac = [ltv[t] / cac[t] if cac[t] > 0 else math.inf for t in range(n)]
    payback = [
        cac[t] / (arpu[t] * gross_margin[t]) if arpu[t] * gross_margin[t] > 0 else math.inf
        for t in range(n)
    ]
    return {
        "arpu": arpu,
        "gross_margin": gross_margin,
        "cac": cac,
        "ltv": ltv,
        "ltv_cac": ltv_cac,
        "payback_months": payback,
    }


def compute_runway(cash_series: list[float]) -> float:
    for t, c in enumerate(cash_series):
        if c < 0:
            return float(t)
    return math.inf


def compute_debt_metrics(
    ebitda: list[float],
    ebit: list[float],
    interest_expense: list[float],
    principal_repaid: list[float],
    debt_outstanding: list[float],
) -> dict[str, list[float]]:
    n = len(ebitda)
    dscr: list[float] = []
    icr: list[float] = []
    leverage: list[float] = []
    for t in range(n):
        debt_service = interest_expense[t] + principal_repaid[t]
        dscr.append(ebitda[t] / debt_service if debt_service > 0 else math.inf)
        icr.append(ebit[t] / interest_expense[t] if interest_expense[t] > 0 else math.inf)
        leverage.append(debt_outstanding[t] / ebitda[t] if ebitda[t] > 0 else 0)
    return {"dscr": dscr, "icr": icr, "leverage": leverage}
