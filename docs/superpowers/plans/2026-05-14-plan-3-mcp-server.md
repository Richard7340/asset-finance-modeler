# Plan 3 — MCP Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Wrap the asset-finance-modeler library (Plans 1+2) as a fully functional MCP server (stdio) exposing 17 `finance.simulate.*` tools and 3 `finance.track.*` stubs, so that any MCP-capable agent (Ian/Gestnova, Aurora, Claude Desktop, etc.) can drive financial modeling conversationally.

**Architecture:** A single `Server` instance from the official `mcp` Python SDK. Tools are declared as `ToolSpec` dataclasses with name + description + JSON schema + handler. Handlers are thin wrappers over the existing library — they translate JSON args → typed calls → JSON results. A single process-wide `SQLiteScenarioStore` is initialized at startup with configurable DB path via env var.

**Tech Stack:** Plan 1+2 stack + `mcp>=1.0` (official Anthropic Python SDK) + `asyncio`.

**Spec reference:** `docs/superpowers/specs/2026-05-14-asset-finance-modeler-design.md` Section 7 (MCP Tools Surface).

**Prerequisites:** Plans 1+2 merged. 128 tests passing.

---

### Task 1: MCP server scaffold + ToolSpec registry + first tool end-to-end

**Files:**
- Modify: `pyproject.toml` (add `mcp` dependency)
- Create: `src/asset_finance_modeler/mcp_server/__init__.py`
- Create: `src/asset_finance_modeler/mcp_server/registry.py`
- Create: `src/asset_finance_modeler/mcp_server/tools/__init__.py`
- Create: `src/asset_finance_modeler/mcp_server/tools/discover.py`
- Create: `src/asset_finance_modeler/mcp_server/server.py`
- Create: `tests/unit/test_mcp_registry.py`
- Create: `tests/unit/test_mcp_tools_discover.py`

- [ ] **Step 1: Add `mcp` to pyproject.toml dependencies**

Edit `pyproject.toml`, in the `[project]` section's `dependencies = [...]`, add `"mcp>=1.0"` after `"jsonpath-ng>=1.6"`:

```toml
dependencies = [
    "pydantic>=2.7,<3",
    "pandas>=2.2,<3",
    "numpy-financial>=1.0",
    "openpyxl>=3.1",
    "PyYAML>=6.0",
    "jsonpath-ng>=1.6",
    "mcp>=1.0",
]
```

Then run:
```bash
cd "/Users/rikyizquierdo/Documents/New project/asset-finance-modeler"
source .venv/bin/activate
pip install -e ".[dev]"
```

Verify `python -c "import mcp; print(mcp.__version__)"` works.

- [ ] **Step 2: Write failing test for ToolSpec registry**

`tests/unit/test_mcp_registry.py`:
```python
import pytest

from asset_finance_modeler.mcp_server.registry import ToolSpec, build_registry


def test_tool_spec_dataclass():
    spec = ToolSpec(
        name="finance.simulate.test",
        description="Test tool",
        input_schema={"type": "object", "properties": {}},
        handler=lambda args: {"ok": True},
    )
    assert spec.name == "finance.simulate.test"
    assert spec.handler({}) == {"ok": True}


def test_registry_contains_simulate_tools():
    registry = build_registry(store=None)
    tool_names = set(registry.keys())
    # At minimum these should exist after the full plan is complete; T1 only needs list_models
    assert "finance.simulate.list_models" in tool_names


def test_registry_handler_callable():
    registry = build_registry(store=None)
    spec = registry["finance.simulate.list_models"]
    result = spec.handler({})
    assert isinstance(result, dict) or isinstance(result, list)
```

- [ ] **Step 3: Write failing test for discover tools (list_models)**

`tests/unit/test_mcp_tools_discover.py`:
```python
from asset_finance_modeler.mcp_server.tools.discover import handle_list_models


def test_list_models_returns_gestnova():
    result = handle_list_models({})
    assert "models" in result
    names = [m["name"] for m in result["models"]]
    assert "gestnova" in names


def test_list_models_model_has_description():
    result = handle_list_models({})
    gn = next(m for m in result["models"] if m["name"] == "gestnova")
    assert "asset_type" in gn
    assert gn["asset_type"] == "saas"
```

- [ ] **Step 4: Run tests, verify fail**

```bash
pytest tests/unit/test_mcp_registry.py tests/unit/test_mcp_tools_discover.py -v
```

Expected: ImportError on multiple modules.

- [ ] **Step 5: Implement ToolSpec + registry skeleton**

`src/asset_finance_modeler/mcp_server/__init__.py`: empty file.

`src/asset_finance_modeler/mcp_server/tools/__init__.py`: empty file.

`src/asset_finance_modeler/mcp_server/registry.py`:
```python
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
```

`src/asset_finance_modeler/mcp_server/tools/discover.py`:
```python
from typing import Any


def handle_list_models(_args: dict[str, Any]) -> dict[str, Any]:
    return {
        "models": [
            {
                "name": "gestnova",
                "asset_type": "saas",
                "description": (
                    "Gestnova SaaS baseline — voice/WhatsApp/email agent platform. "
                    "Pricing per agent-month, cohort retention, multi-LLM COGS, "
                    "team ramp, debt + funding modeling, DCF valuation."
                ),
            },
        ],
    }
```

- [ ] **Step 6: Implement server.py skeleton**

