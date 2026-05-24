from dataclasses import fields

from asset_finance_modeler.core.protocols import (
    DebtSizingResult,
    FinancialModel,
    FinancialOutput,
    ProjectKPIs,
)


def test_financial_output_has_required_fields():
    names = {f.name for f in fields(FinancialOutput)}
    assert "pnl" in names
    assert "cashflow" in names
    assert "balance" in names
    assert "debt_metrics" in names
    assert "revenue_breakdown" in names
    assert "valuation" in names
    assert "sensitivity" in names
    assert "summary" in names
    assert "inputs_resolved" in names
    assert "project_kpis" in names


def test_financial_output_default_project_kpis_is_none():
    out = FinancialOutput(
        pnl={}, cashflow={}, balance={}, debt_metrics={},
        revenue_breakdown={}, valuation={}, sensitivity=None,
        summary={}, inputs_resolved={},
    )
    assert out.project_kpis is None


def test_project_kpis_fields():
    kpis = ProjectKPIs(
        irr_project=0.08, irr_equity=0.12, npv=1_000_000,
        lcoe=45.0, lcos=None, payback_years=7.5,
        dscr_series=[1.3, 1.4, 1.5], dscr_min=1.3, dscr_avg=1.4,
        discount_rate_used=0.07, debt_sizing=None,
    )
    assert kpis.irr_equity == 0.12
    assert kpis.lcos is None
    assert kpis.dscr_min == 1.3


def test_debt_sizing_result_feasible():
    r = DebtSizingResult(
        max_debt=10_000_000, dscr_series=[1.3, 1.35],
        dscr_min=1.3, dscr_avg=1.325, leverage_ratio=0.75,
        equity_required=3_333_333, feasible=True, reason="ok",
    )
    assert r.feasible is True
    assert r.leverage_ratio == 0.75


def test_debt_sizing_result_infeasible():
    r = DebtSizingResult(
        max_debt=0, dscr_series=[], dscr_min=0, dscr_avg=0,
        leverage_ratio=0, equity_required=10_000_000,
        feasible=False, reason="DSCR target unreachable",
    )
    assert r.feasible is False


def test_financial_model_protocol_check():
    from pydantic import BaseModel

    class DummyConfig(BaseModel):
        x: int = 1

    class GoodModel:
        config_schema = DummyConfig
        def run(self) -> FinancialOutput:
            return FinancialOutput(
                pnl={}, cashflow={}, balance={}, debt_metrics={},
                revenue_breakdown={}, valuation={}, sensitivity=None,
                summary={}, inputs_resolved={},
            )

    assert isinstance(GoodModel(), FinancialModel)
