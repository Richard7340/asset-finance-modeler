"""BusinessModel — orchestrator for generic (non-asset) business modelling.

Implements the FinancialModel protocol, mirroring InfrastructureModel but on a
plain P&L-driven business: revenue lines → COGS → OPEX → depreciation → debt →
P&L → cash flow → DCF/IRR → FinancialOutput.

Statements are computed annually and then expanded evenly to per-period series
(length ``n``) so that ``web_api.models._annual`` (sum over each year's ``ppy``
periods) recovers the original annual figures.
"""

from __future__ import annotations

from dataclasses import dataclass

from asset_finance_modeler.assets.business.engines import (
    indice_ipc,
    opex_series,
    revenue_series,
)
from asset_finance_modeler.assets.business.schema import BusinessModelConfig
from asset_finance_modeler.core.drivers import AmortizationSchedule
from asset_finance_modeler.core.financing import size_debt
from asset_finance_modeler.core.statements import PnLBuilder
from asset_finance_modeler.core.protocols import FinancialOutput, ProjectKPIs
from asset_finance_modeler.core.valuation import (
    compute_dcf,
    compute_discounted_payback,
    compute_irr,
)

__all__ = ["BusinessModel"]

_PPY = {"M": 12, "Q": 4, "Y": 1}


@dataclass
class BusinessModel:
    config: BusinessModelConfig
    config_schema = BusinessModelConfig  # satisfies FinancialModel protocol

    def __init__(self, cfg: BusinessModelConfig) -> None:
        self.config = cfg

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> FinancialOutput:
        cfg = self.config
        ppy = _PPY[cfg.meta.horizon.frequency]
        n = cfg.meta.horizon.periods
        years = n // ppy

        # 1. Annual revenue and OPEX
        inf = cfg.inflacion
        idx = indice_ipc(inf.curva, years) if inf else None
        rev_y = revenue_series([line.model_dump() for line in cfg.revenue], years,
                               idx if inf and inf.aplicar_a in ("todo", "ingresos") else None)
        opex_y = opex_series(
            [line.model_dump() for line in cfg.opex.fixed_lines],
            cfg.opex.variable_pct_of_revenue,
            rev_y,
            cfg.opex.escalation_pct_yr,
            years,
            idx if inf and inf.aplicar_a in ("todo", "gastos") else None,
        )

        # 2. Annual straight-line depreciation across all capex items
        dep_y = self._depreciation_annual(years, ppy)

        # 3. Debt — annual interest + principal series (zeros if none)
        int_y, principal_y, drawdown_total, dscr_series = self._debt_annual(
            rev_y, opex_y, dep_y, years, ppy
        )

        # 4. P&L (annual). Use the core PnLBuilder so tax loss carryforward is
        #    honored (P0-5) — the previous pnl_rows taxed each year in isolation
        #    and ignored the taxes.tax_loss_carryforward flag entirely.
        cogs_y = [r * cfg.cogs.pct_of_revenue for r in rev_y]
        rows = PnLBuilder(
            revenue=rev_y,
            cogs=cogs_y,
            opex=opex_y,
            depreciation=dep_y,
            interest_expense=int_y,
            corporate_tax_rate=cfg.taxes.corporate_income_tax_rate,
            carryforward_enabled=cfg.taxes.tax_loss_carryforward,
        ).build()

        # 5. Expand annual rows → per-period (length n), spreading evenly so that
        #    summing each year's ppy periods recovers the annual figure.
        pnl = {k: self._expand(v, ppy, n) for k, v in rows.items()}

        # 6. Cash flow (annual → per-period). Apply working-capital changes
        #    (P0-6): receivable/payable/inventory days build balances off
        #    revenue/COGS; the period-over-period change in net working capital
        #    moves cash. Growing AR/inventory consumes cash; growing AP frees
        #    it. Previously the WC days were a no-op (CFO = NI + depreciation).
        delta_wc_y = self._delta_working_capital(rows["revenue"], rows["cogs"], years)
        cfo_y = [
            rows["net_income"][y] + dep_y[y] - delta_wc_y[y] for y in range(years)
        ]
        cfi_y = self._capex_annual(years, ppy)
        cff_y = [drawdown_total[y] - principal_y[y] for y in range(years)]

        cashflow = {
            "cfo": self._expand(cfo_y, ppy, n),
            "cfi": self._expand(cfi_y, ppy, n),
            "cff": self._expand(cff_y, ppy, n),
        }

        # 7. Valuation — DCF on UNLEVERED annual FCF, financing-independent:
        #    FCF = EBIT*(1-t) + D&A - capex (±ΔWC). Using CFO (which carries the
        #    interest deduction) while dropping the debt principal/drawdown made
        #    the project EV depend on financing and silently undercounted the
        #    debt — see P0-4. Equity NPV (levered, to Ke) is handled separately.
        tax_rate = cfg.taxes.corporate_income_tax_rate
        nopat_y = [
            rows["ebit"][y] * (1.0 - tax_rate) if rows["ebit"][y] > 0 else rows["ebit"][y]
            for y in range(years)
        ]
        # cfi_y is negative capex spend; cfo carries the ΔWC already (see step 6).
        delta_wc_y = [cfo_y[y] - (rows["net_income"][y] + dep_y[y]) for y in range(years)]
        fcf_annual = [
            nopat_y[y] + dep_y[y] + cfi_y[y] + delta_wc_y[y] for y in range(years)
        ]
        # P0-7: residual / exit sale of the underlying asset at horizon end is a
        # cash inflow in the final modelled year — recovers capital for
        # finite-horizon asset-backed deals (e.g. a real-estate sale).
        if cfg.valuation.residual_value and years > 0:
            fcf_annual[-1] += cfg.valuation.residual_value
        try:
            val = compute_dcf(
                fcf_series=fcf_annual,
                wacc_annual=cfg.valuation.discount_rate_annual,
                terminal_growth=cfg.valuation.terminal_growth_rate,
                periods_per_year=1,
                terminal_method=cfg.valuation.terminal_method,  # type: ignore[arg-type]
            )
        except ValueError:
            val = {
                "pv_explicit": 0.0,
                "terminal_value": 0.0,
                "pv_terminal": 0.0,
                "enterprise_value": 0.0,
            }

        # 8. KPIs. Con deuda, la rentabilidad del SOCIO sale de su caja (lo que
        # pone, lo que le queda tras pagar la deuda), no es la del proyecto.
        fcfe = [cfo_y[y] + cfi_y[y] + cff_y[y] for y in range(years)]
        hay_deuda = any(int_y) or any(principal_y) or any(drawdown_total)
        # Deuda viva al final: lo dispuesto (y lo que ya se debia) menos lo devuelto.
        ya_debido = sum(p.importe for p in cfg.financing.prestamos if p.ya_dispuesto)
        self._deuda_final = max(sum(drawdown_total) + ya_debido - sum(principal_y), 0.0)
        # Si el activo se vende al final (valor residual), el socio cobra la
        # venta y devuelve lo que quede de deuda.
        if cfg.valuation.residual_value and years > 0:
            fcfe[-1] += cfg.valuation.residual_value - self._deuda_final
        kpis = self._compute_kpis(fcf_annual, dscr_series, val, fcfe if hay_deuda else None)

        total_capex = sum(item.amount for item in cfg.capex.items)
        summary: dict[str, float | int] = {
            "total_capex": total_capex,
            "revenue_y1": rev_y[0] if rev_y else 0.0,
            "enterprise_value": val["enterprise_value"],
            "irr_project": kpis.irr_project,
        }
        if getattr(self, "_prestamos", None):
            summary["prestamos"] = self._prestamos  # type: ignore[assignment]

        return FinancialOutput(
            pnl=pnl,
            cashflow=cashflow,
            balance={},
            debt_metrics={},
            revenue_breakdown={"total": self._expand(rev_y, ppy, n)},
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
    def _expand(annual: list[float], ppy: int, n: int) -> list[float]:
        """Spread each annual value evenly across its ``ppy`` periods, padded to n."""
        out: list[float] = []
        for value in annual:
            out.extend([value / ppy] * ppy)
        if len(out) < n:
            out.extend([0.0] * (n - len(out)))
        return out[:n]

    def _delta_working_capital(
        self, revenue_y: list[float], cogs_y: list[float], years: int
    ) -> list[float]:
        """Year-over-year change in net working capital (positive = cash used).

        AR  = revenue × receivable_days / 365  (cash tied up)
        INV = COGS    × inventory_days  / 365  (cash tied up)
        AP  = COGS    × payable_days    / 365  (cash released)

        NWC = AR + INV − AP. ΔNWC[y] = NWC[y] − NWC[y-1] (NWC[-1] = 0). A rising
        NWC consumes cash, so CFO subtracts ΔNWC.
        """
        wc = self.config.working_capital
        nwc: list[float] = []
        for y in range(years):
            rev = revenue_y[y] if y < len(revenue_y) else 0.0
            cogs = cogs_y[y] if y < len(cogs_y) else 0.0
            ar = rev * wc.receivable_days / 365.0
            inv = cogs * wc.inventory_days / 365.0
            ap = cogs * wc.payable_days / 365.0
            nwc.append(ar + inv - ap)
        delta: list[float] = []
        prev = 0.0
        for y in range(years):
            delta.append(nwc[y] - prev)
            prev = nwc[y]
        return delta

    def _depreciation_annual(self, years: int, ppy: int) -> list[float]:
        dep = [0.0] * years
        for item in self.config.capex.items:
            if item.depreciation_years <= 0:
                continue
            start_year = item.period // ppy
            annual_charge = item.amount / item.depreciation_years
            for y in range(start_year, min(start_year + item.depreciation_years, years)):
                dep[y] += annual_charge
        return dep

    def _capex_annual(self, years: int, ppy: int) -> list[float]:
        """Negative capex spend per year (CFI), at each item's drawdown year."""
        cfi = [0.0] * years
        for item in self.config.capex.items:
            y = item.period // ppy
            if 0 <= y < years:
                cfi[y] -= item.amount
        return cfi

    def _debt_annual(
        self,
        rev_y: list[float],
        opex_y: list[float],
        dep_y: list[float],
        years: int,
        ppy: int,
    ) -> tuple[list[float], list[float], list[float], list[float]]:
        """Annual interest, principal-repaid, drawdowns and a DSCR series.

        EBITDA (gross margin minus OPEX) is the CFADS proxy. Senior debt is
        auto-sized (or set from ``max_leverage`` × total capex) and a
        subordinated fixed ticket is added if configured. Empty series if no
        debt is configured.
        """
        cfg = self.config
        int_y = [0.0] * years
        principal_y = [0.0] * years
        drawdown_y = [0.0] * years

        cogs_pct = cfg.cogs.pct_of_revenue
        ebitda_y = [
            rev_y[y] * (1.0 - cogs_pct) - opex_y[y] for y in range(years)
        ]
        total_capex = sum(item.amount for item in cfg.capex.items)

        debt_service_y = [0.0] * years

        # Senior tranche
        senior = cfg.financing.senior
        if senior is not None:
            if senior.auto_size:
                sizing = size_debt(
                    cfads=ebitda_y,
                    dscr_target=senior.dscr_target,
                    dscr_mode=senior.dscr_mode,
                    interest_rate=senior.interest_rate,
                    tenor_periods=senior.tenor_years,
                    periods_per_year=1,
                    max_leverage=cfg.financing.max_leverage,
                    total_capex=total_capex,
                    amortization=senior.amortization,
                    grace_periods=senior.grace_period_months // 12,
                )
                principal = sizing.max_debt if sizing.feasible else 0.0
            else:
                principal = total_capex * cfg.financing.max_leverage
            if principal > 0:
                self._apply_tranche(
                    principal=principal,
                    annual_rate=senior.interest_rate,
                    tenor_years=senior.tenor_years,
                    grace_years=senior.grace_period_months // 12,
                    amortization=senior.amortization,
                    start_year=0,
                    years=years,
                    int_y=int_y,
                    principal_y=principal_y,
                    drawdown_y=drawdown_y,
                    debt_service_y=debt_service_y,
                )

        # Subordinated tranche (fixed ticket)
        sub = cfg.financing.subordinated
        if sub is not None and sub.principal > 0:
            self._apply_tranche(
                principal=sub.principal,
                annual_rate=sub.interest_rate,
                tenor_years=sub.tenor_years,
                grace_years=sub.grace_period_months // 12,
                amortization=sub.amortization,
                start_year=sub.drawdown_period // ppy,
                years=years,
                int_y=int_y,
                principal_y=principal_y,
                drawdown_y=drawdown_y,
                debt_service_y=debt_service_y,
            )

        # Prestamos concretos (26-sep): cada uno con su tipo, plazo y carencia.
        self._prestamos = []
        for p in cfg.financing.prestamos:
            inicio = p.anio_inicio
            tramos = [(p.importe - p.valor_residual, p.amortizacion)]
            if p.valor_residual > 0:
                tramos.append((p.valor_residual, "bullet"))
            filas: list[list[dict[str, float]]] = []
            for importe, amort in tramos:
                if importe <= 0:
                    continue
                filas.append(self._apply_tranche(
                    principal=importe, annual_rate=p.tipo_interes, tenor_years=p.plazo_anios,
                    grace_years=p.carencia_meses // 12, amortization=amort, start_year=inicio,
                    years=years, int_y=int_y, principal_y=principal_y, drawdown_y=drawdown_y,
                    debt_service_y=debt_service_y, con_disposicion=not p.ya_dispuesto,
                ))
            comision = p.importe * p.comision_apertura_pct
            if comision and 0 <= inicio < years and not p.ya_dispuesto:
                int_y[inicio] += comision
            primer = [sum(f[0][k] for f in filas if f) for k in ("total_payment", "interest")]
            self._prestamos.append({
                "nombre": p.nombre, "tipo": p.tipo, "importe": round(p.importe),
                "cuota_anual_inicial": round(primer[0]), "cuota_mensual_aprox": round(primer[0] / 12, 2),
                "intereses_totales": round(sum(r["interest"] for f in filas for r in f) + comision),
                "anio_ultimo_pago": inicio + p.plazo_anios, "ya_dispuesto": p.ya_dispuesto,
            })

        dscr_series = [
            ebitda_y[y] / debt_service_y[y]
            for y in range(years)
            if debt_service_y[y] > 0
        ]
        return int_y, principal_y, drawdown_y, dscr_series

    @staticmethod
    def _apply_tranche(
        principal: float,
        annual_rate: float,
        tenor_years: int,
        grace_years: int,
        amortization: str,
        start_year: int,
        years: int,
        int_y: list[float],
        principal_y: list[float],
        drawdown_y: list[float],
        debt_service_y: list[float],
        con_disposicion: bool = True,
    ) -> list[dict[str, float]]:
        if con_disposicion and 0 <= start_year < years:
            drawdown_y[start_year] += principal
        rows = AmortizationSchedule(
            principal=principal,
            annual_rate=annual_rate,
            term_periods=tenor_years,
            periods_per_year=1,
            kind=amortization,  # type: ignore[arg-type]
            grace_periods=grace_years,
        ).rows()
        for i, row in enumerate(rows):
            y = start_year + i
            if y >= years:
                break
            int_y[y] += row["interest"]
            principal_y[y] += row["principal_payment"]
            debt_service_y[y] += row["total_payment"]
        return rows

    def _compute_kpis(
        self,
        fcf_annual: list[float],
        dscr_series: list[float],
        val: dict[str, float],
        fcfe: list[float] | None = None,
    ) -> ProjectKPIs:
        cfg = self.config
        irr_project = compute_irr(fcf_annual, 1)
        ke = cfg.valuation.cost_of_equity_annual or cfg.valuation.discount_rate_annual
        if fcfe is not None:
            irr_equity = compute_irr(fcfe, 1)
            npv_equity = sum(f / (1 + ke) ** (y + 1) for y, f in enumerate(fcfe))
            # Como el VAN del proyecto: con su valor final, menos la deuda que quede.
            if val.get("terminal_value") and fcfe and not cfg.valuation.residual_value:
                npv_equity += (val["terminal_value"] - getattr(self, "_deuda_final", 0.0)) / (1 + ke) ** len(fcfe)
        else:
            irr_equity, npv_equity = irr_project, val["enterprise_value"]
        payback = compute_discounted_payback(
            fcf_annual, cfg.valuation.discount_rate_annual, 1
        )
        positive = [d for d in dscr_series if 0 < d < float("inf")]
        dscr_min = min(positive) if positive else 0.0
        dscr_avg = sum(positive) / len(positive) if positive else 0.0

        return ProjectKPIs(
            irr_project=irr_project,
            irr_equity=irr_equity,
            npv=val["enterprise_value"],
            npv_equity=npv_equity,
            lcoe=None,
            lcos=None,
            payback_years=payback,
            dscr_series=list(dscr_series),
            dscr_min=dscr_min,
            dscr_avg=dscr_avg,
            discount_rate_used=cfg.valuation.discount_rate_annual,
            debt_sizing=None,
        )
