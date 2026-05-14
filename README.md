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
