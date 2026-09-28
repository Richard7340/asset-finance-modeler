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
from asset_finance_modeler.core.capex_events import (
    apply_capex_events,
    apply_degradation_resets,
)
from asset_finance_modeler.core.degradation import (
    degradation_cycle_based,
    degradation_none,
    degradation_time_based,
    degradation_usage_based,
)
from asset_finance_modeler.core.drivers import AmortizationSchedule
from asset_finance_modeler.core.financing import (
    DebtEngine,
    compute_dsra,
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
    compute_moic,
    compute_recovery_multiple,
)

__all__ = ["InfrastructureModel"]

_PPY = {"M": 12, "Q": 4, "Y": 1}
_PERIOD_DAYS = {"M": 30, "Q": 91, "Y": 365}


def _months_to_periods(months: int, ppy: int) -> int:
    """Convert a month count to model periods for the given frequency.

    Monthly (ppy=12) → 1:1. Quarterly (ppy=4) → months/3. Annual (ppy=1) →
    months/12. Rounded to the nearest whole period."""
    if months <= 0:
        return 0
    return int(round(months * ppy / 12.0))


def _timeline_periods(timeline, ppy: int) -> tuple[int, int, int]:
    """Resolve the development/construction timeline into model periods.

    Returns (pre_construction, construction, cod) where:
      * pre_construction = development + permitting periods (capex idle before
        the construction drawdown starts — kept simple: drawdown begins at COD-
        grid window; here we start the construction spend right after permitting)
      * construction      = construction periods (over which capex is drawn)
      * cod               = total offset to commercial operation =
                            development + permitting + construction + grid_connection
    Production/revenue begin at period ``cod``; capex is spread over the
    ``construction`` window beginning at ``pre_construction``."""
    dev = _months_to_periods(timeline.development_months, ppy)
    permit = _months_to_periods(timeline.permitting_months, ppy)
    constr = _months_to_periods(timeline.construction_months, ppy)
    grid = _months_to_periods(timeline.grid_connection_months, ppy)
    pre = dev + permit
    cod = dev + permit + constr + grid
    return pre, constr, cod


def _spread_capex(
    total_capex: float,
    pre_construction: int,
    construction: int,
    schedule: list[float] | None,
    n: int,
) -> list[float]:
    """Spread total capex over the construction window.

    Capex lands across ``construction`` periods starting at ``pre_construction``.
    With a ``construction_drawdown_schedule`` (weights, normalised), capex is
    drawn per its shape; otherwise it is spread evenly. If construction == 0
    (no timeline), it all lands at period 0 — unchanged legacy behaviour. Any
    weight whose period falls beyond the horizon is clamped into the last period
    so the total still reconciles to total_capex."""
    spend = [0.0] * n
    if total_capex == 0 or n == 0:
        return spend
    if construction <= 0:
        spend[0] = total_capex
        return spend

    if schedule:
        weights = [float(w) for w in schedule]
    else:
        weights = [1.0] * construction
    wsum = sum(weights)
    if wsum <= 0:
        spend[0] = total_capex
        return spend
    weights = [w / wsum for w in weights]

    for i, w in enumerate(weights):
        t = pre_construction + i
        if t >= n:
            t = n - 1
        spend[t] += total_capex * w
    return spend


