from typing import Any

from asset_finance_modeler.core.scenario import run_scenario, run_scenario_saas  # noqa: F401
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore

_VIEWS = [
    "summary",
    "pnl",
    "cashflow",
    "balance",
    "unit_econ",
    "valuation",
    "debt_metrics",
    "revenue_breakdown",
    "sensitivity",
    "all",
]


def _results_to_view(scenario_results: dict[str, Any], view: str) -> dict[str, Any]:
    if view == "summary":
        return {"summary": scenario_results.get("summary", {})}
    if view == "all":
        return scenario_results
    if view not in _VIEWS:
        return {"error": f"unknown view {view!r}. Valid: {_VIEWS}"}
    return {view: scenario_results.get(view, {})}


def make_run(store: SQLiteScenarioStore) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        scenario_id = args["scenario_id"]
        scenario = store.get(scenario_id)
        if scenario is None:
            return {"error": f"scenario_id {scenario_id!r} not found"}

        results = run_scenario(scenario)
        full: dict[str, Any] = {
            "summary": dict(results.summary),
            "pnl": results.pnl,
            "cashflow": results.cashflow,
            "balance": results.balance,
            "unit_econ": getattr(results, "unit_econ", None),
            "valuation": results.valuation,
            "debt_metrics": results.debt_metrics,
            "revenue_breakdown": results.revenue_breakdown,
            "sensitivity": results.sensitivity,
        }

        if hasattr(results, "project_kpis") and results.project_kpis is not None:
            kpis = results.project_kpis
            full["project_kpis"] = {
                "irr_project": kpis.irr_project,
                "irr_equity": kpis.irr_equity,
                "npv": kpis.npv,
                "lcoe": kpis.lcoe,
                "lcos": kpis.lcos,
                "payback_years": kpis.payback_years,
                "dscr_min": kpis.dscr_min,
                "dscr_avg": kpis.dscr_avg,
            }

        scenario.results_snapshot = full
        store.save(scenario)
        response_summary = dict(full["summary"])
        if "project_kpis" in full:
            response_summary["project_kpis"] = full["project_kpis"]
        return {"scenario_id": scenario_id, "summary": response_summary}

    return _handle


def make_get_results(store: SQLiteScenarioStore) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        scenario_id = args["scenario_id"]
        view = args.get("view", "summary")
        scenario = store.get(scenario_id)
        if scenario is None:
            return {"error": f"scenario_id {scenario_id!r} not found"}
        if not scenario.results_snapshot:
            return {
                "error": (
                    f"scenario {scenario_id!r} has no results — "
                    "call finance.simulate.run first"
                )
            }
        return _results_to_view(scenario.results_snapshot, view)

    return _handle


def make_get_genealogy(store: SQLiteScenarioStore) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        scenario_id = args["scenario_id"]
        scenario = store.get(scenario_id)
        if scenario is None:
            return {"error": f"scenario_id {scenario_id!r} not found"}
        ancestors = store.get_ancestors(scenario_id)
        descendants = store.get_descendants(scenario_id)
        return {
            "scenario_id": scenario_id,
            "ancestors": [{"id": a.id, "name": a.name} for a in ancestors],
            "descendants": [{"id": d.id, "name": d.name} for d in descendants],
        }

    return _handle
