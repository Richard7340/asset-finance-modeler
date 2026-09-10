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
from asset_finance_modeler.mcp_server.tools.dashboard import make_generate_dashboard
from asset_finance_modeler.mcp_server.tools.report import make_generate_pdf, make_generate_report
from asset_finance_modeler.mcp_server.tools.output import (
    make_export,
    make_fetch_external,
    make_set_external,
    make_track_stub,
)
from asset_finance_modeler.mcp_server.tools.tracking import (
    make_track_import,
    make_track_reconcile,
    make_track_variance,
)
from asset_finance_modeler.mcp_server.tools.vdr_sharing import (
    handle_explain_vdr,
    handle_import_from_vdr,
    handle_list_workspace_shared,
    handle_share_to_vdr,
)
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], Any]


def build_registry(
    store: SQLiteScenarioStore | None,
    kb_db_path: str | None = None,
    kb_index_path: str | None = None,
    ctx_db_path: str | None = None,
) -> dict[str, ToolSpec]:
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
                description=(
                    "Store real operating data (actuals) for a scenario: "
                    "[{line_path, period_start (YYYY-MM-DD), value}]. "
                    "Line must exist in the frozen results (see trackable lines)."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "scenario_id": {"type": "string"},
                        "actuals": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "line_path": {"type": "string"},
                                    "period_start": {"type": "string"},
                                    "value": {"type": "number"},
                                    "unit": {"type": "string"},
                                    "note": {"type": "string"},
                                },
                            },
                        },
                    },
                    "required": ["scenario_id", "actuals"],
                    "additionalProperties": False,
                },
                handler=make_track_import(store),
            ),
            ToolSpec(
                name="finance.track.reconcile",
                description=(
                    "Base vs actual totals per trackable line for a scenario "
                    "(needs results — run it first)."
                ),
                input_schema={
                    "type": "object",
                    "properties": {"scenario_id": {"type": "string"}},
                    "required": ["scenario_id"],
                    "additionalProperties": False,
                },
                handler=make_track_reconcile(store),
            ),
            ToolSpec(
                name="finance.track.variance_report",
                description=(
                    "Year-by-year variance (base, actual, deviation, %) per line. "
                    "Years without data stay null (not invented)."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "scenario_id": {"type": "string"},
                        "line_path": {"type": "string"},
                    },
                    "required": ["scenario_id"],
                    "additionalProperties": False,
                },
                handler=make_track_variance(store),
            ),
            ToolSpec(
                name="finance.dashboard.generate",
                description=(
                    "Generate an interactive HTML dashboard with Chart.js charts for a "
                    "scenario's results. Returns the HTML and a list of chart ids. "
                    "Pass output_path to write the file to disk."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "scenario_id": {"type": "string"},
                        "output_path": {
                            "type": "string",
                            "description": "Optional file path for the HTML output",
                        },
                    },
                    "required": ["scenario_id"],
                    "additionalProperties": False,
                },
                handler=make_generate_dashboard(store),
            ),
            ToolSpec(
                name="finance.report.generate",
                description=(
                    "Generate a professional financial analysis report — cover page, "
                    "executive summary, assumptions, charts, tables, disclaimer. "
                    "Print-ready HTML with Chart.js visualisations. "
                    "Pass output_path to write the file to disk."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "scenario_id": {"type": "string"},
                        "output_path": {
                            "type": "string",
                            "description": "Optional file path for the HTML output",
                        },
                    },
                    "required": ["scenario_id"],
                    "additionalProperties": False,
                },
                handler=make_generate_report(store),
            ),
            ToolSpec(
                name="finance.report.pdf",
                description=(
                    "Generate a PDF financial report (requires weasyprint) or "
                    "print-ready HTML as fallback. "
                    "When weasyprint is installed, writes a real PDF to output_path. "
                    "Otherwise saves an enhanced HTML file and returns browser-print instructions."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "scenario_id": {"type": "string"},
                        "output_path": {
                            "type": "string",
                            "description": "Target file path (e.g. /tmp/report.pdf). Defaults to /tmp/report_<id>.pdf",
                        },
                    },
                    "required": ["scenario_id"],
                    "additionalProperties": False,
                },
                handler=make_generate_pdf(store),
            ),
        ])

    # Knowledge base (optional)
    if kb_db_path is not None and kb_index_path is not None:
        from asset_finance_modeler.intelligence.embeddings import LocalEmbeddingProvider  # noqa: PLC0415
        from asset_finance_modeler.intelligence.knowledge.base import KnowledgeBase  # noqa: PLC0415
        from .tools.knowledge import (  # noqa: PLC0415
            make_knowledge_add,
            make_knowledge_list_categories,
            make_knowledge_search,
        )

        kb = KnowledgeBase(
            db_path=kb_db_path,
            index_path=kb_index_path,
            embedding_provider=LocalEmbeddingProvider(),
        )
        kb.initialize()

        specs.extend([
            ToolSpec(
                name="finance.knowledge.search",
                description=(
                    "Search the financial knowledge base semantically. "
                    "Returns relevant concepts, formulas, benchmarks, frameworks. "
                    "Use this BEFORE answering technical financial questions."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "top_k": {"type": "integer", "default": 5},
                        "category": {"type": "string"},
                        "user_id": {"type": "string"},
                        "workspace_id": {"type": "string"},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                handler=make_knowledge_search(kb),
            ),
            ToolSpec(
                name="finance.knowledge.add",
                description="Add a new knowledge entry. Optional user_id for company-specific knowledge.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "content": {"type": "string"},
                        "category": {"type": "string", "default": "general"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "user_id": {"type": "string"},
                        "workspace_id": {"type": "string"},
                    },
                    "required": ["title", "content"],
                    "additionalProperties": False,
                },
                handler=make_knowledge_add(kb),
            ),
            ToolSpec(
                name="finance.knowledge.list_categories",
                description="List available knowledge categories with entry counts.",
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                handler=make_knowledge_list_categories(kb),
            ),
        ])

    # Workflows
    from .tools.workflows import (  # noqa: PLC0415
        handle_workflows_describe,
        handle_workflows_list,
        make_workflows_run,
    )

    # Mutable holder for the registry so the dispatcher can resolve tools at run time
    _registry_holder: dict[str, dict[str, ToolSpec]] = {}

    def _registry_provider() -> dict[str, ToolSpec]:
        return _registry_holder["registry"]

    specs.extend([
        ToolSpec(
            name="finance.workflows.list",
            description="List built-in workflow templates with id+name+description+inputs.",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            handler=handle_workflows_list,
        ),
        ToolSpec(
            name="finance.workflows.describe",
            description="Describe a single workflow: full inputs spec + step count.",
            input_schema={
                "type": "object",
                "properties": {"workflow_id": {"type": "string"}},
                "required": ["workflow_id"],
                "additionalProperties": False,
            },
            handler=handle_workflows_describe,
        ),
        ToolSpec(
            name="finance.workflows.run",
            description=(
                "Execute a workflow by id. Pass inputs as object. "
                "Returns the workflow's defined output."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "workflow_id": {"type": "string"},
                    "inputs": {"type": "object", "additionalProperties": True},
                },
                "required": ["workflow_id"],
                "additionalProperties": False,
            },
            handler=make_workflows_run(_registry_provider),
        ),
    ])

    # Context memory (optional)
    if ctx_db_path is not None:
        from asset_finance_modeler.intelligence.context.memory import ContextMemory  # noqa: PLC0415
        from asset_finance_modeler.intelligence.embeddings import LocalEmbeddingProvider  # noqa: PLC0415
        from .tools.context import (  # noqa: PLC0415
            make_context_recent,
            make_context_search,
            make_context_store,
        )

        ctx_mem = ContextMemory(
            db_path=ctx_db_path,
            embedding_provider=LocalEmbeddingProvider(),
        )
        ctx_mem.initialize()

        specs.extend([
            ToolSpec(
                name="finance.context.store",
                description=(
                    "Store a piece of conversation context for later semantic retrieval. "
                    "Use to remember decisions, supuestos del cliente, follow-ups."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"},
                        "key": {"type": "string"},
                        "value": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "workspace_id": {"type": "string"},
                    },
                    "required": ["user_id", "key", "value"],
                    "additionalProperties": False,
                },
                handler=make_context_store(ctx_mem),
            ),
            ToolSpec(
                name="finance.context.search",
                description=(
                    "Semantic search over stored context for a given user. "
                    "Use to recall previous discussions or decisions."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"},
                        "query": {"type": "string"},
                        "top_k": {"type": "integer", "default": 5},
                        "workspace_id": {"type": "string"},
                    },
                    "required": ["user_id", "query"],
                    "additionalProperties": False,
                },
                handler=make_context_search(ctx_mem),
            ),
            ToolSpec(
                name="finance.context.recent",
                description="Return most recent context entries for a user (ordered by created_at desc).",
                input_schema={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"},
                        "limit": {"type": "integer", "default": 10},
                        "workspace_id": {"type": "string"},
                    },
                    "required": ["user_id"],
                    "additionalProperties": False,
                },
                handler=make_context_recent(ctx_mem),
            ),
        ])

    # Wizard tools
    from asset_finance_modeler.wizard.engine import WizardEngine  # noqa: PLC0415
    from asset_finance_modeler.mcp_server.tools.wizard import (  # noqa: PLC0415
        make_wizard_start,
        make_wizard_answer,
        make_wizard_skip,
        make_wizard_back,
        make_wizard_adjust,
        make_wizard_status,
        make_wizard_cancel,
        make_wizard_finalize,
        make_wizard_run,
    )

    wizard_engine = WizardEngine()

    wizard_specs = [
        ToolSpec(
            name="finance.wizard.start",
            description="Start a wizard session for financial model configuration.",
            input_schema={
                "type": "object",
                "properties": {
                    "asset_description": {"type": "string"},
                    "region": {"type": "string"},
                },
                "required": ["asset_description"],
            },
            handler=make_wizard_start(wizard_engine),
        ),
        ToolSpec(
            name="finance.wizard.answer",
            description="Answer the current wizard question.",
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "value": {},
                },
                "required": ["session_id", "value"],
            },
            handler=make_wizard_answer(wizard_engine),
        ),
        ToolSpec(
            name="finance.wizard.skip",
            description="Skip current question — proposes benchmark value.",
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                },
                "required": ["session_id"],
            },
            handler=make_wizard_skip(wizard_engine),
        ),
        ToolSpec(
            name="finance.wizard.back",
            description="Go back to previous question.",
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                },
                "required": ["session_id"],
            },
            handler=make_wizard_back(wizard_engine),
        ),
        ToolSpec(
            name="finance.wizard.adjust",
            description="Adjust a specific input value.",
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "field_path": {"type": "string"},
                    "new_value": {},
                },
                "required": ["session_id", "field_path", "new_value"],
            },
            handler=make_wizard_adjust(wizard_engine),
        ),
        ToolSpec(
            name="finance.wizard.status",
            description="Get wizard progress and current state.",
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                },
                "required": ["session_id"],
            },
            handler=make_wizard_status(wizard_engine),
        ),
        ToolSpec(
            name="finance.wizard.cancel",
            description="Cancel and discard wizard session.",
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                },
                "required": ["session_id"],
            },
            handler=make_wizard_cancel(wizard_engine),
        ),
        ToolSpec(
            name="finance.wizard.finalize",
            description="Finalize wizard — generates scenario spec with assumptions table.",
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                },
                "required": ["session_id"],
            },
            handler=make_wizard_finalize(wizard_engine),
        ),
        ToolSpec(
            name="finance.wizard.run",
            description="Run finalized wizard scenario through the financial model.",
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                },
                "required": ["session_id"],
            },
            handler=make_wizard_run(wizard_engine),
        ),
    ]
    specs.extend(wizard_specs)

    # Knowledge retrieve (always available — uses in-memory index from seeded KB)
    from asset_finance_modeler.intelligence.knowledge.retriever import KBRetriever  # noqa: PLC0415
    from asset_finance_modeler.mcp_server.tools.knowledge_retrieve import (  # noqa: PLC0415
        make_knowledge_retrieve,
    )

    kb_retriever = KBRetriever()
    kb_retriever.initialize()

    specs.append(
        ToolSpec(
            name="finance.knowledge.retrieve",
            description=(
                "Search financial knowledge base — concepts, benchmarks, explanations. "
                "Use to answer questions about financial concepts or get benchmarks."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "asset_type": {"type": "string"},
                    "top_k": {"type": "integer", "default": 5},
                    "layer": {"type": "string"},
                },
                "required": ["topic"],
            },
            handler=make_knowledge_retrieve(kb_retriever),
        )
    )

    # Project tools
    if store is not None:
        from asset_finance_modeler.store.projects import SQLiteProjectStore  # noqa: PLC0415
        from asset_finance_modeler.mcp_server.tools.projects import (  # noqa: PLC0415
            make_project_create,
            make_project_list,
            make_project_get,
            make_project_archive,
        )

        project_store = SQLiteProjectStore(store.db_path)
        project_store.initialize()

        project_specs = [
            ToolSpec(
                name="finance.project.create",
                description="Create a new project to group scenarios.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "user_id": {"type": "string"},
                        "workspace_id": {"type": "string"},
                        "description": {"type": "string"},
                        "asset_type": {"type": "string"},
                        "region": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["name"],
                },
                handler=make_project_create(project_store),
            ),
            ToolSpec(
                name="finance.project.list",
                description="List projects for a user.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"},
                        "workspace_id": {"type": "string"},
                        "include_archived": {"type": "boolean"},
                    },
                },
                handler=make_project_list(project_store),
            ),
            ToolSpec(
                name="finance.project.get",
                description="Get project details with scenario list.",
                input_schema={
                    "type": "object",
                    "properties": {"project_id": {"type": "string"}},
                    "required": ["project_id"],
                },
                handler=make_project_get(project_store),
            ),
            ToolSpec(
                name="finance.project.archive",
                description="Archive a project.",
                input_schema={
                    "type": "object",
                    "properties": {"project_id": {"type": "string"}},
                    "required": ["project_id"],
                },
                handler=make_project_archive(project_store),
            ),
        ]
        specs.extend(project_specs)

        from asset_finance_modeler.mcp_server.tools.portfolio import make_portfolio_analyze  # noqa: PLC0415
        specs.append(ToolSpec(
            name="finance.portfolio.analyze",
            description="Analyze a portfolio of scenarios — aggregated metrics, comparison table, narrative.",
            input_schema={"type": "object", "properties": {
                "scenario_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            }, "required": ["scenario_ids"]},
            handler=make_portfolio_analyze(store),
        ))

        # Scenario recall + diff tools
        from asset_finance_modeler.intelligence.recall import ScenarioRecall  # noqa: PLC0415
        from asset_finance_modeler.mcp_server.tools.scenario_recall import (  # noqa: PLC0415
            make_scenario_diff,
            make_scenario_recall,
            make_recall_project_context,
        )

        scenario_recall = ScenarioRecall()

        specs.extend([
            ToolSpec(
                name="finance.scenario.diff",
                description="Compare two scenarios — input deltas + KPI changes.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "scenario_a_id": {"type": "string"},
                        "scenario_b_id": {"type": "string"},
                    },
                    "required": ["scenario_a_id", "scenario_b_id"],
                },
                handler=make_scenario_diff(store),
            ),
            ToolSpec(
                name="finance.scenario.recall",
                description="Search scenarios by natural language description.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "top_k": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
                handler=make_scenario_recall(scenario_recall),
            ),
            ToolSpec(
                name="finance.agent.recall_project_context",
                description=(
                    "Get narrative summary of a project — all scenarios, best metrics, key changes."
                ),
                input_schema={
                    "type": "object",
                    "properties": {"project_id": {"type": "string"}},
                    "required": ["project_id"],
                },
                handler=make_recall_project_context(project_store, store),
            ),
        ])

    # VDR sharing tools (always available — graceful degradation when token absent)
    specs.extend([
        ToolSpec(
            name="financial.share_to_vdr",
            description=(
                "Export a financial scenario/project report to the Gestnova VDR "
                "for sharing with workspace members."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "scenario_id": {"type": "string", "description": "Scenario ID to export"},
                    "project_id": {"type": "string", "description": "Project ID to export"},
                    "format": {
                        "type": "string",
                        "enum": ["json", "markdown", "html"],
                        "default": "json",
                    },
                    "workspace_id": {
                        "type": "string",
                        "description": "Target workspace ID in Gestnova VDR",
                    },
                },
            },
            handler=handle_share_to_vdr,
        ),
        ToolSpec(
            name="financial.import_from_vdr",
            description="Import financial data from a Gestnova VDR file.",
            input_schema={
                "type": "object",
                "properties": {
                    "vdr_path": {"type": "string", "description": "Path inside the VDR"},
                    "workspace_id": {"type": "string"},
                },
                "required": ["vdr_path"],
            },
            handler=handle_import_from_vdr,
        ),
        ToolSpec(
            name="financial.list_workspace_shared",
            description="List financial reports shared in a workspace VDR folder.",
            input_schema={
                "type": "object",
                "properties": {
                    "workspace_id": {
                        "type": "string",
                        "default": "default",
                        "description": "Workspace ID to list reports for",
                    },
                },
            },
            handler=handle_list_workspace_shared,
        ),
        ToolSpec(
            name="financial.explain_vdr",
            description=(
                "Explain a financial report from VDR in natural language. "
                "Returns a suggested flow to import and analyze the data."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "vdr_path": {"type": "string", "description": "VDR file path to explain"},
                    "question": {"type": "string", "description": "Question about the report"},
                },
                "required": ["vdr_path"],
            },
            handler=handle_explain_vdr,
        ),
    ])

    final_registry = {s.name: s for s in specs}
    _registry_holder["registry"] = final_registry
    return final_registry