`src/asset_finance_modeler/mcp_server/server.py`:
```python
"""MCP stdio server for asset-finance-modeler.

Run via:
    python -m asset_finance_modeler.mcp_server.server

Environment variables:
    ASSET_FINANCE_DB_PATH — SQLite DB path (default: ~/.asset-finance-modeler/scenarios.db)
"""
import asyncio
import json
import os
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from asset_finance_modeler.store.scenarios import SQLiteScenarioStore

from .registry import ToolSpec, build_registry


def _default_db_path() -> str:
    p = Path(os.environ.get("ASSET_FINANCE_DB_PATH", "")) or Path.home() / ".asset-finance-modeler" / "scenarios.db"
    if isinstance(p, str):
        p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p)


def _build_app() -> tuple[Server, dict[str, ToolSpec]]:
    db_path = _default_db_path()
    store = SQLiteScenarioStore(db_path)
    store.initialize()
    registry = build_registry(store)
    app: Server = Server("asset-finance-modeler")

    @app.list_tools()
    async def _list_tools() -> list[Tool]:
        return [
            Tool(name=spec.name, description=spec.description, inputSchema=spec.input_schema)
            for spec in registry.values()
        ]

    @app.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any] | None) -> list[TextContent]:
        if name not in registry:
            return [TextContent(type="text", text=json.dumps({"error": f"unknown tool: {name}"}))]
        spec = registry[name]
        try:
            result = spec.handler(arguments or {})
        except Exception as exc:  # noqa: BLE001
            return [TextContent(type="text", text=json.dumps({"error": str(exc), "tool": name}))]
        return [TextContent(type="text", text=json.dumps(result, default=str))]

    return app, registry


async def main() -> None:
    app, _registry = _build_app()
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 7: Run tests, verify pass**

```bash
pytest tests/unit/test_mcp_registry.py tests/unit/test_mcp_tools_discover.py -v
```

Expected: 5 passed.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml src/asset_finance_modeler/mcp_server/ tests/unit/test_mcp_registry.py tests/unit/test_mcp_tools_discover.py
git commit -m "feat(mcp): scaffold MCP stdio server + ToolSpec registry + list_models handler"
```

---

### Task 2: Discovery tools — describe_schema, list_presets, load_baseline

**Files:**
- Modify: `src/asset_finance_modeler/mcp_server/tools/discover.py`
- Modify: `src/asset_finance_modeler/mcp_server/registry.py`
- Modify: `tests/unit/test_mcp_tools_discover.py`

- [ ] **Step 1: Append failing tests**

Add to `tests/unit/test_mcp_tools_discover.py`:
```python
import pytest

from asset_finance_modeler.core.scenario import Scenario
from asset_finance_modeler.mcp_server.tools.discover import (
    handle_describe_schema,
    handle_list_presets,
    handle_load_baseline,
)
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore


def test_describe_schema_returns_json_schema():
    result = handle_describe_schema({"model": "gestnova"})
    assert "schema" in result
    schema = result["schema"]
    # JSON Schema shape
    assert schema.get("type") == "object"
    assert "properties" in schema
    # Expected top-level keys exist
    assert "revenue" in schema["properties"]
    assert "cost_of_revenue" in schema["properties"]


def test_describe_schema_unknown_model_raises():
    with pytest.raises(ValueError):
        handle_describe_schema({"model": "nonexistent"})


def test_list_presets_returns_gestnova():
    result = handle_list_presets({"model": "saas"})
    keys = [p["key"] for p in result["presets"]]
    assert "gestnova" in keys


def test_load_baseline_persists_scenario(tmp_path):
    store = SQLiteScenarioStore(str(tmp_path / "scn.db"))
    store.initialize()
    handler = handle_load_baseline.__wrapped__ if hasattr(handle_load_baseline, "__wrapped__") else handle_load_baseline
    # The actual wired handler is closure-bound; here we exercise via build_registry
    from asset_finance_modeler.mcp_server.registry import build_registry
    registry = build_registry(store)
    result = registry["finance.simulate.load_baseline"].handler({"model": "gestnova", "preset": "gestnova"})
    assert "scenario_id" in result
    fetched = store.get(result["scenario_id"])
    assert isinstance(fetched, Scenario)
    assert fetched.is_canonical is True
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
pytest tests/unit/test_mcp_tools_discover.py -v
```

Expected: ImportError on `handle_describe_schema`, `handle_list_presets`, `handle_load_baseline`.

- [ ] **Step 3: Append handlers to discover.py**

```python
from asset_finance_modeler.assets.saas.schema import SaasModelConfig
from asset_finance_modeler.assets.saas.loader import load_preset
from asset_finance_modeler.core.scenario import Scenario, new_scenario_id

_PRESET_INDEX = {
    "saas": ["gestnova"],
}


def handle_describe_schema(args: dict[str, Any]) -> dict[str, Any]:
    model = args.get("model")
    if model not in {"gestnova", "saas"}:
        raise ValueError(f"unknown model: {model!r}. Use 'gestnova' or 'saas'.")
    return {"schema": SaasModelConfig.model_json_schema()}


def handle_list_presets(args: dict[str, Any]) -> dict[str, Any]:
    model = args.get("model", "saas")
    keys = _PRESET_INDEX.get(model, [])
    return {
        "presets": [
            {"key": k, "name": k.capitalize(), "asset_type": model}
            for k in keys
        ],
    }


def make_handle_load_baseline(store) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        preset = args.get("preset", "gestnova")
        # Verify preset loads
        load_preset(preset)
        scenario = Scenario(
            id=new_scenario_id(),
            name=f"{preset}-baseline",
            description=f"Canonical baseline for {preset}",
            base_model=preset,
            overrides={},
            is_canonical=True,
            tags=["baseline"],
        )
        store.save(scenario)
        return {"scenario_id": scenario.id, "name": scenario.name}

    return _handle
```

- [ ] **Step 4: Wire the new handlers into the registry**

In `src/asset_finance_modeler/mcp_server/registry.py`, replace `build_registry` body:

```python
def build_registry(store: SQLiteScenarioStore | None) -> dict[str, ToolSpec]:
    from .tools.discover import (
        handle_describe_schema,
        handle_list_models,
        handle_list_presets,
        make_handle_load_baseline,
    )

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

    return {s.name: s for s in specs}
```