@dataclass
class InfrastructureModel:
    config: InfrastructureModelConfig
    config_schema = InfrastructureModelConfig  # satisfies FinancialModel protocol

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> FinancialOutput:
        # Un tramo de deuda con plazo 0 es que no hay tal tramo (27-sep: para
        # "100 % equity" un agente puso mezzanine.tenor_years: 0 y el motor
        # fallaba con "grace_periods >= term_periods").
        fin = self.config.financing
        vacios = {
            k: None for k in ("senior", "mezzanine", "subordinated")
            if getattr(fin, k) is not None and getattr(getattr(fin, k), "tenor_years", 1) <= 0
        }
        if vacios:
            self.config = self.config.model_copy(update={"financing": fin.model_copy(update=vacios)})
        cfg = self.config
        n = cfg.meta.horizon.periods
        ppy = _PPY[cfg.meta.horizon.frequency]
        period_days = _PERIOD_DAYS[cfg.meta.horizon.frequency]

        # 1. Degradation multipliers (operating-time shape, from first op period)
        deg = self._compute_degradation(n, ppy)

        # 1c. Construction / permitting timeline → commercial-operation offset.
        #     Production (and therefore revenue) begin at COD; capex is spread
        #     over the construction window. A fully-zero timeline → no offset.
        pre_construction, construction, cod = _timeline_periods(cfg.timeline, ppy)

        # 1d. Defer the degradation profile to COD: the operating degradation
        #     shape starts at COD, not at model period 0. Resets below are then
        #     applied on this deferred curve at their CALENDAR (absolute) period
        #     so a "year 15" repowering lands at calendar period 15*ppy.
        if cod > 0:
            shifted = [deg[0]] * n
            for t in range(cod, n):
                shifted[t] = deg[t - cod]
            deg = shifted

        # 1b. Repowering / augmentation resets: events flagged
        #     resets_degradation restore the curve to nameplate at their period
        #     (calendar/absolute), then the degradation shape restarts.
        reset_periods = [
            e.year * ppy for e in cfg.capex_events if e.resets_degradation
        ]
        if reset_periods:
            deg = apply_degradation_resets(deg, reset_periods)

        # 1e. Repowering con mas potencia: desde su periodo, la produccion sube.
        uplifts = [(e.year * ppy, e.capacity_uplift_pct) for e in cfg.capex_events if e.capacity_uplift_pct]
        if uplifts:
            factor = [1.0] * n
            for start, pct in uplifts:
                for t in range(max(start, 0), n):
                    factor[t] *= 1.0 + pct
            deg = [deg[t] * factor[t] for t in range(n)]

        # 2. Production (degradation already deferred to COD)
        prod = compute_production(cfg.production, deg, n, ppy)
        # 2b. Zero production before COD (development/permitting/construction/
        #     grid-connection): no output, hence no revenue, during that window.
        if cod > 0:
            prod = self._zero_production_before(prod, cod, n)

        # 2c. Recortes (curtailment, 26-sep): energia que no se puede verter.
        prod = self._apply_curtailment(prod, cfg.losses, n, ppy, cod)

        # 3. Revenue (zero during construction because production is zero there)
        rev = compute_revenue(cfg.revenue, prod, n, ppy)

        # 4. CAPEX + depreciation
        cap = compute_capex(cfg.capex, cfg.production, n, ppy)
        # 4a-bis. Spread capex over the construction window (instead of a single
        #         period-0 lump) per the drawdown schedule, if a timeline exists.
        if construction > 0:
            cap["capex_spend"] = _spread_capex(
                cap["total_capex"],
                pre_construction,
                construction,
                cfg.timeline.construction_drawdown_schedule,
                n,
            )

        # 4b. CAPEX events (repowering / augmentation injections): add each
        #     event amount to the spend at its period (lands in investing cash
        #     flow / reduces FCF) and to the headline total CAPEX.
        # Lo que se invierte al principio: con esto se dimensiona la deuda y
        # el capital del socio (29-sep: una repotenciacion del anio 20 subia el
        # prestamo de 2,5 a 2,86 M y se contaba como capital del anio 0).
        cap["capex_inicial"] = cap["total_capex"]
        if cfg.capex_events:
            cap["capex_spend"] = apply_capex_events(
                cap["capex_spend"],
                [(e.year, e.amount) for e in cfg.capex_events],
                ppy,
            )
            cap["total_capex"] += sum(
                e.amount
                for e in cfg.capex_events
                if 0 <= e.year * ppy < n
            )
            # 4c. Depreciate each event from its event period. Straight-line over
            #     the REMAINING periods to horizon end, so the event is fully
            #     expensed within the model and total book depreciation
            #     reconciles to total_capex (P1-5). Fixed-assets-net steps up by
            #     the event amount and then declines with the added depreciation.
            self._depreciate_capex_events(cap, cfg.capex_events, n, ppy)

        # 5. OPEX
        opx = compute_opex(
            cfg.opex,
            prod["capacity_mw"],
            cap["total_capex"],
            prod["production_mwh"],
            n,
            ppy,
            production_config=cfg.production,
        )

        # 5b. Costes propios, IVPEE y desmantelamiento (26-sep).
        opx = self._extra_opex(opx, cfg, prod, rev["total_revenue"], n, ppy, cod)

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
            mezz_ds,
        ) = self._compute_debt(pnl["ebitda"], cap, n, ppy, cfg, cod)

        # 8b-bis. Cash sweep (P2-2): when enabled, excess operating cash above the
        #         trigger DSCR prepays senior debt, accelerating the paydown and
        #         cutting future interest. Recomputes debt_interest / principal /
        #         balance in place (drawdowns untouched). Disabled → no change.
        total_ds = [senior_ds[t] + mezz_ds[t] + sub_ds[t] for t in range(n)]
        if cfg.financing.cash_sweep.enabled:
            debt_interest, debt_principal, debt_balance = self._apply_cash_sweep(
                cfads=pnl["ebitda"],
                total_debt_service=total_ds,
                interest=debt_interest,
                principal=debt_principal,
                balance=debt_balance,
                drawdowns=debt_drawdowns,
                sweep=cfg.financing.cash_sweep,
                ppy=ppy,
                senior_rate=(
                    cfg.financing.senior.interest_rate
                    if cfg.financing.senior is not None
                    else 0.0
                ),
            )

        # 8b-ter. Comision de apertura sobre la deuda dispuesta: gasto financiero
        #         (y caja) en el periodo de cada disposicion.
        fee = cfg.financing.upfront_fee_pct
        if fee > 0:
            debt_interest = [debt_interest[t] + debt_drawdowns[t] * fee for t in range(n)]

        # 8c. Rebuild P&L with actual interest
        pnl = self._build_pnl(
            total_revenue=total_revenue,
            opx=opx,
            cap=cap,
            interest_expense=debt_interest,
            taxes=cfg.taxes,
        )

        # 8d. DSRA (P2-1): a debt service reserve account funded to dsra_months of
        #     forward debt service. The reserve is RESTRICTED cash — funding it
        #     (when the target rises) is a cash use; releasing it (as debt winds
        #     down) is a cash source. We model the per-period change in the
        #     reserve as a financing outflow/inflow so free cash reflects the
        #     tied-up reserve, and hold the reserve balance on the balance sheet.
        # ``total_ds`` is the scheduled (pre-sweep) debt service: it defines the
        # forward reserve requirement regardless of sweep prepayments.
        dsra_balance = compute_dsra(
            debt_service=total_ds,
            dsra_months=cfg.financing.reserves.dsra_months,
            periods_per_year=ppy,
        )
        # Change in reserve per period: +funding (cash out), -release (cash in).
        dsra_funding = [
            dsra_balance[t] - (dsra_balance[t - 1] if t > 0 else 0.0)
            for t in range(n)
        ]
        # A reserve build is a financing USE of cash → negative funding flow.
        funding_flows = [-dsra_funding[t] for t in range(n)]

        # 9. Cash Flow
        cf = CashFlowBuilder(
            net_income=pnl["net_income"],
            depreciation=cap["book_depreciation"],
            revenue=pnl["revenue"],
            cogs=pnl["cogs"],
            dso_days=0,
            dpo_days=0,
            capex=cap["capex_spend"],
            funding_drawdowns=funding_flows,
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
            dsra_balance=dsra_balance,
        ).build()

        # 11. Debt metrics
        debt_metrics = compute_debt_metrics(
            ebitda=pnl["ebitda"],
            ebit=pnl["ebit"],
            interest_expense=debt_interest,
            principal_repaid=debt_principal,
            debt_outstanding=debt_balance,
        )

        # 12. Valuation (DCF on UNLEVERED annual FCF — financing-independent).
        #     The project EV / NPV / IRR must not move with leverage or cash
        #     sweep (E3). Unlevered FCF = EBIT*(1-t) + D&A - capex ± ΔWC,
        #     discounted at WACC. The levered view (interest + principal) lives
        #     under npv_equity / irr_equity in _compute_kpis. (Business/SaaS/SVJ
        #     already value on unlevered FCF; this brings infra in line.)
        years = n // ppy
        tax_rate = cfg.taxes.corporate_income_tax_rate
        # ΔWC per period (infra uses dso=dpo=0 → 0, but kept for correctness).
        delta_wc = [cf["delta_ar"][t] - cf["delta_ap"][t] for t in range(n)]
        unlevered_fcf = [
            (pnl["ebit"][t] * (1.0 - tax_rate) if pnl["ebit"][t] > 0 else pnl["ebit"][t])
            + cap["book_depreciation"][t]
            - cap["capex_spend"][t]
            - delta_wc[t]
            for t in range(n)
        ]
        fcf_annual = (
            [sum(unlevered_fcf[y * ppy : (y + 1) * ppy]) for y in range(years)]
            if years > 0
            else unlevered_fcf
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
            dsra_funding_flows=funding_flows,
            debt_balance=debt_balance,
            debt_metrics=debt_metrics,
            senior_ds=senior_ds,
            sub_ds=sub_ds,
            mezz_ds=mezz_ds,
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

        # El calendario de la deuda por periodo (28-sep): la app lo enseña
        # año a año (saldo, intereses, amortización, disposiciones).
        debt_metrics = {
            **debt_metrics,
            "interest": list(debt_interest),
            "principal": list(debt_principal),
            "drawdowns": list(debt_drawdowns),
            "balance": list(debt_balance),
        }
        return FinancialOutput(
            pnl=pnl,
            cashflow=cf,
            balance=balance,
            debt_metrics=debt_metrics,
            revenue_breakdown={
                "streams": rev.get("streams", {}),
                "total": rev["total_revenue"],
                # La producción por periodo (28-sep): para anotar la real y compararla.
                "production_mwh": list(prod.get("production_mwh") or []),
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

    @staticmethod
    def _apply_cash_sweep(
        cfads: list[float],
        total_debt_service: list[float],
        interest: list[float],
        principal: list[float],
        balance: list[float],
        drawdowns: list[float],
        sweep,
        ppy: int,
        senior_rate: float,
    ) -> tuple[list[float], list[float], list[float]]:
        """Sweep excess operating cash to prepay debt (P2-2).

        Per period, the available excess cash is CFADS net of the scheduled debt
        service. When the period DSCR (CFADS / scheduled service) clears the
        ``trigger_dscr``, ``sweep_pct`` of that excess is applied as EXTRA
        principal prepayment, reducing the outstanding balance. Interest in
        subsequent periods is recomputed on the (lower) outstanding balance at
        the senior period rate, so the sweep both accelerates paydown and cuts
        total interest. Drawdowns are untouched.

        This is an aggregate-tranche approximation (one blended balance at the
        senior rate); it is conservative and disabled by default, so it never
        affects a config that does not opt in.
        """
        n = len(balance)
        period_rate = senior_rate / ppy
        new_interest = list(interest)
        new_principal = list(principal)
        new_balance = list(balance)

        # Total principal drawn — the hard cap on cumulative repayment. The
        # outstanding balance can never be reduced below zero, so the sum of all
        # principal repayments (scheduled + swept) must equal exactly this.
        total_drawn = sum(drawdowns)

        outstanding = 0.0  # running balance carried period to period
        repaid_cum = 0.0  # cumulative principal repaid (scheduled + swept)
        for t in range(n):
            begin_bal = max(outstanding + drawdowns[t], 0.0)
            # Recompute interest on the (reduced) outstanding balance; scheduled
            # interest was computed on the original, higher balance.
            new_interest[t] = begin_bal * period_rate

            # Scheduled principal, but never more than what is still outstanding
            # (once the swept balance has retired the loan, later scheduled
            # principal must be zeroed — otherwise cumulative repaid exceeds the
            # drawn loan and corrupts CFF/cash/equity metrics).
            sched_principal = min(max(principal[t], 0.0), begin_bal)

            scheduled_ds = total_debt_service[t]
            dscr = cfads[t] / scheduled_ds if scheduled_ds > 0 else float("inf")

            # Balance remaining after the (capped) scheduled principal.
            after_sched = begin_bal - sched_principal

            sweep_amt = 0.0
            if dscr >= sweep.trigger_dscr and after_sched > 0:
                excess = cfads[t] - scheduled_ds
                if excess > 0:
                    sweep_amt = min(sweep.sweep_pct * excess, after_sched)

            period_repaid = sched_principal + sweep_amt
            # Hard cap: never repay more than the drawn principal in aggregate.
            period_repaid = min(period_repaid, total_drawn - repaid_cum)
            period_repaid = max(period_repaid, 0.0)

            repaid_cum += period_repaid
            new_principal[t] = period_repaid
            outstanding = max(begin_bal - period_repaid, 0.0)
            new_balance[t] = outstanding

        return new_interest, new_principal, new_balance

    @staticmethod
    def _depreciate_capex_events(cap: dict, events, n: int, ppy: int) -> None:
        """Depreciate each capex event from its event period (mutates ``cap``).

        Each event is straight-lined over the periods remaining from its event
        period to the horizon end, so it is fully expensed within the model and
        total book/tax depreciation reconciles to total_capex (P1-5). The book
        value (fixed_assets_net) steps up by the event amount at the event period
        and then declines with the added depreciation.
        """
        book = cap["book_depreciation"]
        tax = cap["tax_depreciation"]
        fan = cap["fixed_assets_net"]
        for e in events:
            start = e.year * ppy
            if start < 0 or start >= n:
                continue
            remaining = n - start
            per_period = e.amount / remaining
            book_add = [0.0] * n
            for t in range(start, n):
                book[t] += per_period
                tax[t] += per_period
                book_add[t] = per_period
            # Book value: + event amount at start, then -cumulative added depr.
            cumulative = 0.0
            for t in range(start, n):
                cumulative += book_add[t]
                fan[t] += max(e.amount - cumulative, 0.0)

    @staticmethod
    def _zero_production_before(prod: dict, cod: int, n: int) -> dict:
        """Zero every per-period production series for the first ``cod`` periods.

        The degradation curve was already deferred to COD upstream, so periods
        ``cod..n`` already carry the operating profile; this just blanks the
        construction window. Scalar keys (capacity_mw, …) are left untouched."""
        out = dict(prod)
        for key, series in prod.items():
            if isinstance(series, list) and len(series) == n:
                blanked = list(series)
                for t in range(min(cod, n)):
                    blanked[t] = 0.0
                out[key] = blanked
        return out

    @staticmethod
    def _apply_curtailment(prod: dict, losses, n: int, ppy: int, cod: int) -> dict:
        """Quita a la produccion el recorte del anio (fijo o por curva, contada
        desde la puesta en marcha). Sin recorte, la produccion no cambia."""
        curva = losses.curtailment_curve
        if not curva and not losses.curtailment_pct and not losses.equipment_events:
            return prod
        out = dict(prod)
        serie = list(prod.get("production_mwh") or [])
        for t in range(min(n, len(serie))):
            anio = max(0, (t - cod) // ppy)
            pct = (curva[min(anio, len(curva) - 1)] if curva else losses.curtailment_pct) or 0.0
            serie[t] *= max(0.0, 1.0 - min(pct, 1.0))
            # Caidas por equipos en esos anios de operacion (1 = el primero).
            if t >= cod:
                for e in losses.equipment_events:
                    if e.year - 1 <= anio < e.year - 1 + e.years:
                        serie[t] *= max(0.0, 1.0 - e.loss_pct)
        out["production_mwh"] = serie
        return out

    @staticmethod
    def _extra_opex(opx: dict, cfg, prod: dict, energy_revenue: list[float], n: int, ppy: int, cod: int) -> dict:
        """Lineas de coste propias, IVPEE sobre la venta de energia y dotacion al
        desmantelamiento, sumadas a la OPEX (con su detalle por linea)."""
        o = cfg.opex
        extra: dict[str, list[float]] = {}
        cap_mw = prod.get("capacity_mw") or 0.0
        cap_mw = float(cap_mw[0] if isinstance(cap_mw, list) and cap_mw else cap_mw or 0.0)
        mwh = prod.get("production_mwh") or [0.0] * n
        for linea in o.other_lines:
            esc = o.opex_escalation_pct_yr if linea.escalation_pct_yr is None else linea.escalation_pct_yr
            serie = [0.0] * n
            for t in range(cod, n):
                factor = (1 + esc) ** ((t - cod) // ppy)
                fijo = (linea.eur_yr + linea.eur_per_mw_yr * cap_mw) / ppy
                serie[t] = (fijo + linea.eur_per_mwh * mwh[t]) * factor
            extra[linea.name] = serie
        if o.generation_tax_pct:
            extra["IVPEE"] = [max(energy_revenue[t], 0.0) * o.generation_tax_pct for t in range(n)]
        d = o.decommissioning
        if d is not None and d.cost_eur > 0:
            periodos = min(d.accrue_years * ppy, n)
            extra["Desmantelamiento"] = [0.0] * (n - periodos) + [d.cost_eur / periodos] * periodos
        if not extra:
            return opx
        out = dict(opx)
        out["total_opex"] = [opx["total_opex"][t] + sum(v[t] for v in extra.values()) for t in range(n)]
        out["lineas_extra"] = extra
        return out

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
        cod: int = 0,
    ) -> tuple[
        list[float], list[float], list[float], list[float],
        list[float], list[float], list[float],
    ]:
        """Size and schedule senior (+ mezzanine + subordinated) debt.

        Returns (interest, principal, drawdowns, balance, senior_ds, sub_ds,
        mezz_ds) where senior_ds / mezz_ds / sub_ds are the per-period total
        debt-service series for each tranche (zeros if absent). Interest /
        principal / drawdowns / balance aggregate all tranches.

        Seniority order is senior > mezzanine > subordinated. The mezzanine
        (P2-3) is auto-sized on residual CFADS (EBITDA proxy net of the senior
        debt service) to its own ``dscr_target``, drawn at financial close and
        deferred to COD like the senior tranche.

        ``cod`` is the commercial-operation offset in periods (from the
        construction/permitting timeline). With cod>0 the standard project-
        finance treatment applies: debt is drawn at financial close (period 0)
        but interest during construction is CAPITALIZED (IDC) and amortization
        begins at COD. DSCR is therefore measured over operating periods only
        (construction periods carry no debt service). cod==0 => legacy
        behaviour, debt amortizes from period 0.
        """
        debt_interest = [0.0] * n
        debt_principal = [0.0] * n
        debt_drawdowns = [0.0] * n
        debt_balance = [0.0] * n
        senior_ds = [0.0] * n
        sub_ds = [0.0] * n
        mezz_ds = [0.0] * n

        instruments: list[DebtInstrument] = []
        senior_amount = 0.0

        if cfg.financing.senior is not None:
            sr = cfg.financing.senior
            total_capex = cap.get("capex_inicial", cap["total_capex"])

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
                    deferral_periods=cod,
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
                        deferral_periods=cod,
                    )
                )
                senior_amount = debt_amount
                senior_ds = self._debt_service_series(
                    principal=debt_amount,
                    annual_rate=sr.interest_rate,
                    term_periods=sr.tenor_years * ppy,
                    grace_periods=sr.grace_period_months,
                    amortization=sr.amortization,
                    drawdown_period=0,
                    n=n,
                    ppy=ppy,
                    deferral_periods=cod,
                )

        # Mezzanine (P2-3): auto-sized on residual CFADS net of the senior debt
        # service, to its own DSCR target. Sits between senior and sub in the
        # stack/waterfall; drawn at close, amortization deferred to COD.
        mezz = cfg.financing.mezzanine
        if mezz is not None:
            residual_cfads = [ebitda[t] - senior_ds[t] for t in range(n)]
            headroom_capex = max(cap.get("capex_inicial", cap["total_capex"]) - senior_amount, 0.0)
            mezz_sizing = size_debt(
                cfads=residual_cfads,
                dscr_target=mezz.dscr_target,
                dscr_mode="min",
                interest_rate=mezz.interest_rate,
                tenor_periods=mezz.tenor_years * ppy,
                periods_per_year=ppy,
                max_leverage=1.0,  # cap is the remaining (post-senior) capex
                total_capex=headroom_capex,
                amortization="french",
                grace_periods=0,
                deferral_periods=cod,
            )
            mezz_amount = mezz_sizing.max_debt if mezz_sizing.feasible else 0.0
            if mezz_amount > 0:
                instruments.append(
                    DebtInstrument(
                        name="Mezzanine",
                        principal=mezz_amount,
                        drawdown_period=0,
                        interest_rate_annual=mezz.interest_rate,
                        term_months=mezz.tenor_years * ppy,
                        grace_period_months=0,
                        amortization="french",
                        deferral_periods=cod,
                    )
                )
                mezz_ds = self._debt_service_series(
                    principal=mezz_amount,
                    annual_rate=mezz.interest_rate,
                    term_periods=mezz.tenor_years * ppy,
                    grace_periods=0,
                    amortization="french",
                    drawdown_period=0,
                    n=n,
                    ppy=ppy,
                    deferral_periods=cod,
                )

        sub = cfg.financing.subordinated
        if sub is not None and sub.principal > 0:
            # Sub deferral runs from its own drawdown to COD, so amortization
            # still starts at COD (relative to the sub's drawdown period).
            sub_defer = max(0, cod - sub.drawdown_period)
            instruments.append(
                DebtInstrument(
                    name="Subordinated",
                    principal=sub.principal,
                    drawdown_period=sub.drawdown_period,
                    interest_rate_annual=sub.interest_rate,
                    term_months=sub.tenor_years * ppy,
                    grace_period_months=sub.grace_period_months,
                    amortization=sub.amortization,
                    deferral_periods=sub_defer,
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
                deferral_periods=sub_defer,
            )

        if not instruments:
            return (
                debt_interest,
                debt_principal,
                debt_drawdowns,
                debt_balance,
                senior_ds,
                sub_ds,
                mezz_ds,
            )

        debt_out = DebtEngine(instruments, periods=n, periods_per_year=ppy).compute()

        return (
            debt_out["interest_expense"],
            debt_out["principal_repaid"],
            debt_out["drawdowns"],
            debt_out["balance_outstanding"],
            senior_ds,
            sub_ds,
            mezz_ds,
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
        deferral_periods: int = 0,
    ) -> list[float]:
        """Per-period total debt service (interest + principal), padded to n.

        P3-1 — amortization convention: the per-tranche debt service is built on
        the ANNUAL convention (one amortization row per year) and then spread
        EVENLY across the ``ppy`` periods of each year. This is the SAME
        convention as the consolidated/SVJ path
        (``HybridProject._tranche_debt_service``), so the SAME loan produces the
        SAME annual debt service in both paths. (Previously this series amortized
        monthly — periods_per_year=ppy, term=tenor*ppy — which over-counted
        interest within the year by ~1-3% vs the annual path, an inconsistency.)

        Term/grace/deferral are passed in PERIODS (the caller's convention) and
        converted to YEARS for the annual schedule. The resulting annual payment
        is divided by ``ppy`` so the per-period DSCR series keeps its length and
        the cash-sweep / DSRA consumers see a smooth service profile whose annual
        sum equals the annual-convention service.

        ``deferral_periods`` defers amortization to COD (no service during
        construction; face-value principal — construction interest funded by
        equity/IDC reserve)."""
        series = [0.0] * n
        # Period -> year conversions (round to the nearest whole year; callers
        # pass whole-year tenors * ppy, grace/deferral in months).
        term_years = max(1, round(term_periods / ppy))
        grace_years = round(grace_periods / ppy)
        deferral_years = round(deferral_periods / ppy)
        rows = AmortizationSchedule(
            principal=principal,
            annual_rate=annual_rate,
            term_periods=term_years,
            periods_per_year=1,
            kind=amortization,
            grace_periods=grace_years,
            deferral_periods=deferral_years,
        ).rows()
        for year, row in enumerate(rows):
            # Spread the annual payment evenly across this year's ppy periods.
            per_period = row["total_payment"] / ppy
            for sub in range(ppy):
                t = drawdown_period + year * ppy + sub
                if t >= n:
                    return series
                series[t] += per_period
        return series

    def _compute_kpis(
        self,
        fcf_annual: list[float],
        cap: dict,
        pnl: dict,
        cap_book_depr: list[float],
        debt_drawdowns: list[float],
        debt_principal: list[float],
        dsra_funding_flows: list[float],
        debt_balance: list[float],
        debt_metrics: dict,
        senior_ds: list[float],
        sub_ds: list[float],
        mezz_ds: list[float],
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
        # Las inversiones posteriores (repotenciacion…) las pone el socio en su anio.
        equity_outlay = cap.get("capex_inicial", total_capex) - (debt_drawdowns[0] if debt_drawdowns else 0.0)
        equity_cf: list[float] = [-equity_outlay]
        eventos_por_anio: dict[int, float] = {}
        for e in cfg.capex_events or []:
            if 0 <= e.year * ppy < len(debt_balance or pnl["net_income"]):
                eventos_por_anio[e.year] = eventos_por_anio.get(e.year, 0.0) + e.amount
        for y in range(years):
            ni_yr = sum(pnl["net_income"][y * ppy : (y + 1) * ppy])
            dep_yr = sum(cap_book_depr[y * ppy : (y + 1) * ppy])
            rep_yr = sum(debt_principal[y * ppy : (y + 1) * ppy])
            # DSRA funding flow (A3): a reserve BUILD ties up cash (financing
            # outflow, negative) so it defers equity distributions; a RELEASE
            # returns cash. So dsra_months directly moves npv_equity/irr_equity —
            # a longer reserve hold lowers equity NPV at Ke. The reserve is fully
            # released by horizon end, so the timing (not the total) is what bites.
            dsra_yr = sum(dsra_funding_flows[y * ppy : (y + 1) * ppy])
            equity_cf.append(ni_yr + dep_yr - rep_yr + dsra_yr - eventos_por_anio.get(y, 0.0))

        has_debt = sum(debt_balance) > 0

        # Reparto al socio (26-sep): sin dividendos los primeros anios pactados
        # ni el anio en que el DSCR incumple el lock-up; lo retenido se paga el
        # primer anio que se pueda (o al final).
        eq = cfg.financing.equity
        if has_debt and (eq.distribution_lock_years > 0 or eq.lockup_dscr):
            ds_total = [senior_ds[t] + mezz_ds[t] + sub_ds[t] for t in range(len(senior_ds))]
            retenido = 0.0
            for y in range(years):
                cfads_y = sum(pnl["ebitda"][y * ppy:(y + 1) * ppy])
                ds_y = sum(ds_total[y * ppy:(y + 1) * ppy])
                bloqueado = y < eq.distribution_lock_years or bool(
                    eq.lockup_dscr and ds_y > 0 and cfads_y / ds_y < eq.lockup_dscr)
                caja = equity_cf[y + 1]
                if bloqueado and caja > 0:
                    retenido += caja
                    equity_cf[y + 1] = 0.0
                elif not bloqueado and retenido:
                    equity_cf[y + 1] = caja + retenido
                    retenido = 0.0
            if retenido and years:
                equity_cf[-1] += retenido
            self._reparto_retenido = True

        irr_project = compute_irr(project_cf, 1)
        irr_equity = compute_irr(equity_cf, 1) if has_debt else irr_project

        # Equity NPV: plain discounted sum of the (finite, levered) equity cashflow
        # at the cost of equity. equity_cf[0] is the year-0 outlay (discounted at
        # t=0), so no terminal value is injected — unlike the project EV DCF.
        ke = cfg.valuation.cost_of_equity_annual or cfg.valuation.discount_rate_annual
        npv_equity = sum(
            cf / ((1 + ke) ** t) for t, cf in enumerate(equity_cf)
        )

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
        # (EBITDA proxy) net of all more-senior tranches' debt service. Order:
        # senior > mezzanine > subordinated.
        cfads = pnl["ebitda"]
        tranches = [senior_ds]
        has_mezz = cfg.financing.mezzanine is not None and any(ds > 0 for ds in mezz_ds)
        mezz_idx = -1
        if has_mezz:
            mezz_idx = len(tranches)
            tranches.append(mezz_ds)
        has_sub = cfg.financing.subordinated is not None and any(
            ds > 0 for ds in sub_ds
        )
        sub_idx = -1
        if has_sub:
            sub_idx = len(tranches)
            tranches.append(sub_ds)
        tranche_dscrs = compute_waterfall_dscr(cfads, tranches)

        def _reduce(series: list[float]) -> tuple[float, float]:
            active = [d for d in series if 0 < d < float("inf")]
            if not active:
                return 0.0, 0.0
            return min(active), sum(active) / len(active)

        dscr_senior_min, dscr_senior_avg = _reduce(tranche_dscrs[0])
        dscr_mezzanine_min = 0.0
        dscr_mezzanine_avg = 0.0
        if has_mezz:
            dscr_mezzanine_min, dscr_mezzanine_avg = _reduce(tranche_dscrs[mezz_idx])
        dscr_subordinated_min = 0.0
        dscr_subordinated_avg = 0.0
        moic_subordinated = 0.0
        recovery_going_concern = 0.0
        if has_sub:
            dscr_subordinated_min, dscr_subordinated_avg = _reduce(
                tranche_dscrs[sub_idx]
            )
            sub = cfg.financing.subordinated
            assert sub is not None  # narrowed by has_sub
            moic_subordinated = compute_moic(sub_ds, sub.principal)
            recovery_rate = (
                cfg.valuation.cost_of_equity_annual
                or cfg.valuation.discount_rate_annual
            )
            tenor_periods = int(sub.tenor_years * ppy)
            recovery_going_concern = compute_recovery_multiple(
                cfads,
                from_period=tenor_periods,
                discount_rate_annual=recovery_rate,
                periods_per_year=ppy,
                outstanding_principal=sub.principal,
            )

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
            npv_equity=npv_equity,
            dscr_senior_min=dscr_senior_min,
            dscr_senior_avg=dscr_senior_avg,
            dscr_subordinated_min=dscr_subordinated_min,
            dscr_subordinated_avg=dscr_subordinated_avg,
            moic_subordinated=moic_subordinated,
            recovery_going_concern=recovery_going_concern,
            dscr_mezzanine_min=dscr_mezzanine_min,
            dscr_mezzanine_avg=dscr_mezzanine_avg,
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

        if deg.type == "custom":
            return [float(deg.curve[min(t // ppy, len(deg.curve) - 1)]) for t in range(periods)]

        # deg.type == "none" (or anything unrecognised)
        return degradation_none(periods)
