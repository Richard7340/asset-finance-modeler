# asset-finance-modeler

Comprehensive financial modeling engine for SaaS and other assets, exposed as MCP tools.

V1 covers SaaS (Gestnova baseline shipped); Plan 4 adds an intelligence layer (knowledge base, workflows, contextual memory). Designed to scale to renewables, real estate, generic business.

## Architecture

- `core/` — asset-agnostic primitives (TimeGrid, GrowthCurve, AmortizationSchedule, statements, valuation, scenario)
- `assets/saas/` — SaaS schema + engines + orchestrator (`SaasModel`) + presets
- `store/` — SQLite scenarios + exports + compare + sensitivity
- `cli/` — argparse CLI
- `mcp_server/` — MCP stdio server exposing **30 tools** total:
  - 18 `finance.simulate.*` tools (run, clone, compare, sensitivity, export…)
  - 3 `finance.track.*` stubs (V2)
  - 3 `finance.knowledge.*` tools — FAISS-backed semantic search over 30+ financial concepts
  - 3 `finance.workflows.*` tools — declarative multi-step analysis recipes (pricing_impact, valuation_summary…)
  - 3 `finance.context.*` tools — per-tenant persistent memory, semantically searchable
- `intelligence/` — embeddings (sentence-transformers MiniLM), KnowledgeBase, WorkflowEngine, ContextMemory

## Quickstart (dev)

```
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                                  # ≥193 tests
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

## Intelligence layer (Plan 4)

The modeler now ships a structured intelligence layer — **no extra LLM in the chain**; all intelligence is retrieval + workflow execution.

```python
# Knowledge base: semantic search over financial concepts (30 seeded entries, bilingual ES/EN)
reg["finance.knowledge.search"].handler({"query": "qué es LTV/CAC saludable", "top_k": 3})

# Workflows: run a multi-step analysis with one call
reg["finance.workflows.run"].handler({
    "workflow_id": "pricing_impact_analysis",
    "inputs": {"base_scenario_id": "scn-xxx", "prices": [200, 300, 400]},
})

# Context memory: store and recall per-tenant decisions
reg["finance.context.store"].handler({"tenant_id": "gestnova", "key": "pricing-2026-05",
    "value": "Decided to keep pricing at 300€/agent after EV analysis"})
reg["finance.context.search"].handler({"tenant_id": "gestnova", "query": "pricing decision"})
```

## Specs and plans

- `docs/superpowers/specs/2026-05-14-asset-finance-modeler-design.md` — design
- `docs/superpowers/plans/2026-05-14-plan-1-foundation-engine.md` — done
- `docs/superpowers/plans/2026-05-14-plan-2-scenarios-store-exports-cli.md` — done
- `docs/superpowers/plans/2026-05-14-plan-3-mcp-server.md` — done
- `docs/superpowers/plans/2026-05-15-plan-4-intelligent-toolkit.md` — done

## Qué incluye y qué no

Este repositorio es el **motor**: los modelos, el servidor MCP con sus herramientas y una colección
de presets de referencia (BESS, solar, eólica, datacenter, negocio, alquiler y la vía híbrida
consolidada).

Los presets traen **cifras redondas de ejemplo**, no de ningún proyecto real. Sirven para que el
motor se ejecute de punta a punta nada más instalarlo, y para que los tests comprueben siempre lo
mismo. Para un caso de verdad se pasan los parámetros propios.

## Licencia

MIT. Úsalo, modifícalo y véndelo si te sirve. Hecho en [Gestnova](https://gestnova.eu).
