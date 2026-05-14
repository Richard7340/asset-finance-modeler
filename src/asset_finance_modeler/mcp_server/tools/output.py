from typing import Any

from asset_finance_modeler.assets.saas.model import ModelResults
from asset_finance_modeler.store.exports import (
    to_csv,
    to_json,
    to_markdown_report,
    to_markdown_table,
    to_summary,
    to_xlsx,
)
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore


def _hydrate_results_from_scenario(snapshot: dict[str, Any]) -> ModelResults:
    return ModelResults(
        pnl=snapshot.get("pnl", {}),
        cashflow=snapshot.get("cashflow", {}),
        balance=snapshot.get("balance", {}),
        unit_econ=snapshot.get("unit_econ", {}),
        valuation=snapshot.get("valuation", {}),
        sensitivity=snapshot.get("sensitivity"),
        debt_metrics=snapshot.get("debt_metrics", {}),
        revenue_breakdown=snapshot.get("revenue_breakdown", {}),
        summary=snapshot.get("summary", {}),
    )


def make_export(store: SQLiteScenarioStore) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        scenario = store.get(args["scenario_id"])
        if scenario is None:
            return {"error": "scenario not found"}
        if not scenario.results_snapshot:
            return {"error": "scenario has no results — run it first"}
        results = _hydrate_results_from_scenario(scenario.results_snapshot)
        fmt = args["format"]
        view = args.get("view")
        path = args.get("path")

        if fmt == "summary":
            return {"content": to_summary(results)}
        if fmt == "markdown_table":
            if view is None:
                return {"error": "markdown_table requires 'view'"}
            return {"content": to_markdown_table(results, view=view)}
        if fmt == "markdown_report":
            return {"content": to_markdown_report(results)}
        if fmt == "json":
            content = to_json(results, path=path)
            if path:
                return {"ok": True, "path": path}
            return {"content": content}
        if fmt == "csv":
            if path is None:
                return {"error": "csv requires 'path'"}
            if view is None:
                return {"error": "csv requires 'view'"}
            to_csv(results, view=view, path=path)
            return {"ok": True, "path": path}
        if fmt == "xlsx":
            if path is None:
                return {"error": "xlsx requires 'path'"}
            to_xlsx(results, path=path)
            return {"ok": True, "path": path}
        return {"error": f"unknown format {fmt!r}"}

    return _handle


def make_fetch_external(store: SQLiteScenarioStore) -> Any:
    """Delegation tool: does NOT make HTTP — returns instruction for the caller."""
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        return {
            "query": args["query"],
            "field_path": args["field_path"],
            "hint": args.get("hint", ""),
            "instruction": (
                "Execute WebSearch (or equivalent) with this query, then call "
                "finance.simulate.set_external with the resulting value+source."
            ),
        }

    return _handle


def make_set_external(store: SQLiteScenarioStore) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        scenario = store.get(args["scenario_id"])
        if scenario is None:
            return {"error": "scenario not found"}
        field_path = args["field_path"]
        value = args["value"]
        source = args.get("source")
        confidence = args.get("confidence", "medium")

        # Persist as overrides on the value/source/confidence subkeys
        # so subsequent runs see them
        scenario.overrides[f"{field_path}.value"] = value
        if source is not None:
            scenario.overrides[f"{field_path}.source"] = source
        scenario.overrides[f"{field_path}.confidence"] = confidence
        store.save(scenario)
        return {"ok": True, "field_path": field_path, "value": value, "source": source}

    return _handle


def make_track_stub(verb: str) -> Any:
    def _handle(_args: dict[str, Any]) -> dict[str, Any]:
        return {
            "error": f"finance.track.{verb} is a v2 surface — not implemented in v1",
            "v2_status": "planned",
        }

    return _handle
