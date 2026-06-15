from dataclasses import dataclass

from asset_finance_modeler.core.drivers import expand_growth
from asset_finance_modeler.core.financing import DebtEngine

from .schema import CapExItem, COGSConfig, DebtInstrument, OpexConfig, RevenueSource


@dataclass
class CohortRevenueEngine:
    sources: list[RevenueSource]
    periods: int
    periods_per_year: int = 12

    def compute(self) -> dict[str, list[float]]:
        ppy = self.periods_per_year
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
            base_price = src.pricing.per_unit_per_period
            setup_fee = src.pricing.setup_one_time
            # P2-5: annual price escalation steps the per-unit price up at each
            # year boundary (compounded yearly). 0 → flat price (unchanged).
            esc = src.pricing.price_escalation_annual
            price_at = [base_price * (1 + esc) ** (t // ppy) for t in range(self.periods)]
            # P2-5: gross revenue retention erodes per-cohort revenue beyond logo
            # churn (down-sell / contraction), applied per elapsed year; 1.0 →
            # no extra erosion. Expansion revenue compounds monthly on the live
            # base; 0 → none. Both default to no-op.
            grr = src.retention.gross_revenue_retention
            expansion = src.retention.expansion_revenue_pct

            au = [0.0] * self.periods
            ac = [0.0] * self.periods
            stp = [0.0] * self.periods
            sub = [0.0] * self.periods
            for cohort_t, new_u in enumerate(new_units_series):
                new_c = new_u / avg_u_per_c if avg_u_per_c > 0 else 0
                stp[cohort_t] += new_c * setup_fee
                for t in range(cohort_t, self.periods):
                    elapsed = t - cohort_t
                    survival = (1 - churn) ** elapsed
                    au[t] += new_u * survival
                    ac[t] += new_c * survival
                    # Revenue for this cohort at t: surviving units × current
                    # price × net-revenue-retention factors (GRR down-sell per
                    # year + monthly expansion up-sell).
                    nrr = grr ** (elapsed / ppy) * (1 + expansion) ** elapsed
                    sub[t] += new_u * survival * price_at[t] * nrr

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
    new_customers: list[float] | None = None

    def compute(self) -> dict[str, list[float]]:
        per_unit = self.cogs.per_active_unit.monthly_cost_eur()
        support = self.cogs.per_active_customer.support_eur
        # P2-5: one-time onboarding cost charged once per NEW customer in the
        # period it is acquired; 0 → none (unchanged).
        onboarding = self.cogs.per_active_customer.onboarding_one_time_eur
        new_c = self.new_customers if self.new_customers is not None else [0.0] * len(self.active_units)
        variable_unit = [per_unit * u for u in self.active_units]
        variable_customer = [
            support * c + onboarding * new_c[t]
            for t, c in enumerate(self.active_customers)
        ]
        total = [v + c for v, c in zip(variable_unit, variable_customer)]
        return {
            "variable_per_unit": variable_unit,
            "variable_per_customer": variable_customer,
            "total_cogs": total,
        }


def _expand_opex_bucket(value: float | list[float], periods: int) -> list[float]:
    return expand_growth(value, periods)


def _inflate_scalar_bucket(
    value: float | list[float],
    periods: int,
    periods_per_year: int,
    inflation: float,
) -> list[float]:
    """Expand an opex bucket, escalating SCALAR buckets by inflation per year.

    A scalar bucket grows at ``inflation`` compounded at each year boundary
    (P2-5: inflation_annual). A bucket supplied as an explicit per-period list
    is an override and is left untouched (no auto-escalation). inflation 0 →
    flat (legacy behaviour).
    """
    base = expand_growth(value, periods)
    if inflation == 0 or isinstance(value, list):
        return base
    return [base[t] * (1 + inflation) ** (t // periods_per_year) for t in range(periods)]


@dataclass
class OpexEngine:
    opex: OpexConfig
    periods: int
    payroll_taxes_pct: float = 0.0
    inflation_annual: float = 0.0
    periods_per_year: int = 12

    def compute(self) -> dict[str, list[float]]:
        team_cost = [0.0] * self.periods
        # P2-5: employer payroll-tax burden applied on top of the gross team
        # cost. 0 → no burden (unchanged).
        burden = 1.0 + self.payroll_taxes_pct
        for role in self.opex.team:
            for t in range(self.periods):
                team_cost[t] += role.headcount_at_period(t) * role.monthly_cost * burden

        ppy = self.periods_per_year
        infl = self.inflation_annual
        infra = _inflate_scalar_bucket(self.opex.infra_fixed_eur, self.periods, ppy, infl)
        marketing = _inflate_scalar_bucket(self.opex.marketing_eur, self.periods, ppy, infl)
        legal = _inflate_scalar_bucket(self.opex.legal_admin_eur, self.periods, ppy, infl)
        other = _inflate_scalar_bucket(self.opex.other_eur, self.periods, ppy, infl)

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
