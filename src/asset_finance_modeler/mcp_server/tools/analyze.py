from typing import Any

from asset_finance_modeler.core.scenario import Scenario, new_scenario_id, run_scenario_saas
from asset_finance_modeler.store.compare import compare_scenarios
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore
from asset_finance_modeler.store.sensitivity import sensitivity_1d as _sensitivity_1d


def make_compare(store: SQLiteScenarioStore) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        ids = args["scenario_ids"]
        scenarios = []
        for sid in ids:
            s = store.get(sid)
            if s is None:
                return {"error": f"scenario_id {sid!r} not found"}
            # Materialize compatible Scenario with summary from results_snapshot
            if "summary" not in (s.results_snapshot or {}):
                return {"error": f"scenario {sid!r} has no summary — run it first"}
            scenarios.append(s)
        try:
            table = compare_scenarios(scenarios, metrics=args.get("metrics"))
        except ValueError as exc:
            return {"error": str(exc)}
        return {"table": table}

    return _handle


def make_sensitivity_1d(store: SQLiteScenarioStore) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        base_id = args["scenario_id"]
        base = store.get(base_id)
        if base is None:
            return {"error": f"scenario_id {base_id!r} not found"}
        out = _sensitivity_1d(
            base_scenario=base,
            variable=args["variable"],
            values=args["values"],
            metric=args["metric"],
        )
        return out

    return _handle


def make_sensitivity_grid(store: SQLiteScenarioStore) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        base = store.get(args["scenario_id"])
        if base is None:
            return {"error": "scenario_id not found"}
        var_x = args["var_x"]
        var_y = args["var_y"]
        values_x = args["values_x"]
        values_y = args["values_y"]
        metric = args["metric"]
        grid: list[list[float]] = []
        for vx in values_x:
            row: list[float] = []
            for vy in values_y:
                merged_overrides = dict(base.overrides)
                merged_overrides[var_x] = vx
                merged_overrides[var_y] = vy
                run_s = Scenario(
                    id=new_scenario_id(),
                    name=f"grid-{vx}-{vy}",
                    base_model=base.base_model,
                    overrides=merged_overrides,
                )
                results = run_scenario_saas(run_s)
                if metric not in results.summary:
                    return {"error": f"metric {metric!r} not in summary"}
                row.append(results.summary[metric])
            grid.append(row)
        return {
            "var_x": var_x,
            "var_y": var_y,
            "values_x": values_x,
            "values_y": values_y,
            "metric": metric,
            "grid": grid,
        }

    return _handle
