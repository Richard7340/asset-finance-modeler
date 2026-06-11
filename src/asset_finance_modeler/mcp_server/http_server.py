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
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from asset_finance_modeler.web_api.assets import router as assets_router
from asset_finance_modeler.web_api.models import router as models_router
from asset_finance_modeler.web_api.routes import router as svj_router

from .server import _build_app


class CallRequest(BaseModel):
    name: str
    arguments: dict[str, Any] = {}


app = FastAPI(title="asset-finance-modeler HTTP")
# SIM_ONLY=1 skips building the full 30+ MCP tool registry (incl. the heavy
# embeddings/FAISS intelligence stack). The web simulator only needs /api/svj/*
# + the static SPA, so this gives an instant, reliable startup for the dashboard.
if os.getenv("SIM_ONLY") == "1":
    _registry = {}
else:
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


# /api/svj/* router (model/run/export) with token auth. Mounted before the SPA
# so /api routes win over the catch-all static mount.
app.include_router(svj_router)
# Generic multi-asset router /api/models (list + schema + run). After svj,
# before the static mount so /api routes win over the catch-all.
app.include_router(models_router)
# Generic asset persistence router /api/assets (save/list/review/delete).
app.include_router(assets_router)

# Static SPA mount (AFTER include_router so /api wins). The built SPA lives at
# `web/dist`. Prefer SIM_WEB_DIST (set in the Docker image where the package is
# installed to site-packages); fall back to the repo layout for local dev. The
# dir may not exist until the frontend is built, so guard with is_dir().
_env_dist = os.getenv("SIM_WEB_DIST")
web_dist = Path(_env_dist) if _env_dist else Path(__file__).resolve().parents[3] / "web" / "dist"
if web_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(web_dist), html=True), name="spa")


def main() -> None:
    port = int(os.getenv("PORT", "8015"))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
