from dataclasses import dataclass, field

from asset_finance_modeler.core.statements import (
    BalanceBuilder,
    CashFlowBuilder,
    PnLBuilder,
    compute_debt_metrics,
    compute_runway,
    compute_unit_economics,
)
from asset_finance_modeler.core.time_grid import TimeGrid
from asset_finance_modeler.core.valuation import (
    compute_dcf,
    compute_sensitivity_grid,
)

from .engines import (
    CapExEngine,
    COGSEngine,
    CohortRevenueEngine,
    DebtEngine,
    OpexEngine,
)
from .schema import SaasModelConfig

_PERIOD_DAYS = {"M": 30, "Q": 91, "Y": 365}


@dataclass
class ModelResults:
    pnl: dict[str, list[float]]
    cashflow: dict[str, list[float]]
    balance: dict[str, list[float]]
    unit_econ: dict[str, list[float]]
    valuation: dict[str, float]
    sensitivity: list[list[float]] | None
    debt_metrics: dict[str, list[float]]
    revenue_breakdown: dict[str, list[float]]
    summary: dict[str, float | int]
    inputs_resolved: dict[str, object] = field(default_factory=dict)


@dataclass
class SaasModel:
    config: SaasModelConfig

    def run(self) -> ModelResults:
        cfg = self.config
        n = cfg.meta.horizon.periods
        ppy = TimeGrid(periods=n, frequency=cfg.meta.horizon.frequency, start_date=cfg.meta.start_date).periods_per_year
        period_days = _PERIOD_DAYS[cfg.meta.horizon.frequency]

        # 1. Revenue
        rev = CohortRevenueEngine(cfg.revenue.sources, periods=n).compute()

        # 2. COGS
        cogs = COGSEngine(
            cfg.cost_of_revenue,
            active_units=rev["active_units"],
            active_customers=rev["active_customers"],
        ).compute()

        # 3. CapEx + depreciation
        capex_eng = CapExEngine(cfg.capital.capex_schedule, periods=n, periods_per_year=ppy).compute()

        # 4. Opex
        opex = OpexEngine(cfg.operating_expenses, periods=n).compute()

        # 5. CAC spend for unit economics
        cac_spend = [
            rev["new_customers"][t] * cfg.revenue.sources[0].acquisition.cac_per_customer
            for t in range(n)
        ]

        # 6. Debt
        debt = DebtEngine(cfg.capital.debt, periods=n, periods_per_year=ppy).compute()

        # 7. P&L
        pnl = PnLBuilder(
            revenue=rev["total_revenue"],
            cogs=cogs["total_cogs"],
            opex=opex["total_opex"],
            depreciation=capex_eng["depreciation"],
            interest_expense=debt["interest_expense"],
            corporate_tax_rate=cfg.taxes.corporate_income_tax_rate,
            carryforward_enabled=cfg.taxes.tax_loss_carryforward,
        ).build()

        # 8. Cash Flow
        funding_drawdowns = [0.0] * n
        for fr in cfg.capital.funding_rounds:
            if fr.period < n:
                funding_drawdowns[fr.period] += fr.amount

        cf = CashFlowBuilder(
            net_income=pnl["net_income"],
            depreciation=capex_eng["depreciation"],
            revenue=pnl["revenue"],
            cogs=pnl["cogs"],
            dso_days=cfg.capital.working_capital.days_sales_outstanding,
            dpo_days=cfg.capital.working_capital.days_payable_outstanding,
            capex=capex_eng["capex_spend"],
            funding_drawdowns=funding_drawdowns,
            debt_drawdowns=debt["drawdowns"],
            debt_principal_repaid=debt["principal_repaid"],
            origination_fees=debt["origination_fees"],
            initial_cash=cfg.meta.initial_cash,
            period_days=period_days,
        ).build()

        # 9. Balance
        balance = BalanceBuilder(
            cash=cf["cash"],
            ar_balance=cf["ar_balance"],
            fixed_assets_net=capex_eng["fixed_assets_net"],
            debt_outstanding=debt["balance_outstanding"],
            ap_balance=cf["ap_balance"],
            equity_initial=cfg.meta.initial_cash,
        ).build()

        # 10. Unit econ
        unit_econ = compute_unit_economics(
            revenue=pnl["revenue"],
            cogs=pnl["cogs"],
            cac_spend=cac_spend,
            active_customers=rev["active_customers"],
            new_customers=rev["new_customers"],
            monthly_churn=cfg.revenue.sources[0].retention.monthly_churn_rate,
            periods_per_year=ppy,
        )

        # 11. Debt metrics
        debt_metrics = compute_debt_metrics(
            ebitda=pnl["ebitda"],
            ebit=pnl["ebit"],
            interest_expense=pnl["interest_expense"],
            principal_repaid=debt["principal_repaid"],
            debt_outstanding=debt["balance_outstanding"],
        )

        # 12. Valuation
        fcf_period = [cf["cfo"][t] + cf["cfi"][t] for t in range(n)]
        years = n // ppy
        fcf_annual = [sum(fcf_period[y * ppy:(y + 1) * ppy]) for y in range(years)] if years > 0 else fcf_period

        try:
            val = compute_dcf(
                fcf_series=fcf_annual,
                wacc_annual=cfg.valuation.discount_rate_annual,
                terminal_growth=cfg.valuation.terminal_growth_rate,
                periods_per_year=1,
                terminal_method=cfg.valuation.terminal_method,
                exit_arr=pnl["revenue"][-1] * ppy if cfg.valuation.exit_multiple_arr else None,
                exit_multiple_arr=cfg.valuation.exit_multiple_arr,
            )
        except ValueError:
            val = {"pv_explicit": 0.0, "terminal_value": 0.0, "pv_terminal": 0.0, "enterprise_value": 0.0}

        sens = None
        if cfg.valuation.sensitivity_grid:
            sens = compute_sensitivity_grid(
                fcf_series=fcf_annual,
                wacc_values=cfg.valuation.sensitivity_grid.wacc,
                growth_values=cfg.valuation.sensitivity_grid.growth,
                periods_per_year=1,
                terminal_method=cfg.valuation.terminal_method,
            )

        runway = compute_runway(cf["cash"])

        # 13. Summary
        annual_revenue_y1 = sum(pnl["revenue"][:ppy]) if n >= ppy else sum(pnl["revenue"])
        ebitda_margin_last = (
            pnl["ebitda"][-1] / pnl["revenue"][-1] if pnl["revenue"][-1] > 0 else 0
        )
        summary: dict[str, float | int] = {
            "revenue_y1": annual_revenue_y1,
            "revenue_end_period": pnl["revenue"][-1],
            "ebitda_margin_end": ebitda_margin_last,
            "active_customers_end": rev["active_customers"][-1],
            "active_units_end": rev["active_units"][-1],
            "cash_end": cf["cash"][-1],
            "runway_months": runway if runway != float("inf") else -1,
            "ltv_cac_end": unit_econ["ltv_cac"][-1] if unit_econ["ltv_cac"][-1] != float("inf") else -1,
            "enterprise_value": val["enterprise_value"],
        }

        return ModelResults(
            pnl=pnl,
            cashflow=cf,
            balance=balance,
            unit_econ=unit_econ,
            valuation=val,
            sensitivity=sens,
            debt_metrics=debt_metrics,
            revenue_breakdown=rev,
            summary=summary,
            inputs_resolved=cfg.model_dump(mode="json"),
        )