- [ ] **Step 5: Run tests, verify pass**

```bash
pytest tests/unit/test_mcp_tools_discover.py -v
```

Expected: 6 passed (4 new + 2 from T1).

- [ ] **Step 6: Commit**

```bash
git add src/asset_finance_modeler/mcp_server/ tests/unit/test_mcp_tools_discover.py
git commit -m "feat(mcp): discovery tools — describe_schema, list_presets, load_baseline"
```

---

### Task 3: Scenario CRUD tools (create, clone, list, delete, set_canonical)

**Files:**
- Create: `src/asset_finance_modeler/mcp_server/tools/crud.py`
- Modify: `src/asset_finance_modeler/mcp_server/registry.py`
- Create: `tests/unit/test_mcp_tools_crud.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_mcp_tools_crud.py`:
```python
import pytest

from asset_finance_modeler.mcp_server.registry import build_registry
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore


@pytest.fixture
def store_and_baseline(tmp_path):
    store = SQLiteScenarioStore(str(tmp_path / "s.db"))
    store.initialize()
    reg = build_registry(store)
    load = reg["finance.simulate.load_baseline"].handler
    baseline_id = load({"model": "gestnova", "preset": "gestnova"})["scenario_id"]
    return store, reg, baseline_id


def test_create_scenario(store_and_baseline):
    store, reg, baseline_id = store_and_baseline
    create = reg["finance.simulate.create_scenario"].handler
    result = create({
        "name": "pricing-250",
        "base_scenario_id": baseline_id,
        "overrides": {"revenue.sources[0].pricing.per_unit_per_period": 250},
        "notes": "Lower price",
    })
    assert "scenario_id" in result
    fetched = store.get(result["scenario_id"])
    assert fetched.name == "pricing-250"
    assert fetched.parent_scenario_id == baseline_id


def test_clone_scenario(store_and_baseline):
    store, reg, baseline_id = store_and_baseline
    create = reg["finance.simulate.create_scenario"].handler
    clone = reg["finance.simulate.clone_scenario"].handler

    first = create({
        "name": "first",
        "base_scenario_id": baseline_id,
        "overrides": {"revenue.sources[0].pricing.per_unit_per_period": 250},
    })
    second = clone({
        "scenario_id": first["scenario_id"],
        "name": "second-with-extra",
        "overrides": {"operating_expenses.infra_fixed_eur": 600},
    })
    assert "scenario_id" in second
    fetched = store.get(second["scenario_id"])
    # Clone inherits parent's overrides + adds its own
    assert fetched.overrides["revenue.sources[0].pricing.per_unit_per_period"] == 250
    assert fetched.overrides["operating_expenses.infra_fixed_eur"] == 600
    assert fetched.parent_scenario_id == first["scenario_id"]


def test_list_scenarios(store_and_baseline):
    store, reg, baseline_id = store_and_baseline
    create = reg["finance.simulate.create_scenario"].handler
    create({"name": "a", "base_scenario_id": baseline_id, "overrides": {}})
    create({"name": "b", "base_scenario_id": baseline_id, "overrides": {}})
    list_tool = reg["finance.simulate.list_scenarios"].handler
    result = list_tool({})
    assert "scenarios" in result
    names = [s["name"] for s in result["scenarios"]]
    assert "a" in names and "b" in names
    assert "gestnova-baseline" in names


def test_delete_scenario(store_and_baseline):
    store, reg, baseline_id = store_and_baseline
    create = reg["finance.simulate.create_scenario"].handler
    delete = reg["finance.simulate.delete_scenario"].handler
    s = create({"name": "x", "base_scenario_id": baseline_id, "overrides": {}})
    delete({"scenario_id": s["scenario_id"]})
    assert store.get(s["scenario_id"]).is_deleted is True


def test_delete_canonical_returns_error(store_and_baseline):
    store, reg, baseline_id = store_and_baseline
    delete = reg["finance.simulate.delete_scenario"].handler
    # Baseline is canonical
    result = delete({"scenario_id": baseline_id})
    assert "error" in result


def test_set_canonical(store_and_baseline):
    store, reg, baseline_id = store_and_baseline
    create = reg["finance.simulate.create_scenario"].handler
    set_canonical = reg["finance.simulate.set_canonical"].handler
    s = create({"name": "candidate", "base_scenario_id": baseline_id, "overrides": {}})
    set_canonical({"scenario_id": s["scenario_id"], "name": "new-baseline"})
    fetched = store.get(s["scenario_id"])
    assert fetched.is_canonical is True
    assert fetched.name == "new-baseline"
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
pytest tests/unit/test_mcp_tools_crud.py -v
```

Expected: KeyError on missing tools.

- [ ] **Step 3: Implement crud.py**

`src/asset_finance_modeler/mcp_server/tools/crud.py`:
```python
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
```

- [ ] **Step 4: Wire CRUD tools into registry**

In `src/asset_finance_modeler/mcp_server/registry.py`, inside the `if store is not None:` block, append five more ToolSpecs:

```python
    if store is not None:
        from .tools.crud import (
            make_clone_scenario,
            make_create_scenario,
            make_delete_scenario,
            make_list_scenarios,
            make_set_canonical,
        )

        specs.append(
            ToolSpec(
                name="finance.simulate.load_baseline",
                # ... (existing)
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

    return {s.name: s for s in specs}
```

