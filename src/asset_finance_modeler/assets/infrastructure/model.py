"""InfrastructureModel — main orchestrator for infrastructure asset modelling.

Implements the FinancialModel protocol and wires together all computation
engines in a fixed pipeline:

  degradation → production → revenue → CAPEX → OPEX → incentives →
  P&L → debt sizing → P&L (with interest) → cash flow → balance →
  debt metrics → valuation → KPIs → FinancialOutput
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from asset_finance_modeler.assets.infrastructure.engines.capex import compute_capex
from asset_finance_modeler.assets.infrastructure.engines.opex import compute_opex
from asset_finance_modeler.assets.infrastructure.engines.production import compute_production
from asset_finance_modeler.assets.infrastructure.engines.revenue import compute_revenue
from asset_finance_modeler.assets.infrastructure.schema import InfrastructureModelConfig
from asset_finance_modeler.assets.saas.schema import DebtInstrument
from asset_finance_modeler.core.degradation import (
    degradation_cycle_based,
    degradation_none,
    degradation_time_based,
    degradation_usage_based,
)
from asset_finance_modeler.core.drivers import AmortizationSchedule
from asset_finance_modeler.core.financing import (
    DebtEngine,
    compute_waterfall_dscr,
    size_debt,
)
from asset_finance_modeler.core.incentives import compute_incentives
from asset_finance_modeler.core.protocols import FinancialOutput, ProjectKPIs
from asset_finance_modeler.core.statements import (
    BalanceBuilder,
    CashFlowBuilder,
    PnLBuilder,
    compute_debt_metrics,
)
from asset_finance_modeler.core.valuation import (
    compute_dcf,
    compute_discounted_payback,
    compute_irr,
    compute_lcoe,
)

__all__ = ["InfrastructureModel"]

_PPY = {"M": 12, "Q": 4, "Y": 1}
_PERIOD_DAYS = {"M": 30, "Q": 91, "Y": 365}


@dataclass
class InfrastructureModel:
    config: InfrastructureModelConfig
    config_schema = InfrastructureModelConfig  # satisfies FinancialModel protocol

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> FinancialOutput:
        cfg = self.config
        n = cfg.meta.horizon.periods
        ppy = _PPY[cfg.meta.horizon.frequency]
        period_days = _PERIOD_DAYS[cfg.meta.horizon.frequency]

        # 1. Degradation multipliers
        deg = self._compute_degradation(n, ppy)

        # 2. Production
        prod = compute_production(cfg.production, deg, n, ppy)

        # 3. Revenue
        rev = compute_revenue(cfg.revenue, prod, n, ppy)

        # 4. CAPEX + depreciation
        cap = compute_capex(cfg.capex, cfg.production, n, ppy)

        # 5. OPEX
        opx = compute_opex(
            cfg.opex,
            prod["capacity_mw"],
            cap["total_capex"],
            prod["production_mwh"],
            n,
            ppy,
        )

        # 6. Incentives
        inc = compute_incentives(
            items=[item.model_dump() for item in cfg.incentives.items],
            periods=n,
            periods_per_year=ppy,
            production_per_period=prod["production_mwh"],
            total_capex=cap["total_capex"],
        )

        # 7. Combined revenue (market + subsidies + grants)
        total_revenue = [
            rev["total_revenue"][t] + inc["subsidies"][t] + inc["grants"][t]
            for t in range(n)
        ]

        # 8a. First P&L pass — without interest (needed to size debt)
        pnl = self._build_pnl(
            total_revenue=total_revenue,
            opx=opx,
            cap=cap,
            interest_expense=[0.0] * n,
            taxes=cfg.taxes,
        )

        # 8b. Debt sizing (uses EBITDA as CFADS proxy)
        (
            debt_interest,
            debt_principal,
            debt_drawdowns,
            debt_balance,
            senior_ds,
            sub_ds,
        ) = self._compute_debt(pnl["ebitda"], cap, n, ppy, cfg)

        # 8c. Rebuild P&L with actual interest
        pnl = self._build_pnl(
            total_revenue=total_revenue,
            opx=opx,
            cap=cap,
            interest_expense=debt_interest,
            taxes=cfg.taxes,
        )

        # 9. Cash Flow
        cf = CashFlowBuilder(
            net_income=pnl["net_income"],
            depreciation=cap["book_depreciation"],
            revenue=pnl["revenue"],
            cogs=pnl["cogs"],
            dso_days=0,
            dpo_days=0,
            capex=cap["capex_spend"],
            funding_drawdowns=[0.0] * n,
            debt_drawdowns=debt_drawdowns,
            debt_principal_repaid=debt_principal,
            origination_fees=[0.0] * n,
            initial_cash=cfg.meta.initial_cash,
            period_days=period_days,
        ).build()

        # 10. Balance Sheet
        dta_balance = pnl.get("dta_dtl")
        balance = BalanceBuilder(
            cash=cf["cash"],
            ar_balance=cf["ar_balance"],
            fixed_assets_net=cap["fixed_assets_net"],
            debt_outstanding=debt_balance,
            ap_balance=cf["ap_balance"],
            equity_initial=cfg.meta.initial_cash,
            dta_balance=dta_balance,
        ).build()

        # 11. Debt metrics
        debt_metrics = compute_debt_metrics(
            ebitda=pnl["ebitda"],
            ebit=pnl["ebit"],
            interest_expense=debt_interest,
            principal_repaid=debt_principal,
            debt_outstanding=debt_balance,
        )

        # 12. Valuation (DCF on annual FCF)
        fcf = [cf["cfo"][t] + cf["cfi"][t] for t in range(n)]
        years = n // ppy
        fcf_annual = (
            [sum(fcf[y * ppy : (y + 1) * ppy]) for y in range(years)]
            if years > 0
            else fcf
        )
        try:
            val = compute_dcf(
                fcf_series=fcf_annual,
                wacc_annual=cfg.valuation.discount_rate_annual,
                terminal_growth=cfg.valuation.terminal_growth_rate,
                periods_per_year=1,
                terminal_method=cfg.valuation.terminal_method,
            )
        except ValueError:
            val = {
                "pv_explicit": 0.0,
                "terminal_value": 0.0,
                "pv_terminal": 0.0,
                "enterprise_value": 0.0,
            }

        # 13. Project KPIs
        kpis = self._compute_kpis(
            fcf_annual=fcf_annual,
            cap=cap,
            pnl=pnl,
            cap_book_depr=cap["book_depreciation"],
            debt_drawdowns=debt_drawdowns,
            debt_principal=debt_principal,
            debt_balance=debt_balance,
            debt_metrics=debt_metrics,
            senior_ds=senior_ds,
            sub_ds=sub_ds,
            prod=prod,
            opx=opx,
            val=val,
            cfg=cfg,
            ppy=ppy,
            years=years,
        )

        # 14. Summary
        annual_rev_y1 = sum(pnl["revenue"][:ppy]) if n >= ppy else sum(pnl["revenue"])
        last_rev = pnl["revenue"][-1]
        summary: dict[str, float | int] = {
            "total_capex": cap["total_capex"],
            "revenue_y1": annual_rev_y1,
            "ebitda_margin_end": pnl["ebitda"][-1] / last_rev if last_rev > 0 else 0.0,
            "cash_end": cf["cash"][-1],
            "enterprise_value": val["enterprise_value"],
            "irr_project": kpis.irr_project,
            "lcoe": kpis.lcoe if kpis.lcoe is not None else -1.0,
        }

        return FinancialOutput(
            pnl=pnl,
            cashflow=cf,
            balance=balance,
            debt_metrics=debt_metrics,
            revenue_breakdown={
                "streams": rev.get("streams", {}),
                "total": rev["total_revenue"],
            },
            valuation=val,
            sensitivity=None,
            summary=summary,
            inputs_resolved=cfg.model_dump(mode="json"),
            project_kpis=kpis,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_pnl(
        self,
        total_revenue: list[float],
        opx: dict,
        cap: dict,
        interest_expense: list[float],
        taxes,
    ) -> dict:
        tax_dep = cap["tax_depreciation"]
        book_dep = cap["book_depreciation"]
        use_tax_dep = tax_dep != book_dep  # avoid unnecessary DTA tracking

        return PnLBuilder(
            revenue=total_revenue,
            cogs=[0.0] * len(total_revenue),
            opex=opx["total_opex"],
            depreciation=book_dep,
            interest_expense=interest_expense,
            corporate_tax_rate=taxes.corporate_income_tax_rate,
            carryforward_enabled=taxes.tax_loss_carryforward,
            tax_depreciation=tax_dep if use_tax_dep else None,
        ).build()

    def _compute_debt(
        self,
        ebitda: list[float],
        cap: dict,
        n: int,
        ppy: int,
        cfg: InfrastructureModelConfig,
    ) -> tuple[
        list[float], list[float], list[float], list[float], list[float], list[float]
    ]:
        """Size and schedule senior (+ subordinated) debt.

        Returns (interest, principal, drawdowns, balance, senior_ds, sub_ds)
        where senior_ds / sub_ds are the per-period total debt-service series
        for the senior and subordinated tranches (zeros if absent). Interest /
        principal / drawdowns / balance aggregate both tranches.
        """
        debt_interest = [0.0] * n
        debt_principal = [0.0] * n
        debt_drawdowns = [0.0] * n
        debt_balance = [0.0] * n
        senior_ds = [0.0] * n
        sub_ds = [0.0] * n

        instruments: list[DebtInstrument] = []

        if cfg.financing.senior is not None:
            sr = cfg.financing.senior
            total_capex = cap["total_capex"]

            if sr.auto_size:
                sizing = size_debt(
                    cfads=ebitda,
                    dscr_target=sr.dscr_target,
                    dscr_mode=sr.dscr_mode,
                    interest_rate=sr.interest_rate,
                    tenor_periods=sr.tenor_years * ppy,
                    periods_per_year=ppy,
                    max_leverage=cfg.financing.max_leverage,
                    total_capex=total_capex,
                    amortization=sr.amortization,
                    grace_periods=sr.grace_period_months,
                )
                debt_amount = sizing.max_debt if sizing.feasible else 0.0
            else:
                debt_amount = total_capex * cfg.financing.max_leverage

            if debt_amount > 0:
                instruments.append(
                    DebtInstrument(
                        name="Senior",
                        principal=debt_amount,
                        drawdown_period=0,
                        interest_rate_annual=sr.interest_rate,
                        term_months=sr.tenor_years * ppy,
                        grace_period_months=sr.grace_period_months,
                        amortization=sr.amortization,
                    )
                )
                senior_ds = self._debt_service_series(
                    principal=debt_amount,
                    annual_rate=sr.interest_rate,
                    term_periods=sr.tenor_years * ppy,
                    grace_periods=sr.grace_period_months,
                    amortization=sr.amortization,
                    drawdown_period=0,
                    n=n,
                    ppy=ppy,
                )

        sub = cfg.financing.subordinated
        if sub is not None and sub.principal > 0:
            instruments.append(
                DebtInstrument(
                    name="Subordinated",
                    principal=sub.principal,
                    drawdown_period=sub.drawdown_period,
                    interest_rate_annual=sub.interest_rate,
                    term_months=sub.tenor_years * ppy,
                    grace_period_months=sub.grace_period_months,
                    amortization=sub.amortization,
                )
            )
            sub_ds = self._debt_service_series(
                principal=sub.principal,
                annual_rate=sub.interest_rate,
                term_periods=sub.tenor_years * ppy,
                grace_periods=sub.grace_period_months,
                amortization=sub.amortization,
                drawdown_period=sub.drawdown_period,
                n=n,
                ppy=ppy,
            )

        if not instruments:
            return (
                debt_interest,
                debt_principal,
                debt_drawdowns,
                debt_balance,
                senior_ds,
                sub_ds,
            )

        debt_out = DebtEngine(instruments, periods=n, periods_per_year=ppy).compute()

        return (
            debt_out["interest_expense"],
            debt_out["principal_repaid"],
            debt_out["drawdowns"],
            debt_out["balance_outstanding"],
            senior_ds,
            sub_ds,
        )

    @staticmethod
    def _debt_service_series(
        principal: float,
        annual_rate: float,
        term_periods: int,
        grace_periods: int,
        amortization: Literal["french", "bullet", "linear"],
        drawdown_period: int,
        n: int,
        ppy: int,
    ) -> list[float]:
        """Per-period total debt service (interest + principal), padded to n."""
        series = [0.0] * n
        rows = AmortizationSchedule(
            principal=principal,
            annual_rate=annual_rate,
            term_periods=term_periods,
            periods_per_year=ppy,
            kind=amortization,
            grace_periods=grace_periods,
        ).rows()
        for i, row in enumerate(rows):
            t = drawdown_period + i
            if t >= n:
                break
            series[t] += row["total_payment"]
        return series

    def _compute_kpis(
        self,
        fcf_annual: list[float],
        cap: dict,
        pnl: dict,
        cap_book_depr: list[float],
        debt_drawdowns: list[float],
        debt_principal: list[float],
        debt_balance: list[float],
        debt_metrics: dict,
        senior_ds: list[float],
        sub_ds: list[float],
        prod: dict,
        opx: dict,
        val: dict,
        cfg: InfrastructureModelConfig,
        ppy: int,
        years: int,
    ) -> ProjectKPIs:
        total_capex = cap["total_capex"]

        # Project FCF: fcf_annual already includes CAPEX in year 0 via CFI
        project_cf = list(fcf_annual)

        # Equity FCF: equity deployed = capex minus debt drawdown at t=0
        equity_outlay = total_capex - (debt_drawdowns[0] if debt_drawdowns else 0.0)
        equity_cf: list[float] = [-equity_outlay]
        for y in range(years):
            ni_yr = sum(pnl["net_income"][y * ppy : (y + 1) * ppy])
            dep_yr = sum(cap_book_depr[y * ppy : (y + 1) * ppy])
            rep_yr = sum(debt_principal[y * ppy : (y + 1) * ppy])
            equity_cf.append(ni_yr + dep_yr - rep_yr)

        has_debt = sum(debt_balance) > 0

        irr_project = compute_irr(project_cf, 1)
        irr_equity = compute_irr(equity_cf, 1) if has_debt else irr_project

        # LCOE
        total_production = sum(prod["production_mwh"])
        total_costs_pv = total_capex + sum(opx["total_opex"])
        lcoe = (
            compute_lcoe(total_costs_pv, total_production)
            if total_production > 0
            else None
        )

        payback = compute_discounted_payback(
            project_cf, cfg.valuation.discount_rate_annual, 1
        )

        dscr_series = debt_metrics["dscr"]
        positive_dscr = [d for d in dscr_series if 0 < d < float("inf")]
        dscr_min = min(positive_dscr) if positive_dscr else 0.0
        dscr_avg = sum(positive_dscr) / len(positive_dscr) if positive_dscr else 0.0

        # Per-tranche DSCR via the seniority waterfall: each tranche sees CFADS
        # (EBITDA proxy) net of all more-senior tranches' debt service.
        cfads = pnl["ebitda"]
        tranches = [senior_ds]
        has_sub = cfg.financing.subordinated is not None and any(
            ds > 0 for ds in sub_ds
        )
        if has_sub:
            tranches.append(sub_ds)
        tranche_dscrs = compute_waterfall_dscr(cfads, tranches)

        def _reduce(series: list[float]) -> tuple[float, float]:
            active = [d for d in series if 0 < d < float("inf")]
            if not active:
                return 0.0, 0.0
            return min(active), sum(active) / len(active)

        dscr_senior_min, dscr_senior_avg = _reduce(tranche_dscrs[0])
        dscr_subordinated_min = 0.0
        dscr_subordinated_avg = 0.0
        if has_sub:
            dscr_subordinated_min, dscr_subordinated_avg = _reduce(tranche_dscrs[1])

        return ProjectKPIs(
            irr_project=irr_project,
            irr_equity=irr_equity,
            npv=val["enterprise_value"],
            lcoe=lcoe,
            lcos=None,
            payback_years=payback,
            dscr_series=dscr_series,
            dscr_min=dscr_min,
            dscr_avg=dscr_avg,
            discount_rate_used=cfg.valuation.discount_rate_annual,
            debt_sizing=None,
            dscr_senior_min=dscr_senior_min,
            dscr_senior_avg=dscr_senior_avg,
            dscr_subordinated_min=dscr_subordinated_min,
            dscr_subordinated_avg=dscr_subordinated_avg,
        )

    def _compute_degradation(self, periods: int, ppy: int) -> list[float]:
        deg = self.config.degradation

        if deg.type == "time_based":
            return degradation_time_based(periods, deg.annual_rate, ppy)

        if deg.type == "cycle_based":
            prod = self.config.production
            cpd = getattr(prod, "cycles_per_day", 1.0)
            cycles_per_period = cpd * (365.0 / ppy)
            return degradation_cycle_based(
                periods,
                cycles_per_period,
                deg.capacity_fade_per_cycle,
                deg.calendar_fade_annual,
                ppy,
                deg.eol_capacity_pct,
            )

        if deg.type == "usage_based":
            prod = self.config.production
            availability = getattr(prod, "availability", 1.0)
            hours = 8760.0 / ppy * availability
            return degradation_usage_based(periods, hours, deg.efficiency_loss_per_1000h)

        # deg.type == "none" (or anything unrecognised)
        return degradation_none(periods)
