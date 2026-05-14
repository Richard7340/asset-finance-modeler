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
