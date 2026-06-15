"""Generic multi-asset web routes: /api/models (list + schema + run).

Exposes every infrastructure preset (and the SVJ hybrid deal) as a uniform
model with introspectable input leaves and a run endpoint that returns
annualized P&L, free-cash-flow and headline KPIs.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from asset_finance_modeler.assets.business.loader import (
    business_preset_ids,
    load_business_preset,
)
from asset_finance_modeler.assets.business.model import BusinessModel
from asset_finance_modeler.assets.business.schema import BusinessModelConfig
from asset_finance_modeler.assets.infrastructure import presets as _presets_pkg
from asset_finance_modeler.assets.infrastructure.loader import load_preset
from asset_finance_modeler.assets.infrastructure.model import InfrastructureModel
from asset_finance_modeler.assets.infrastructure.schema import InfrastructureModelConfig
from asset_finance_modeler.core.protocols import FinancialOutput
from asset_finance_modeler.deals.svj import run_svj, svj_input_spec
from asset_finance_modeler.web_api.auth import require_token
from asset_finance_modeler.web_api.introspect import (
    InvalidPathError,
    schema_tree,
    set_by_path,
)

_FREQ_PPY = {"M": 12, "Q": 4, "Y": 1}

_BUSINESS_IDS: set[str] = set(business_preset_ids())

_BUSINESS_NAMES: dict[str, str] = {
    "business_generic": "Negocio genérico",
    "business_restaurant": "Restaurante",
    "business_industrial": "Planta industrial",
    "real_estate_rental": "Inmueble en alquiler",
}


def _preset_ids() -> list[str]:
    """Robustly derive preset ids from the presets package directory."""
    presets_dir = Path(_presets_pkg.__file__).resolve().parent
    return sorted(q.stem for q in presets_dir.glob("*.yaml"))


def _annual(series: list[float], ppy: int) -> list[float]:
    return [sum(series[y * ppy : (y + 1) * ppy]) for y in range(len(series) // ppy)]


def _ppy_of(cfg_dict: dict[str, Any]) -> int:
    freq = (cfg_dict.get("meta", {}).get("horizon", {}) or {}).get("frequency", "M")
    return _FREQ_PPY.get(freq, 12)


def _run_config(cfg_dict: dict[str, Any]) -> dict[str, Any]:
    """Validate, run, and shape an infrastructure config dict into a JSON-
    serializable payload with annualized statements + KPIs."""
    cfg = InfrastructureModelConfig.model_validate(cfg_dict)
    out = InfrastructureModel(cfg).run()
    return _run_financial_output(out, _ppy_of(cfg_dict))


def _run_financial_output(out: FinancialOutput, ppy: int) -> dict[str, Any]:
    """Shape any ``FinancialOutput`` into the JSON payload (annualized
    statements + headline KPIs). Shared by infra and business models."""
    pnl = out.pnl
    income_rows = {
        k: [round(x) for x in _annual(pnl[k], ppy)]
        for k in ("revenue", "ebitda", "ebit", "interest_expense", "ebt", "tax", "net_income")
        if k in pnl
    }
    n_years = len(next(iter(income_rows.values()))) if income_rows else 0
    income_statement = {"years": list(range(1, n_years + 1)), "rows": income_rows}

    cf = out.cashflow
    cash_flow: dict[str, Any] = {"years": list(range(1, n_years + 1))}
    for k in ("cfo", "cfi", "cff"):
        if k in cf:
            cash_flow[k] = [round(x) for x in _annual(cf[k], ppy)]

    kp = out.project_kpis

    def _round_irr(v: float | None) -> float | None:
        return round(v, 4) if v is not None else None  # None -> "n/a" (FIX 3)

    kpis = {
        "npv": round(getattr(kp, "npv", 0)),
        "irr_project": _round_irr(getattr(kp, "irr_project", 0)),
        "irr_equity": _round_irr(getattr(kp, "irr_equity", 0)),
        "dscr_min": round(getattr(kp, "dscr_min", 0), 2),
        "total_capex": round(out.summary.get("total_capex", 0)),
    }

    payload = {
        "kpis": kpis,
        "income_statement": income_statement,
        "cash_flow": cash_flow,
        "summary": dict(out.summary),
    }
    # Ensure JSON-serializable (Decimals/dates -> str).
    result: dict[str, Any] = json.loads(json.dumps(payload, default=str))
    return result


def _run_business_config(cfg_dict: dict[str, Any]) -> dict[str, Any]:
    """Validate, run, and shape a business config dict (same payload shape)."""
    cfg = BusinessModelConfig.model_validate(cfg_dict)
    out = BusinessModel(cfg).run()
    return _run_financial_output(out, _ppy_of(cfg_dict))


def _apply_overrides(cfg: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Apply override-by-path values, converting an invalid path into a 400
    (with the offending path) instead of a 500 (P3-3)."""
    for path, value in (overrides or {}).items():
        try:
            cfg = set_by_path(cfg, path, _coerce(cfg, path, value))
        except InvalidPathError as exc:
            raise HTTPException(
                status_code=400, detail=f"invalid override path: {exc.path}"
            ) from exc
    return cfg


