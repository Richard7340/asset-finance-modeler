"""FastAPI HTTP wrapper exposing the modeler's 30 MCP tools over HTTP.

Mirrors the stdio MCP server but on port 8015 (default), so the Ian agent
in livekit-voice-platform can call modeler tools via a simple POST /call
endpoint without spawning a subprocess.

Run via:
    asset-finance-modeler-http              # via entry point
    PORT=8015 python -m asset_finance_modeler.mcp_server.http_server

Endpoints:
    GET  /health      → {"status": "ok"}
    GET  /tools       → [{name, description, input_schema}, …]
    POST /call        → {result of the tool}  (body: {name, arguments})

Environment:
    ASSET_FINANCE_DB_PATH   path for scenarios.db / knowledge.db / context.db
    PORT                    HTTP port (default 8015)
"""
from __future__ import annotations
import json
import os
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

from .server import _build_app


class CallRequest(BaseModel):
    name: str
    arguments: dict[str, Any] = {}


app = FastAPI(title="asset-finance-modeler HTTP")
_, _registry = _build_app()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "tools_loaded": str(len(_registry))}


@app.get("/tools")
async def list_tools() -> list[dict[str, Any]]:
    return [
        {"name": spec.name, "description": spec.description, "input_schema": spec.input_schema}
        for spec in _registry.values()
    ]


@app.post("/call")
async def call_tool(req: CallRequest) -> dict[str, Any]:
    if req.name not in _registry:
        raise HTTPException(status_code=404, detail=f"unknown tool: {req.name}")
    spec = _registry[req.name]
    try:
        result = spec.handler(req.arguments or {})
    except Exception as exc:  # noqa: BLE001
        # Surface the error as a structured payload (no 500). Caller checks for 'error' key.
        return {"error": str(exc), "tool": req.name}
    # MCP tool handlers can return any JSON-serializable type; default-stringify Decimals/dates
    return json.loads(json.dumps(result, default=str))


def main() -> None:
    port = int(os.getenv("PORT", "8015"))
    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
