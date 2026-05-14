from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from asset_finance_modeler.store.scenarios import SQLiteScenarioStore


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], Any]


def build_registry(store: SQLiteScenarioStore | None) -> dict[str, ToolSpec]:
    """Build the full tool registry. `store` is the shared SQLite store
    used by all stateful tools. Pass None for discovery-only tools."""
    from .tools.discover import handle_list_models

    specs: list[ToolSpec] = [
        ToolSpec(
            name="finance.simulate.list_models",
            description=(
                "List available financial models (asset types). "
                "Returns array of {name, asset_type, description}. "
                "Use this first to know which presets exist."
            ),
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            handler=handle_list_models,
        ),
    ]
    return {s.name: s for s in specs}