(Adapt the existing `load_baseline` insertion so that it doesn't duplicate; the snippet above replaces the single `specs.append(load_baseline)` with `specs.append(load_baseline); specs.extend([...])`.)

- [ ] **Step 5: Run tests, verify pass**

```bash
pytest tests/unit/test_mcp_tools_crud.py -v
```

Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add src/asset_finance_modeler/mcp_server/ tests/unit/test_mcp_tools_crud.py
git commit -m "feat(mcp): scenario CRUD tools (create, clone, list, delete, set_canonical)"
```

---

### Task 4: Execution tools (run, get_results) + genealogy tool

**Files:**
- Create: `src/asset_finance_modeler/mcp_server/tools/execute.py`
- Modify: `src/asset_finance_modeler/mcp_server/registry.py`
- Create: `tests/unit/test_mcp_tools_execute.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_mcp_tools_execute.py`:
```python
import pytest

from asset_finance_modeler.mcp_server.registry import build_registry
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore


@pytest.fixture
def reg_with_baseline(tmp_path):
    store = SQLiteScenarioStore(str(tmp_path / "s.db"))
    store.initialize()
    reg = build_registry(store)
    baseline_id = reg["finance.simulate.load_baseline"].handler(
        {"model": "gestnova", "preset": "gestnova"}
    )["scenario_id"]
    return store, reg, baseline_id


def test_run_persists_summary_in_results_snapshot(reg_with_baseline):
    store, reg, baseline_id = reg_with_baseline
    run = reg["finance.simulate.run"].handler
    result = run({"scenario_id": baseline_id})
    assert "summary" in result
    assert "revenue_y1" in result["summary"]
    # Persisted on the scenario row
    fetched = store.get(baseline_id)
    assert "summary" in fetched.results_snapshot


def test_get_results_summary_view(reg_with_baseline):
    store, reg, baseline_id = reg_with_baseline
    reg["finance.simulate.run"].handler({"scenario_id": baseline_id})
    get_results = reg["finance.simulate.get_results"].handler
    out = get_results({"scenario_id": baseline_id, "view": "summary"})
    assert "summary" in out
    assert "revenue_y1" in out["summary"]


def test_get_results_pnl_view(reg_with_baseline):
    store, reg, baseline_id = reg_with_baseline
    reg["finance.simulate.run"].handler({"scenario_id": baseline_id})
    get_results = reg["finance.simulate.get_results"].handler
    out = get_results({"scenario_id": baseline_id, "view": "pnl"})
    assert "pnl" in out
    assert "revenue" in out["pnl"]
    assert len(out["pnl"]["revenue"]) == 60


def test_get_results_all_view(reg_with_baseline):
    store, reg, baseline_id = reg_with_baseline
    reg["finance.simulate.run"].handler({"scenario_id": baseline_id})
    get_results = reg["finance.simulate.get_results"].handler
    out = get_results({"scenario_id": baseline_id, "view": "all"})
    # 'all' should expose every view
    for key in ["summary", "pnl", "cashflow", "balance", "unit_econ", "valuation"]:
        assert key in out


def test_get_genealogy(reg_with_baseline):
    store, reg, baseline_id = reg_with_baseline
    create = reg["finance.simulate.create_scenario"].handler
    a = create({"name": "a", "base_scenario_id": baseline_id, "overrides": {}})["scenario_id"]
    b = create({"name": "b", "base_scenario_id": a, "overrides": {}})["scenario_id"]

    genealogy = reg["finance.simulate.get_genealogy"].handler
    out = genealogy({"scenario_id": b})
    anc_names = [a["name"] for a in out["ancestors"]]
    assert anc_names == ["a", "gestnova-baseline"]


def test_run_unknown_scenario_returns_error(reg_with_baseline):
    _, reg, _ = reg_with_baseline
    run = reg["finance.simulate.run"].handler
    out = run({"scenario_id": "nonexistent"})
    assert "error" in out
```

- [ ] **Step 2: Run tests, verify fail**

```bash
pytest tests/unit/test_mcp_tools_execute.py -v
```

Expected: KeyError on missing tools.

- [ ] **Step 3: Implement execute.py**

`src/asset_finance_modeler/mcp_server/tools/execute.py`:
```python
from typing import Any

from asset_finance_modeler.core.scenario import run_scenario_saas
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore

_VIEWS = ["summary", "pnl", "cashflow", "balance", "unit_econ", "valuation", "debt_metrics", "revenue_breakdown", "sensitivity", "all"]


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

        results = run_scenario_saas(scenario)
        full = {
            "summary": dict(results.summary),
            "pnl": results.pnl,
            "cashflow": results.cashflow,
            "balance": results.balance,
            "unit_econ": results.unit_econ,
            "valuation": results.valuation,
            "debt_metrics": results.debt_metrics,
            "revenue_breakdown": results.revenue_breakdown,
            "sensitivity": results.sensitivity,
        }

        scenario.results_snapshot = full
        store.save(scenario)
        return {"scenario_id": scenario_id, "summary": full["summary"]}

    return _handle


def make_get_results(store: SQLiteScenarioStore) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        scenario_id = args["scenario_id"]
        view = args.get("view", "summary")
        scenario = store.get(scenario_id)
        if scenario is None:
            return {"error": f"scenario_id {scenario_id!r} not found"}
        if not scenario.results_snapshot:
            return {"error": f"scenario {scenario_id!r} has no results — call finance.simulate.run first"}
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
```

- [ ] **Step 4: Wire into registry**

In the `if store is not None:` block of `registry.py`, after the CRUD specs.extend([...]), append:

```python
        from .tools.execute import (
            make_get_genealogy,
            make_get_results,
            make_run,
        )

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
                            "enum": ["summary", "pnl", "cashflow", "balance", "unit_econ", "valuation", "debt_metrics", "revenue_breakdown", "sensitivity", "all"],
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
```

- [ ] **Step 5: Run tests, verify pass**

```bash
pytest tests/unit/test_mcp_tools_execute.py -v
```

Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add src/asset_finance_modeler/mcp_server/ tests/unit/test_mcp_tools_execute.py
git commit -m "feat(mcp): execution tools — run, get_results (views), get_genealogy"
```

---

### Task 5: Analysis tools (compare, sensitivity_1d, sensitivity_grid)

**Files:**
- Create: `src/asset_finance_modeler/mcp_server/tools/analyze.py`
- Modify: `src/asset_finance_modeler/mcp_server/registry.py`
- Create: `tests/unit/test_mcp_tools_analyze.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_mcp_tools_analyze.py`:
```python
import pytest

from asset_finance_modeler.mcp_server.registry import build_registry
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore


@pytest.fixture
def reg_three_scenarios(tmp_path):
    store = SQLiteScenarioStore(str(tmp_path / "s.db"))
    store.initialize()
    reg = build_registry(store)
    baseline_id = reg["finance.simulate.load_baseline"].handler(
        {"model": "gestnova", "preset": "gestnova"}
    )["scenario_id"]
    create = reg["finance.simulate.create_scenario"].handler
    cheap = create({
        "name": "cheap",
        "base_scenario_id": baseline_id,
        "overrides": {"revenue.sources[0].pricing.per_unit_per_period": 200},
    })["scenario_id"]
    expensive = create({
        "name": "expensive",
        "base_scenario_id": baseline_id,
        "overrides": {"revenue.sources[0].pricing.per_unit_per_period": 400},
    })["scenario_id"]
    # Run all three
    run = reg["finance.simulate.run"].handler
    for sid in (baseline_id, cheap, expensive):
        run({"scenario_id": sid})
    return store, reg, [baseline_id, cheap, expensive]


def test_compare(reg_three_scenarios):
    _, reg, ids = reg_three_scenarios
    compare = reg["finance.simulate.compare"].handler
    out = compare({"scenario_ids": ids})
    assert "table" in out
    table = out["table"]
    assert table["scenarios"] == ["gestnova-baseline", "cheap", "expensive"]
    # revenue_y1 should be ordered by pricing
    revs = table["metrics"]["revenue_y1"]
    assert revs[1] < revs[0] < revs[2]


def test_sensitivity_1d(reg_three_scenarios):
    _, reg, ids = reg_three_scenarios
    sens = reg["finance.simulate.sensitivity_1d"].handler
    out = sens({
        "scenario_id": ids[0],
        "variable": "revenue.sources[0].pricing.per_unit_per_period",
        "values": [200, 300, 400],
        "metric": "revenue_end_period",
    })
    assert "points" in out
    assert len(out["points"]) == 3
    vals = [p["metric_value"] for p in out["points"]]
    assert vals[0] < vals[1] < vals[2]


def test_sensitivity_grid(reg_three_scenarios):
    _, reg, ids = reg_three_scenarios
    grid_tool = reg["finance.simulate.sensitivity_grid"].handler
    out = grid_tool({
        "scenario_id": ids[0],
        "var_x": "revenue.sources[0].pricing.per_unit_per_period",
        "values_x": [200, 300],
        "var_y": "revenue.sources[0].retention.monthly_churn_rate",
        "values_y": [0.01, 0.05],
        "metric": "enterprise_value",
    })
    assert "grid" in out
    grid = out["grid"]
    assert len(grid) == 2  # rows = len(values_x)
    assert len(grid[0]) == 2  # cols = len(values_y)
    # Higher churn (col 1) → lower EV
    assert grid[0][0] > grid[0][1]


def test_compare_missing_results_returns_error(tmp_path):
    store = SQLiteScenarioStore(str(tmp_path / "s.db"))
    store.initialize()
    reg = build_registry(store)
    baseline_id = reg["finance.simulate.load_baseline"].handler(
        {"model": "gestnova", "preset": "gestnova"}
    )["scenario_id"]
    # NOT run — no results_snapshot
    compare = reg["finance.simulate.compare"].handler
    out = compare({"scenario_ids": [baseline_id]})
    assert "error" in out
```

- [ ] **Step 2: Run tests, verify fail**

```bash
pytest tests/unit/test_mcp_tools_analyze.py -v
```

Expected: KeyError.

- [ ] **Step 3: Implement analyze.py**

`src/asset_finance_modeler/mcp_server/tools/analyze.py`:
```python
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
            # store.compare_scenarios reads s.results_snapshot["summary"]
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
            return {"error": f"scenario_id not found"}
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
            "var_x": var_x, "var_y": var_y,
            "values_x": values_x, "values_y": values_y,
            "metric": metric,
            "grid": grid,
        }

    return _handle
```

- [ ] **Step 4: Wire into registry**

Inside `if store is not None:` block, append:

```python
        from .tools.analyze import (
            make_compare,
            make_sensitivity_1d,
            make_sensitivity_grid,
        )

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
                        "variable": {"type": "string", "description": "JSONPath, e.g. 'revenue.sources[0].pricing.per_unit_per_period'"},
                        "values": {"type": "array", "items": {"type": "number"}, "minItems": 1},
                        "metric": {"type": "string", "description": "Summary metric to track, e.g. 'enterprise_value'"},
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
```

- [ ] **Step 5: Run tests, verify pass**

```bash
pytest tests/unit/test_mcp_tools_analyze.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add src/asset_finance_modeler/mcp_server/ tests/unit/test_mcp_tools_analyze.py
git commit -m "feat(mcp): analysis tools — compare, sensitivity_1d, sensitivity_grid"
```

---

### Task 6: Export tool + external delegation + track stubs

**Files:**
- Create: `src/asset_finance_modeler/mcp_server/tools/output.py`
- Modify: `src/asset_finance_modeler/mcp_server/registry.py`
- Create: `tests/unit/test_mcp_tools_output.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_mcp_tools_output.py`:
```python
import json

import pytest

from asset_finance_modeler.mcp_server.registry import build_registry
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore


@pytest.fixture
def reg_with_run(tmp_path):
    store = SQLiteScenarioStore(str(tmp_path / "s.db"))
    store.initialize()
    reg = build_registry(store)
    sid = reg["finance.simulate.load_baseline"].handler(
        {"model": "gestnova", "preset": "gestnova"}
    )["scenario_id"]
    reg["finance.simulate.run"].handler({"scenario_id": sid})
    return store, reg, sid, tmp_path


def test_export_csv(reg_with_run):
    store, reg, sid, tmp_path = reg_with_run
    export = reg["finance.simulate.export"].handler
    out_path = tmp_path / "pnl.csv"
    result = export({
        "scenario_id": sid,
        "format": "csv",
        "view": "pnl",
        "path": str(out_path),
    })
    assert result["ok"] is True
    assert out_path.exists()
    assert "revenue" in out_path.read_text()


def test_export_xlsx(reg_with_run):
    store, reg, sid, tmp_path = reg_with_run
    export = reg["finance.simulate.export"].handler
    out_path = tmp_path / "model.xlsx"
    result = export({
        "scenario_id": sid,
        "format": "xlsx",
        "path": str(out_path),
    })
    assert result["ok"] is True
    assert out_path.exists()


def test_export_markdown_report_inline(reg_with_run):
    store, reg, sid, tmp_path = reg_with_run
    export = reg["finance.simulate.export"].handler
    result = export({
        "scenario_id": sid,
        "format": "markdown_report",
    })
    # No path → return content inline
    assert "content" in result
    assert "Revenue" in result["content"] or "revenue" in result["content"]


def test_export_json_inline(reg_with_run):
    store, reg, sid, _ = reg_with_run
    export = reg["finance.simulate.export"].handler
    result = export({"scenario_id": sid, "format": "json"})
    parsed = json.loads(result["content"])
    assert "summary" in parsed


def test_fetch_external_returns_query_instruction(reg_with_run):
    store, reg, sid, _ = reg_with_run
    fetch = reg["finance.simulate.fetch_external"].handler
    out = fetch({
        "scenario_id": sid,
        "field_path": "external_data.benchmarks.saas_churn_p50",
        "query": "SaaS B2B average monthly churn 2025",
        "hint": "industry reports preferred",
    })
    # fetch_external does NOT execute HTTP — returns instruction
    assert out["query"] == "SaaS B2B average monthly churn 2025"
    assert out["field_path"] == "external_data.benchmarks.saas_churn_p50"


def test_set_external_persists_value(reg_with_run):
    store, reg, sid, _ = reg_with_run
    set_ext = reg["finance.simulate.set_external"].handler
    out = set_ext({
        "scenario_id": sid,
        "field_path": "external_data.benchmarks.saas_churn_p50",
        "value": 0.018,
        "source": "ChartMogul SaaS Benchmarks 2025",
        "confidence": "high",
    })
    assert out["ok"] is True
    # The scenario overrides now contains the new benchmark
    s = store.get(sid)
    assert s.overrides.get("external_data.benchmarks.saas_churn_p50.value") == 0.018


def test_track_import_real_data_stubbed(reg_with_run):
    _, reg, _, _ = reg_with_run
    h = reg["finance.track.import_real_data"].handler
    out = h({"source": "holded", "period": "2026-04"})
    assert "error" in out
    assert "v2" in out["error"].lower() or "not" in out["error"].lower()
```

- [ ] **Step 2: Run tests, verify fail**

```bash
pytest tests/unit/test_mcp_tools_output.py -v
```

Expected: KeyError.

- [ ] **Step 3: Implement output.py**

`src/asset_finance_modeler/mcp_server/tools/output.py`:
```python
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
```

- [ ] **Step 4: Wire tools into registry**

Inside `if store is not None:` block, append:

```python
        from .tools.output import (
            make_export,
            make_fetch_external,
            make_set_external,
            make_track_stub,
        )

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
                        "confidence": {"type": "string", "enum": ["low", "medium", "high"], "default": "medium"},
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
```

- [ ] **Step 5: Run tests, verify pass**

```bash
pytest tests/unit/test_mcp_tools_output.py -v
```

Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add src/asset_finance_modeler/mcp_server/ tests/unit/test_mcp_tools_output.py
git commit -m "feat(mcp): export tool + fetch/set_external delegation + finance.track.* stubs"
```

---

### Task 7: Integration smoke test over MCP stdio (in-process)

**Files:**
- Create: `tests/integration/test_mcp_smoke.py`

- [ ] **Step 1: Write the integration test**

`tests/integration/test_mcp_smoke.py`:
```python
"""In-process smoke test exercising the MCP server registry end-to-end
without spawning a subprocess (which is brittle on macOS .venv hidden flag)."""
import pytest

from asset_finance_modeler.mcp_server.registry import build_registry
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore


def test_full_workflow_via_registry(tmp_path):
    store = SQLiteScenarioStore(str(tmp_path / "smoke.db"))
    store.initialize()
    reg = build_registry(store)

    # 1. Discovery
    models = reg["finance.simulate.list_models"].handler({})
    assert any(m["name"] == "gestnova" for m in models["models"])
    schema = reg["finance.simulate.describe_schema"].handler({"model": "gestnova"})
    assert "revenue" in schema["schema"]["properties"]
    presets = reg["finance.simulate.list_presets"].handler({"model": "saas"})
    assert any(p["key"] == "gestnova" for p in presets["presets"])

    # 2. Load baseline
    baseline = reg["finance.simulate.load_baseline"].handler(
        {"model": "gestnova", "preset": "gestnova"}
    )
    baseline_id = baseline["scenario_id"]

    # 3. Branch + run
    create = reg["finance.simulate.create_scenario"].handler
    pricing_200 = create({
        "name": "pricing-200",
        "base_scenario_id": baseline_id,
        "overrides": {"revenue.sources[0].pricing.per_unit_per_period": 200},
    })["scenario_id"]
    pricing_400 = create({
        "name": "pricing-400",
        "base_scenario_id": baseline_id,
        "overrides": {"revenue.sources[0].pricing.per_unit_per_period": 400},
    })["scenario_id"]

    run = reg["finance.simulate.run"].handler
    for sid in (baseline_id, pricing_200, pricing_400):
        run({"scenario_id": sid})

    # 4. Compare
    table = reg["finance.simulate.compare"].handler({
        "scenario_ids": [baseline_id, pricing_200, pricing_400]
    })["table"]
    assert len(table["scenarios"]) == 3
    revs = table["metrics"]["revenue_y1"]
    assert revs[1] < revs[0] < revs[2]

    # 5. Sensitivity
    sens = reg["finance.simulate.sensitivity_1d"].handler({
        "scenario_id": baseline_id,
        "variable": "revenue.sources[0].retention.monthly_churn_rate",
        "values": [0.01, 0.03, 0.05],
        "metric": "enterprise_value",
    })
    assert len(sens["points"]) == 3
    evs = [p["metric_value"] for p in sens["points"]]
    assert evs[0] > evs[2]  # lower churn → higher EV

    # 6. Export
    out_csv = tmp_path / "pnl.csv"
    export_result = reg["finance.simulate.export"].handler({
        "scenario_id": baseline_id,
        "format": "csv",
        "view": "pnl",
        "path": str(out_csv),
    })
    assert export_result["ok"] is True
    assert out_csv.exists()

    report = reg["finance.simulate.export"].handler({
        "scenario_id": baseline_id,
        "format": "markdown_report",
    })
    assert "content" in report

    # 7. Genealogy
    g = reg["finance.simulate.get_genealogy"].handler({"scenario_id": pricing_200})
    assert g["ancestors"][0]["name"] == "gestnova-baseline"

    # 8. External delegation flow
    fetch = reg["finance.simulate.fetch_external"].handler({
        "scenario_id": baseline_id,
        "field_path": "external_data.benchmarks.saas_churn_p50",
        "query": "SaaS B2B median monthly churn 2025",
    })
    assert "query" in fetch
    set_result = reg["finance.simulate.set_external"].handler({
        "scenario_id": baseline_id,
        "field_path": "external_data.benchmarks.saas_churn_p50",
        "value": 0.018,
        "source": "ChartMogul SaaS Benchmarks 2025",
    })
    assert set_result["ok"] is True

    # 9. Canonical protection
    delete = reg["finance.simulate.delete_scenario"].handler
    fail = delete({"scenario_id": baseline_id})
    assert "error" in fail
    ok = delete({"scenario_id": pricing_400})
    assert ok.get("ok") is True

    # 10. List scenarios
    listing = reg["finance.simulate.list_scenarios"].handler({})
    names = [s["name"] for s in listing["scenarios"]]
    assert "gestnova-baseline" in names
    # pricing_400 was deleted → not in default listing
    assert "pricing-400" not in names

    # 11. Track stubs return v2 error
    track = reg["finance.track.import_real_data"].handler({"source": "holded"})
    assert "v2" in track["error"].lower() or "not implemented" in track["error"].lower()
```

- [ ] **Step 2: Run the test**

```bash
pytest tests/integration/test_mcp_smoke.py -v
```

Expected: 1 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_mcp_smoke.py
git commit -m "test(mcp): in-process smoke covering all 17 finance.simulate.* tools + track stubs"
```

---

### Task 8: Real MCP stdio handshake test (subprocess + JSONRPC)

**Files:**
- Create: `tests/integration/test_mcp_stdio.py`

- [ ] **Step 1: Write the stdio integration test**

`tests/integration/test_mcp_stdio.py`:
```python
"""Subprocess-based test: launches the MCP server, sends a JSONRPC
tools/list request, verifies response. Lightweight — does not cover full surface
(that's `test_mcp_smoke.py`). This test exists to prove the server actually starts
and the registry is reachable over stdio."""
import json
import os
import subprocess
import sys
from pathlib import Path


def test_mcp_server_starts_and_lists_tools(tmp_path):
    env = os.environ.copy()
    repo_root = Path(__file__).parent.parent.parent
    env["PYTHONPATH"] = str(repo_root / "src")
    env["ASSET_FINANCE_DB_PATH"] = str(tmp_path / "stdio.db")

    proc = subprocess.Popen(
        [sys.executable, "-m", "asset_finance_modeler.mcp_server.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
    )

    try:
        # Initialize
        initialize_req = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        }) + "\n"
        proc.stdin.write(initialize_req)
        proc.stdin.flush()
        init_resp_line = proc.stdout.readline()
        init_resp = json.loads(init_resp_line)
        assert init_resp.get("id") == 1
        assert "result" in init_resp

        # Send initialized notification
        notif = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
        proc.stdin.write(notif)
        proc.stdin.flush()

        # tools/list
        tools_req = json.dumps({
            "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {},
        }) + "\n"
        proc.stdin.write(tools_req)
        proc.stdin.flush()
        tools_resp_line = proc.stdout.readline()
        tools_resp = json.loads(tools_resp_line)
        assert tools_resp.get("id") == 2
        tools = tools_resp["result"]["tools"]
        names = {t["name"] for t in tools}
        # Must contain at least these:
        assert "finance.simulate.list_models" in names
        assert "finance.simulate.run" in names
        assert "finance.simulate.compare" in names
        assert "finance.track.import_real_data" in names

    finally:
        proc.stdin.close()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
```

- [ ] **Step 2: Run the test**

```bash
pytest tests/integration/test_mcp_stdio.py -v
```

Expected: 1 passed.

If the test hangs, the server is not flushing stdout or not implementing the protocol correctly. Check `proc.stderr` for errors.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_mcp_stdio.py
git commit -m "test(mcp): subprocess stdio handshake verifying server starts and tools/list returns 20+ tools"
```

---

### Task 9: Final sanity + bridge plan reference doc

**Files:**
- Modify: `README.md`
- Create: `docs/INTEGRATION.md`
- Verify all gates pass

- [ ] **Step 1: Update README**

Edit `README.md`:

```markdown
# asset-finance-modeler

Comprehensive financial modeling engine for SaaS and other assets, exposed as MCP tools.

V1 covers SaaS (Gestnova baseline shipped); designed to scale to renewables, real estate, generic business.

## Architecture

- `core/` — asset-agnostic primitives (TimeGrid, GrowthCurve, AmortizationSchedule, statements, valuation, scenario)
- `assets/saas/` — SaaS schema + engines + orchestrator (`SaasModel`) + presets
- `store/` — SQLite scenarios + exports + compare + sensitivity
- `cli/` — argparse CLI
- `mcp_server/` — MCP stdio server exposing 17 `finance.simulate.*` tools + 3 `finance.track.*` stubs

## Quickstart (dev)

```
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                                  # ≥175 tests
ruff check src/ tests/                  # clean
mypy src/                               # clean
```

## CLI usage

```
PYTHONPATH=src python -m asset_finance_modeler.cli.main list-models
PYTHONPATH=src python -m asset_finance_modeler.cli.main run --preset gestnova --output summary
PYTHONPATH=src python -m asset_finance_modeler.cli.main run --preset gestnova \
    --override 'revenue.sources[0].pricing.per_unit_per_period=250' \
    --output report
```

## MCP server

```
PYTHONPATH=src python -m asset_finance_modeler.mcp_server.server
```

Configure your MCP client to point to this command via stdio. See `docs/INTEGRATION.md` for wiring into Gestnova/Ian.

## Specs and plans

- `docs/superpowers/specs/2026-05-14-asset-finance-modeler-design.md` — design
- `docs/superpowers/plans/2026-05-14-plan-1-foundation-engine.md` — done
- `docs/superpowers/plans/2026-05-14-plan-2-scenarios-store-exports-cli.md` — done
- `docs/superpowers/plans/2026-05-14-plan-3-mcp-server.md` — done
```

- [ ] **Step 2: Create INTEGRATION.md**

`docs/INTEGRATION.md`:
```markdown
# Integration with Gestnova / Ian

## Bridge plan (3-4h)

After the modeler MCP server is live, wire it into `livekit-voice-platform` (Ian) as follows:

### 1. MCP connector configuration

Add an entry to the per-company MCP config (e.g. `config/companies/gestnova.json`):

```json
{
  "mcpServers": {
    "asset-finance-modeler": {
      "command": "python",
      "args": ["-m", "asset_finance_modeler.mcp_server.server"],
      "env": {
        "PYTHONPATH": "/path/to/asset-finance-modeler/src",
        "ASSET_FINANCE_DB_PATH": "/var/lib/gestnova/finance.db"
      }
    }
  }
}
```

### 2. Skill registry — `financial-analysis` skill

Create `src/skills/core/financial-analysis.skill.ts` declaring the MCP tools with LLM-friendly descriptions. The 17 `finance.simulate.*` tools become Ian's surface.

### 3. Prompt update for Ian

Ian needs to learn:
- When to declare assumptions (user has no data) vs use real data (V2)
- Conversational pattern: discover → load baseline → create scenario → run → compare → export
- Output format choice based on channel: summary in WhatsApp, report by email, dashboard via artifact

### 4. `buildModelInputsFromCompanyData` helper (V2 / when ready)

Extract `Expense`, `Invoice`, `Customer`, `Agent` from Prisma → produce a partial `SaasModelConfig` overlay. Use as overrides when running scenarios for Gestnova's own books.

### 5. Smoke test

E2E: WhatsApp message "Ian, simula Gestnova con bajada a 250€/agente, mándame el cash flow en Excel" should:
1. Trigger `finance.simulate.load_baseline` → `create_scenario` (override) → `run` → `export` (xlsx) → return file URL/path to user.

## Architecture invariants

- The modeler **never** renders UI / HTML / PDF. It returns structured data.
- Ian decides rendering (artifact dashboard, PDF via DocumentTemplate, CSV attachment, WhatsApp markdown).
- The modeler is multi-consumer: Aurora can use the same MCP, scripts can use the CLI.

## Cost / billing

Tokens used by Ian when reasoning over the modeler responses are billed normally. The modeler itself does no LLM calls (web search delegated to caller).
```

- [ ] **Step 3: Run all gates**

```bash
cd "/Users/rikyizquierdo/Documents/New project/asset-finance-modeler"
source .venv/bin/activate
pytest -v 2>&1 | tail -10
ruff check src/ tests/
mypy src/
```

Expected:
- pytest: ≥175 tests passing
- ruff: All checks passed
- mypy: Success

Fix any failures inline.

- [ ] **Step 4: Final commit**

```bash
git add README.md docs/INTEGRATION.md
git commit -m "docs: README + INTEGRATION.md (bridge plan for Gestnova/Ian)"
# If sanity fixes were needed:
git add -u
git commit -m "chore: lint/type fixes after Plan 3 sanity" || true
```

---

## End of Plan 3 — End of asset-finance-modeler v1

After this plan, the modeler is **fully functional and ready to integrate**:

- 20 MCP tools exposed over stdio
- All Plan 1+2 functionality reachable via MCP
- Bridge plan documented for Gestnova/Ian

**Estimated effort:** 3-4 hours with subagent-driven execution. Subsequent work (none in this project; integration happens in `livekit-voice-platform`).
