from __future__ import annotations
from typing import Any
from asset_finance_modeler.core.portfolio import analyze_portfolio
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore


def make_portfolio_analyze(store: SQLiteScenarioStore) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        scenario_ids = args["scenario_ids"]
        scenarios = []
        for sid in scenario_ids:
            s = store.get(sid)
            if s is None:
                return {"error": f"Scenario {sid} not found"}
            if not s.results_snapshot:
                return {"error": f"Scenario {sid} has no results — run it first"}
            scenarios.append({
                "id": s.id, "name": s.name, "base_model": s.base_model,
                "summary": s.results_snapshot.get("summary", {}),
                "project_kpis": s.results_snapshot.get("project_kpis", {}),
            })
        result = analyze_portfolio(scenarios)
        return {
            "aggregated": result.aggregated,
            "comparison_table": result.comparison_table,
            "narrative": result.narrative,
        }
    return _handle
