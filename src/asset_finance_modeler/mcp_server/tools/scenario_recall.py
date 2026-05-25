from __future__ import annotations

from typing import Any

from asset_finance_modeler.core.scenario_diff import diff_scenarios
from asset_finance_modeler.intelligence.recall import ScenarioRecall
from asset_finance_modeler.store.projects import SQLiteProjectStore
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore


def make_scenario_diff(scenario_store: SQLiteScenarioStore) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        a = scenario_store.get(args["scenario_a_id"])
        b = scenario_store.get(args["scenario_b_id"])
        if a is None:
            return {"error": f"Scenario {args['scenario_a_id']} not found"}
        if b is None:
            return {"error": f"Scenario {args['scenario_b_id']} not found"}
        result = diff_scenarios(
            a.results_snapshot,
            b.results_snapshot,
            scenario_a_id=a.id,
            scenario_b_id=b.id,
            scenario_a_name=a.name,
            scenario_b_name=b.name,
        )
        return {
            "summary": result.summary,
            "input_deltas": [
                {
                    "field": d.field_path,
                    "from": d.value_a,
                    "to": d.value_b,
                    "change": d.change,
                }
                for d in result.input_deltas
            ],
            "kpi_deltas": [
                {
                    "metric": d.metric,
                    "from": d.value_a,
                    "to": d.value_b,
                    "change": d.change,
                    "change_pct": d.change_pct,
                    "direction": d.direction,
                }
                for d in result.kpi_deltas
            ],
        }

    return _handle


def make_scenario_recall(recall: ScenarioRecall) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        results = recall.search(args["query"], top_k=args.get("top_k", 5))
        return {
            "results": [
                {
                    "scenario_id": r.scenario_id,
                    "name": r.name,
                    "description": r.description,
                    "asset_type": r.asset_type,
                    "score": r.score,
                    "summary": r.summary,
                }
                for r in results
            ]
        }

    return _handle


def make_recall_project_context(
    project_store: SQLiteProjectStore, scenario_store: SQLiteScenarioStore
) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        project = project_store.get(args["project_id"])
        if project is None:
            return {"error": f"Project {args['project_id']} not found"}
        scenarios = []
        for sid in project.scenario_ids:
            s = scenario_store.get(sid)
            if s and s.results_snapshot:
                summary = s.results_snapshot.get("summary", {})
                kpis = s.results_snapshot.get("project_kpis", {})
                if isinstance(kpis, dict):
                    summary = {**summary, **kpis}
                scenarios.append({"id": s.id, "name": s.name, "summary": summary})
        narrative = f"Project '{project.name}'"
        if project.asset_type:
            narrative += f" ({project.asset_type})"
        if project.region:
            narrative += f" in {project.region}"
        narrative += f" has {len(scenarios)} scenario(s)."
        if scenarios:
            best_irr = max((s["summary"].get("irr_project", 0) for s in scenarios), default=0)
            narrative += f" Best project IRR: {best_irr:.1%}."
        return {
            "project": {"id": project.id, "name": project.name},
            "scenarios": scenarios,
            "narrative": narrative,
        }

    return _handle
