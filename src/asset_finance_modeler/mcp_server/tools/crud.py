from typing import Any

from asset_finance_modeler.core.scenario import Scenario, new_scenario_id
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore


def make_create_scenario(store: SQLiteScenarioStore) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        base_id = args["base_scenario_id"]
        base = store.get(base_id)
        if base is None:
            return {"error": f"base_scenario_id {base_id!r} not found"}
        scenario = Scenario(
            id=new_scenario_id(),
            name=args["name"],
            description=args.get("description", ""),
            base_model=base.base_model,
            parent_scenario_id=base_id,
            overrides=args.get("overrides", {}),
            tags=args.get("tags", []),
            notes=args.get("notes", ""),
        )
        store.save(scenario)
        return {"scenario_id": scenario.id, "name": scenario.name}

    return _handle


def make_clone_scenario(store: SQLiteScenarioStore) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        src_id = args["scenario_id"]
        src = store.get(src_id)
        if src is None:
            return {"error": f"scenario_id {src_id!r} not found"}
        # Inherit parent overrides + apply additional ones (additional takes precedence)
        merged_overrides = dict(src.overrides)
        merged_overrides.update(args.get("overrides", {}))
        scenario = Scenario(
            id=new_scenario_id(),
            name=args["name"],
            description=args.get("description", ""),
            base_model=src.base_model,
            parent_scenario_id=src.id,
            overrides=merged_overrides,
            tags=args.get("tags", []),
            notes=args.get("notes", ""),
        )
        store.save(scenario)
        return {"scenario_id": scenario.id, "name": scenario.name}

    return _handle


def make_list_scenarios(store: SQLiteScenarioStore) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        base_model = args.get("base_model")
        include_deleted = args.get("include_deleted", False)
        scenarios = store.list(base_model=base_model, include_deleted=include_deleted)
        return {
            "scenarios": [
                {
                    "id": s.id,
                    "name": s.name,
                    "base_model": s.base_model,
                    "parent_scenario_id": s.parent_scenario_id,
                    "is_canonical": s.is_canonical,
                    "is_deleted": s.is_deleted,
                    "tags": s.tags,
                    "created_at": s.created_at.isoformat(),
                }
                for s in scenarios
            ],
        }

    return _handle


def make_delete_scenario(store: SQLiteScenarioStore) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        try:
            store.delete(args["scenario_id"])
        except PermissionError as exc:
            return {"error": str(exc)}
        return {"ok": True}

    return _handle


def make_set_canonical(store: SQLiteScenarioStore) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        store.set_canonical(args["scenario_id"], name=args.get("name"))
        return {"ok": True}

    return _handle
