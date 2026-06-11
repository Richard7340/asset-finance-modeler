"""Generic asset persistence: /api/assets (save/list/review/delete).

Persists a configured asset (model + overrides + run results) on top of the
engine's ScenarioStore, so a user can build a portfolio, review each asset as
it was run, and delete it. Reuses the run plumbing from web_api.models and the
SVJ hybrid deal.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from asset_finance_modeler.core.scenario import Scenario, new_scenario_id
from asset_finance_modeler.deals.svj import run_svj
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore
from asset_finance_modeler.web_api.auth import require_token
from asset_finance_modeler.web_api.introspect import set_by_path
from asset_finance_modeler.web_api.models import _coerce, _preset_ids, _run_config

from asset_finance_modeler.assets.infrastructure.loader import load_preset  # isort: skip


def _db_path() -> str:
    """Resolve the SQLite DB path. ASSET_FINANCE_DB_PATH may be a directory (the
    web layer convention — mirrors http_server's per-process dir) or a file. If
    it points to a dir (or is empty), join 'scenarios.db' under it."""
    raw = os.getenv("ASSET_FINANCE_DB_PATH", "").strip()
    base = Path(raw) if raw else Path.home() / ".asset-finance-modeler"
    # Treat as a directory if it has no .db suffix (the web convention passes a dir).
    if base.suffix == ".db":
        db_path = base
    else:
        db_path = base / "scenarios.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return str(db_path)


def _store() -> SQLiteScenarioStore:
    store = SQLiteScenarioStore(_db_path())
    store.initialize()
    return store


def _run_model(model_id: str, overrides: dict[str, Any]) -> dict[str, Any]:
    """Run a model and return its JSON-serializable result payload (with a
    top-level 'kpis' key). Mirrors web_api.models.model_run dispatch."""
    if model_id == "svj_hybrid":
        return run_svj(overrides)
    if model_id not in _preset_ids():
        raise HTTPException(status_code=404, detail=f"unknown model: {model_id}")
    cfg = load_preset(model_id).model_dump()
    for path, value in (overrides or {}).items():
        cfg = set_by_path(cfg, path, _coerce(cfg, path, value))
    return _run_config(cfg)


router = APIRouter(prefix="/api/assets", dependencies=[Depends(require_token)])


class SaveAssetBody(BaseModel):
    model_id: str
    name: str
    overrides: dict[str, Any] = {}
    tags: list[str] = []


@router.post("")
def save_asset(body: SaveAssetBody) -> dict[str, Any]:
    overrides = body.overrides or {}
    results = _run_model(body.model_id, overrides)
    scenario = Scenario(
        id=new_scenario_id(),
        name=body.name,
        base_model=body.model_id,
        overrides=overrides,
        inputs_snapshot={"model_id": body.model_id, "overrides": overrides},
        results_snapshot=results,
        tags=body.tags or [],
    )
    _store().save(scenario)
    return {"id": scenario.id}


@router.get("")
def list_assets() -> dict[str, Any]:
    scenarios = _store().list()
    return {
        "assets": [
            {
                "id": s.id,
                "name": s.name,
                "model_id": s.base_model,
                "created_at": s.created_at.isoformat(),
                "kpis": s.results_snapshot.get("kpis", {}),
            }
            for s in scenarios
        ]
    }


@router.get("/{asset_id}")
def get_asset(asset_id: str) -> dict[str, Any]:
    s = _store().get(asset_id)
    if s is None or s.is_deleted:
        raise HTTPException(status_code=404, detail=f"unknown asset: {asset_id}")
    return {
        "id": s.id,
        "name": s.name,
        "model_id": s.base_model,
        "overrides": s.inputs_snapshot.get("overrides", s.overrides),
        "results_snapshot": s.results_snapshot,
        "created_at": s.created_at.isoformat(),
    }


@router.delete("/{asset_id}")
def delete_asset(asset_id: str) -> dict[str, Any]:
    _store().delete(asset_id)
    return {"ok": True}
