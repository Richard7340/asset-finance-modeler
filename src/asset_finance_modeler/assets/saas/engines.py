from dataclasses import dataclass

from asset_finance_modeler.core.drivers import AmortizationSchedule, expand_growth

from .schema import COGSConfig, CapExItem, DebtInstrument, OpexConfig, RevenueSource


@dataclass
class CohortRevenueEngine:
    sources: list[RevenueSource]
    periods: int

    def compute(self) -> dict[str, list[float]]:
        active_units = [0.0] * self.periods
        active_customers = [0.0] * self.periods
        subscription = [0.0] * self.periods
        setup = [0.0] * self.periods
        new_units_total = [0.0] * self.periods
        new_customers_total = [0.0] * self.periods

        for src in self.sources:
            new_units_series = expand_growth(src.acquisition.new_units_per_period, self.periods)
            churn = src.retention.monthly_churn_rate
            avg_u_per_c = src.acquisition.avg_units_per_customer
            price = src.pricing.per_unit_per_period
            setup_fee = src.pricing.setup_one_time

            au = [0.0] * self.periods
            ac = [0.0] * self.periods
            stp = [0.0] * self.periods
            for cohort_t, new_u in enumerate(new_units_series):
                new_c = new_u / avg_u_per_c if avg_u_per_c > 0 else 0
                stp[cohort_t] += new_c * setup_fee
                for t in range(cohort_t, self.periods):
                    survival = (1 - churn) ** (t - cohort_t)
                    au[t] += new_u * survival
                    ac[t] += new_c * survival

            sub = [au[t] * price for t in range(self.periods)]

            for t in range(self.periods):
                active_units[t] += au[t]
                active_customers[t] += ac[t]
                subscription[t] += sub[t]
                setup[t] += stp[t]
                new_units_total[t] += new_units_series[t]
                new_customers_total[t] += new_units_series[t] / avg_u_per_c if avg_u_per_c > 0 else 0

        return {
            "active_units": active_units,
            "active_customers": active_customers,
            "subscription_revenue": subscription,
            "setup_revenue": setup,
            "total_revenue": [s + u for s, u in zip(subscription, setup)],
            "new_units": new_units_total,
            "new_customers": new_customers_total,
        }


@dataclass
class COGSEngine:
    cogs: COGSConfig
    active_units: list[float]
    active_customers: list[float]

    def compute(self) -> dict[str, list[float]]:
        per_unit = self.cogs.per_active_unit.monthly_cost_eur()
        support = self.cogs.per_active_customer.support_eur
        variable_unit = [per_unit * u for u in self.active_units]
        variable_customer = [support * c for c in self.active_customers]
        total = [v + c for v, c in zip(variable_unit, variable_customer)]
        return {
            "variable_per_unit": variable_unit,
            "variable_per_customer": variable_customer,
            "total_cogs": total,
        }


def _expand_opex_bucket(value: float | list[float], periods: int) -> list[float]:
    return expand_growth(value, periods)


@dataclass
class OpexEngine:
    opex: OpexConfig
    periods: int

    def compute(self) -> dict[str, list[float]]:
        team_cost = [0.0] * self.periods
        for role in self.opex.team:
            for t in range(self.periods):
                team_cost[t] += role.headcount_at_period(t) * role.monthly_cost

        infra = _expand_opex_bucket(self.opex.infra_fixed_eur, self.periods)
        marketing = _expand_opex_bucket(self.opex.marketing_eur, self.periods)
        legal = _expand_opex_bucket(self.opex.legal_admin_eur, self.periods)
        other = _expand_opex_bucket(self.opex.other_eur, self.periods)

        total = [team_cost[t] + infra[t] + marketing[t] + legal[t] + other[t] for t in range(self.periods)]
        return {
            "team_cost": team_cost,
            "infra_fixed": infra,
            "marketing": marketing,
            "legal_admin": legal,
            "other": other,
            "total_opex": total,
        }


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


@dataclass
class CapExEngine:
    items: list[CapExItem]
    periods: int
    periods_per_year: int

    def compute(self) -> dict[str, list[float]]:
        capex = [0.0] * self.periods
        depreciation = [0.0] * self.periods
        fixed_net = [0.0] * self.periods

        for item in self.items:
            if item.period >= self.periods:
                continue
            capex[item.period] += item.amount
            life_periods = item.depreciation_years * self.periods_per_year
            per_period_dep = item.amount / life_periods
            for t in range(item.period, min(item.period + life_periods, self.periods)):
                depreciation[t] += per_period_dep

        cum_capex = 0.0
        cum_dep = 0.0
        for t in range(self.periods):
            cum_capex += capex[t]
            cum_dep += depreciation[t]
            fixed_net[t] = cum_capex - cum_dep

        return {
            "capex_spend": capex,
            "depreciation": depreciation,
            "fixed_assets_net": fixed_net,
        }
