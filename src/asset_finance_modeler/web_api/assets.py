"""Generic asset persistence: /api/assets (save/list/review/delete).

Persists a configured asset (model + overrides + run results) on top of the
engine's ScenarioStore, so a user can build a portfolio, review each asset as
it was run, and delete it. Reuses the run plumbing from web_api.models and the
SVJ hybrid deal.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from asset_finance_modeler.assets.business.loader import load_business_preset
from asset_finance_modeler.core.scenario import Scenario, new_scenario_id
from asset_finance_modeler.deals.svj import run_svj
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore
from asset_finance_modeler.web_api.auth import require_token
from asset_finance_modeler.web_api.introspect import set_by_path
from asset_finance_modeler.web_api.models import (
    _BUSINESS_IDS,
    _coerce,
    _preset_ids,
    _run_business_config,
    _run_config,
)

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
    if model_id in _BUSINESS_IDS:
        cfg = load_business_preset(model_id).model_dump()
        for path, value in (overrides or {}).items():
            cfg = set_by_path(cfg, path, _coerce(cfg, path, value))
        return _run_business_config(cfg)
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
def list_assets(lifecycle: str | None = None) -> dict[str, Any]:
    scenarios = _store().list(lifecycle=lifecycle)
    return {
        "assets": [
            {
                "id": s.id,
                "name": s.name,
                "model_id": s.base_model,
                "created_at": s.created_at.isoformat(),
                "kpis": s.results_snapshot.get("kpis", {}),
                "lifecycle": s.lifecycle,
                "commissioning_date": (
                    s.commissioning_date.isoformat() if s.commissioning_date else None
                ),
                "tracking_frequency": s.tracking_frequency,
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


class LifecycleBody(BaseModel):
    lifecycle: Literal["opportunity", "operational"]
    tracking_frequency: Literal["daily", "monthly", "quarterly"] | None = None
    commissioning_date: str | None = None  # ISO; si falta al promover, se usa ahora


@router.patch("/{asset_id}/lifecycle")
def set_lifecycle(asset_id: str, body: LifecycleBody) -> dict[str, Any]:
    store = _store()
    s = store.get(asset_id)
    if s is None or s.is_deleted:
        raise HTTPException(status_code=404, detail=f"unknown asset: {asset_id}")
    if body.lifecycle == "operational":
        s.lifecycle = "operational"
        s.base_locked = True
        s.is_canonical = True
        s.tracking_frequency = body.tracking_frequency or s.tracking_frequency or "monthly"
        if body.commissioning_date:
            s.commissioning_date = datetime.fromisoformat(body.commissioning_date)
        elif s.commissioning_date is None:
            s.commissioning_date = datetime.now(UTC)
    else:  # demote -> opportunity
        s.lifecycle = "opportunity"
        s.base_locked = False
        s.is_canonical = False
        s.commissioning_date = None
        s.tracking_frequency = None
    store.save(s)
    return {
        "id": s.id,
        "lifecycle": s.lifecycle,
        "base_locked": s.base_locked,
        "commissioning_date": (
            s.commissioning_date.isoformat() if s.commissioning_date else None
        ),
        "tracking_frequency": s.tracking_frequency,
    }


portfolio_router = APIRouter(prefix="/api/portfolio", dependencies=[Depends(require_token)])


def _normalize_run(result: dict[str, Any]) -> dict[str, float]:
    """Normalize the two run-result shapes (generic vs svj_hybrid) to a flat
    set of portfolio metrics."""
    kpis = result.get("kpis", {}) or {}
    npv = kpis.get("npv", kpis.get("npv_hybrid", 0)) or 0
    capex = kpis.get("total_capex", 0) or 0
    irr = kpis.get("irr", kpis.get("irr_project", 0)) or 0
    revenue_y1: float = 0
    income = result.get("income_statement") or {}
    rows = income.get("rows") or {}
    revenue = rows.get("revenue") or []
    if revenue:
        revenue_y1 = revenue[0] or 0
    else:
        revenue_y1 = kpis.get("revenue_y1", 0) or 0
    yield_pct = round(float(npv) / float(capex), 4) if capex else 0.0
    return {
        "npv": float(npv),
        "capex": float(capex),
        "revenue_y1": float(revenue_y1),
        "irr": float(irr),
        "yield_pct": float(yield_pct),
    }


@portfolio_router.get("")
def portfolio(ids: str | None = None, lifecycle: str | None = None) -> dict[str, Any]:
    """Aggregate saved (non-deleted) assets by re-running each one fresh, so
    valuations reflect current inputs. Optional ?ids=id1,id2 limits the set.
    Assets that fail to run are reported in `skipped` (not silently dropped,
    not fatal) so a broken asset stays visible (FIX 4)."""
    wanted: set[str] | None = None
    if ids:
        wanted = {i.strip() for i in ids.split(",") if i.strip()}

    assets: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    totals = {"npv": 0.0, "capex": 0.0, "revenue_y1": 0.0, "count": 0, "irr_weighted": 0.0}
    _irr_capex_sum = 0.0
    for s in _store().list(lifecycle=lifecycle):
        if wanted is not None and s.id not in wanted:
            continue
        snapshot = s.inputs_snapshot or {}
        model_id = snapshot.get("model_id", s.base_model)
        overrides = snapshot.get("overrides", s.overrides) or {}
        try:
            result = _run_model(model_id, overrides)
            metrics = _normalize_run(result)
        except Exception as exc:  # noqa: BLE001 — surface failures, don't 500
            skipped.append(
                {"id": s.id, "name": s.name, "model_id": model_id, "error": str(exc)}
            )
            continue
        assets.append(
            {
                "id": s.id,
                "name": s.name,
                "model_id": model_id,
                "npv": metrics["npv"],
                "irr": metrics["irr"],
                "revenue_y1": metrics["revenue_y1"],
                "capex": metrics["capex"],
                "yield_pct": metrics["yield_pct"],
            }
        )
        totals["npv"] += metrics["npv"]
        totals["capex"] += metrics["capex"]
        totals["revenue_y1"] += metrics["revenue_y1"]
        totals["count"] += 1
        _irr_capex_sum += metrics["irr"] * metrics["capex"]

    if totals["capex"]:
        totals["irr_weighted"] = round(_irr_capex_sum / totals["capex"], 4)

    return {"assets": assets, "totals": totals, "skipped": skipped}
