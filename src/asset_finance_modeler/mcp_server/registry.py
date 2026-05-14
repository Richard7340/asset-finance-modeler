from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from asset_finance_modeler.mcp_server.tools.analyze import (
    make_compare,
    make_sensitivity_1d,
    make_sensitivity_grid,
)
from asset_finance_modeler.mcp_server.tools.crud import (
    make_clone_scenario,
    make_create_scenario,
    make_delete_scenario,
    make_list_scenarios,
    make_set_canonical,
)
from asset_finance_modeler.mcp_server.tools.discover import (
    handle_describe_schema,
    handle_list_models,
    handle_list_presets,
    make_handle_load_baseline,
)
from asset_finance_modeler.mcp_server.tools.execute import (
    make_get_genealogy,
    make_get_results,
    make_run,
)
from asset_finance_modeler.mcp_server.tools.output import (
    make_export,
    make_fetch_external,
    make_set_external,
    make_track_stub,
)
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
        ToolSpec(
            name="finance.simulate.describe_schema",
            description=(
                "Return the full JSON Schema for a model's config. "
                "Use this to know which inputs to request from the user."
            ),
            input_schema={
                "type": "object",
                "properties": {"model": {"type": "string", "description": "Model name, e.g. 'gestnova'"}},
                "required": ["model"],
                "additionalProperties": False,
            },
            handler=handle_describe_schema,
        ),
        ToolSpec(
            name="finance.simulate.list_presets",
            description="List available preset baselines for a model.",
            input_schema={
                "type": "object",
                "properties": {"model": {"type": "string", "default": "saas"}},
                "additionalProperties": False,
            },
            handler=handle_list_presets,
        ),
    ]

    if store is not None:
        specs.append(
            ToolSpec(
                name="finance.simulate.load_baseline",
                description=(
                    "Load a preset as a canonical baseline Scenario in the store. "
                    "Returns {scenario_id, name}. Use this before creating overrides."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "model": {"type": "string", "default": "gestnova"},
                        "preset": {"type": "string", "default": "gestnova"},
                    },
                    "additionalProperties": False,
                },
                handler=make_handle_load_baseline(store),
            )
        )
        specs.extend([
            ToolSpec(
                name="finance.simulate.create_scenario",
                description=(
                    "Create a new Scenario as a child of an existing one. "
                    "Overrides use JSONPath syntax: 'revenue.sources[0].pricing.per_unit_per_period'."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "base_scenario_id": {"type": "string"},
                        "description": {"type": "string"},
                        "overrides": {"type": "object", "additionalProperties": True},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "notes": {"type": "string"},
                    },
                    "required": ["name", "base_scenario_id"],
                    "additionalProperties": False,
                },
                handler=make_create_scenario(store),
            ),
            ToolSpec(
                name="finance.simulate.clone_scenario",
                description=(
                    "Branch from an existing Scenario inheriting its overrides; new overrides win on conflict. "
                    "Use this to compose hypotheses: pricing-250 → pricing-250-with-debt."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "scenario_id": {"type": "string"},
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "overrides": {"type": "object", "additionalProperties": True},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "notes": {"type": "string"},
                    },
                    "required": ["scenario_id", "name"],
                    "additionalProperties": False,
                },
                handler=make_clone_scenario(store),
            ),
            ToolSpec(
                name="finance.simulate.list_scenarios",
                description="List scenarios in the store with optional filters.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "base_model": {"type": "string"},
                        "include_deleted": {"type": "boolean", "default": False},
                    },
                    "additionalProperties": False,
                },
                handler=make_list_scenarios(store),
            ),
            ToolSpec(
                name="finance.simulate.delete_scenario",
                description="Soft-delete a Scenario. Canonical scenarios cannot be deleted.",
                input_schema={
                    "type": "object",
                    "properties": {"scenario_id": {"type": "string"}},
                    "required": ["scenario_id"],
                    "additionalProperties": False,
                },
                handler=make_delete_scenario(store),
            ),
            ToolSpec(
                name="finance.simulate.set_canonical",
                description="Mark a Scenario as canonical (protected from deletion).",
                input_schema={
                    "type": "object",
                    "properties": {
                        "scenario_id": {"type": "string"},
                        "name": {"type": "string"},
                    },
                    "required": ["scenario_id"],
                    "additionalProperties": False,
                },
                handler=make_set_canonical(store),
            ),
        ])

        specs.extend([
            ToolSpec(
                name="finance.simulate.run",
                description=(
                    "Execute a Scenario through the financial model. "
                    "Persists full results in the scenario. Returns the summary."
                ),
                input_schema={
                    "type": "object",
                    "properties": {"scenario_id": {"type": "string"}},
                    "required": ["scenario_id"],
                    "additionalProperties": False,
                },
                handler=make_run(store),
            ),
            ToolSpec(
                name="finance.simulate.get_results",
                description=(
                    "Read the cached results of a Scenario. "
                    "Use view to limit payload: summary, pnl, cashflow, balance, unit_econ, valuation, all."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "scenario_id": {"type": "string"},
                        "view": {
                            "type": "string",
                            "enum": [
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
                            ],
                            "default": "summary",
                        },
                    },
                    "required": ["scenario_id"],
                    "additionalProperties": False,
                },
                handler=make_get_results(store),
            ),
            ToolSpec(
                name="finance.simulate.get_genealogy",
                description="Return ancestor and descendant tree of a Scenario.",
                input_schema={
                    "type": "object",
                    "properties": {"scenario_id": {"type": "string"}},
                    "required": ["scenario_id"],
                    "additionalProperties": False,
                },
                handler=make_get_genealogy(store),
            ),
        ])

        specs.extend([
            ToolSpec(
                name="finance.simulate.compare",
                description=(
                    "Side-by-side comparison of N Scenarios (each must have been run). "
                    "Default metrics include revenue_y1, EBITDA margin, cash, runway, LTV/CAC, EV."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "scenario_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                        "metrics": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["scenario_ids"],
                    "additionalProperties": False,
                },
                handler=make_compare(store),
            ),
            ToolSpec(
                name="finance.simulate.sensitivity_1d",
                description=(
                    "Sweep a single variable (JSONPath) across values, return metric values. "
                    "Use to answer 'what if pricing was X, Y, Z?'"
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "scenario_id": {"type": "string"},
                        "variable": {
                            "type": "string",
                            "description": "JSONPath, e.g. 'revenue.sources[0].pricing.per_unit_per_period'",
                        },
                        "values": {"type": "array", "items": {"type": "number"}, "minItems": 1},
                        "metric": {
                            "type": "string",
                            "description": "Summary metric to track, e.g. 'enterprise_value'",
                        },
                    },
                    "required": ["scenario_id", "variable", "values", "metric"],
                    "additionalProperties": False,
                },
                handler=make_sensitivity_1d(store),
            ),
            ToolSpec(
                name="finance.simulate.sensitivity_grid",
                description=(
                    "2D sensitivity grid: sweep two variables and report a metric. "
                    "Classic use: WACC × growth → enterprise_value heatmap."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "scenario_id": {"type": "string"},
                        "var_x": {"type": "string"},
                        "values_x": {"type": "array", "items": {"type": "number"}, "minItems": 1},
                        "var_y": {"type": "string"},
                        "values_y": {"type": "array", "items": {"type": "number"}, "minItems": 1},
                        "metric": {"type": "string"},
                    },
                    "required": ["scenario_id", "var_x", "values_x", "var_y", "values_y", "metric"],
                    "additionalProperties": False,
                },
                handler=make_sensitivity_grid(store),
            ),
        ])

        specs.extend([
            ToolSpec(
                name="finance.simulate.export",
                description=(
                    "Export scenario results in various formats. "
                    "Inline-return for summary/markdown_table/markdown_report/json (when no path). "
                    "File-write for csv/xlsx/json (with path)."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "scenario_id": {"type": "string"},
                        "format": {
                            "type": "string",
                            "enum": ["summary", "markdown_table", "markdown_report", "json", "csv", "xlsx"],
                        },
                        "view": {
                            "type": "string",
                            "enum": ["pnl", "cashflow", "balance", "unit_econ"],
                            "description": "Required for csv and markdown_table",
                        },
                        "path": {"type": "string", "description": "Required for csv/xlsx; optional for json"},
                    },
                    "required": ["scenario_id", "format"],
                    "additionalProperties": False,
                },
                handler=make_export(store),
            ),
            ToolSpec(
                name="finance.simulate.fetch_external",
                description=(
                    "Request the caller to fetch an external benchmark. "
                    "Returns the query payload — the caller then runs WebSearch and calls set_external."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "scenario_id": {"type": "string"},
                        "field_path": {"type": "string"},
                        "query": {"type": "string"},
                        "hint": {"type": "string"},
                    },
                    "required": ["scenario_id", "field_path", "query"],
                    "additionalProperties": False,
                },
                handler=make_fetch_external(store),
            ),
            ToolSpec(
                name="finance.simulate.set_external",
                description=(
                    "Set an external benchmark value on the scenario after fetching it. "
                    "Persists value+source+confidence as overrides."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "scenario_id": {"type": "string"},
                        "field_path": {"type": "string"},
                        "value": {},
                        "source": {"type": "string"},
                        "confidence": {
                            "type": "string",
                            "enum": ["low", "medium", "high"],
                            "default": "medium",
                        },
                    },
                    "required": ["scenario_id", "field_path", "value"],
                    "additionalProperties": False,
                },
                handler=make_set_external(store),
            ),
            ToolSpec(
                name="finance.track.import_real_data",
                description="V2 stub: import real accounting data. Not implemented in v1.",
                input_schema={"type": "object", "additionalProperties": True},
                handler=make_track_stub("import_real_data"),
            ),
            ToolSpec(
                name="finance.track.reconcile",
                description="V2 stub: reconcile model vs actuals. Not implemented in v1.",
                input_schema={"type": "object", "additionalProperties": True},
                handler=make_track_stub("reconcile"),
            ),
            ToolSpec(
                name="finance.track.variance_report",
                description="V2 stub: variance analysis. Not implemented in v1.",
                input_schema={"type": "object", "additionalProperties": True},
                handler=make_track_stub("variance_report"),
            ),
        ])

    return {s.name: s for s in specs}