router = APIRouter(prefix="/api/models", dependencies=[Depends(require_token)])


class RunBody(BaseModel):
    overrides: dict[str, Any] = {}


@router.get("")
def list_models() -> dict[str, Any]:
    models = [
        {
            "id": pid,
            "name": pid.replace("_", " ").title(),
            "asset_type": pid.split("_")[0],
        }
        for pid in _preset_ids()
    ]
    models.append(
        {
            "id": "svj_hybrid",
            "name": "SVJ 1&2 — FV + BESS (Hibrido)",
            "asset_type": "hybrid",
        }
    )
    for bid in business_preset_ids():
        models.append(
            {
                "id": bid,
                "name": _BUSINESS_NAMES.get(bid, bid.replace("_", " ").title()),
                "asset_type": "real_estate" if bid.startswith("real_estate") else "business",
            }
        )
    return {"models": models}


@router.get("/{model_id}/schema")
def model_schema(model_id: str) -> dict[str, Any]:
    if model_id == "svj_hybrid":
        return {"inputs": svj_input_spec()}

    if model_id in _BUSINESS_IDS:
        cfg = load_business_preset(model_id).model_dump()
        return {"inputs": schema_tree(cfg)}

    if model_id not in _preset_ids():
        raise HTTPException(status_code=404, detail=f"unknown model: {model_id}")
    cfg = load_preset(model_id).model_dump()
    return {"inputs": schema_tree(cfg)}


@router.post("/{model_id}/run")
def model_run(model_id: str, body: RunBody) -> dict[str, Any]:
    overrides = body.overrides or {}
    if model_id == "svj_hybrid":
        return run_svj(overrides)

    if model_id in _BUSINESS_IDS:
        cfg = load_business_preset(model_id).model_dump()
        cfg = _apply_overrides(cfg, overrides)
        return _run_business_config(cfg)

    if model_id not in _preset_ids():
        raise HTTPException(status_code=404, detail=f"unknown model: {model_id}")

    cfg = load_preset(model_id).model_dump()
    cfg = _apply_overrides(cfg, overrides)
    return _run_config(cfg)


def _coerce(cfg: dict[str, Any], path: str, value: Any) -> Any:
    """Coerce an override value to the type of the existing value at `path`
    (keeps numbers numeric) when straightforward; otherwise pass through."""
    try:
        leaves = {leaf["path"]: leaf["value"] for leaf in schema_tree(cfg)}
        current = leaves.get(path)
        if isinstance(current, bool) or current is None:
            return value
        if isinstance(current, int) and not isinstance(value, bool):
            return int(value)
        if isinstance(current, float):
            return float(value)
    except (TypeError, ValueError):
        return value
    return value
