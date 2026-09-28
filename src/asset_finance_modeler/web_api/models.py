"""Generic multi-asset web routes: /api/models (list + schema + run).

Exposes every infrastructure preset (and the SVJ hybrid deal) as a uniform
model with introspectable input leaves and a run endpoint that returns
annualized P&L, free-cash-flow and headline KPIs.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ValidationError

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
from asset_finance_modeler.assets.saas import presets as _saas_presets_pkg
from asset_finance_modeler.assets.saas.loader import load_preset as load_saas_preset
from asset_finance_modeler.assets.saas.model import ModelResults, SaasModel
from asset_finance_modeler.assets.saas.schema import SaasModelConfig
from asset_finance_modeler.core.protocols import FinancialOutput
from asset_finance_modeler.deals.svj import SvjInputError, run_svj, svj_input_spec
from asset_finance_modeler.web_api.auth import require_token
from asset_finance_modeler.web_api.introspect import (
    InvalidPathError,
    schema_tree,
    set_by_path,
)

_FREQ_PPY = {"M": 12, "Q": 4, "Y": 1}

_BUSINESS_IDS: set[str] = set(business_preset_ids())

from asset_finance_modeler.assets.inmobiliario.cargador import cargar_inmueble, ids_inmobiliario  # noqa: E402
from asset_finance_modeler.assets.inmobiliario.modelo import InmuebleConfig, ejecutar as _ejecutar_inmueble  # noqa: E402

# Inmobiliario profesional (compra, hipoteca, alquiler, fiscalidad, venta).
_INMUEBLE_IDS: set[str] = set(ids_inmobiliario())


def _run_inmueble_config(cfg_dict: dict[str, Any]) -> dict[str, Any]:
    return _ejecutar_inmueble(_validate(InmuebleConfig, cfg_dict))

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


def _saas_preset_ids() -> list[str]:
    """SaaS preset ids, namespaced ``saas_<stem>`` so they never collide with
    infra/business ids and the asset_type is unambiguous."""
    presets_dir = Path(_saas_presets_pkg.__file__).resolve().parent
    return sorted("saas_" + q.stem for q in presets_dir.glob("*.yaml"))


_SAAS_IDS: set[str] = set(_saas_preset_ids())


def _annual(series: list[float], ppy: int) -> list[float]:
    return [sum(series[y * ppy : (y + 1) * ppy]) for y in range(len(series) // ppy)]


def _ppy_of(cfg_dict: dict[str, Any]) -> int:
    freq = (cfg_dict.get("meta", {}).get("horizon", {}) or {}).get("frequency", "M")
    return _FREQ_PPY.get(freq, 12)


def _validate(model_cls: type[BaseModel], cfg_dict: dict[str, Any]) -> Any:
    """Validate a config dict against its Pydantic model, turning a
    ValidationError (e.g. an out-of-range override) into a clear HTTP 400
    instead of a 500 (FIX 2). Applied to every model-run path so no override
    can 500."""
    try:
        return model_cls.model_validate(cfg_dict)
    except ValidationError as exc:
        errs = exc.errors()
        if errs:
            e = errs[0]
            loc = ".".join(str(p) for p in e.get("loc", ()))
            msg = e.get("msg", "invalid value")
            detail = f"invalid override value: {loc}: {msg}" if loc else f"invalid override value: {msg}"
        else:  # pragma: no cover — defensive
            detail = "invalid override value"
        raise HTTPException(status_code=400, detail=detail) from exc


def _run_config(cfg_dict: dict[str, Any]) -> dict[str, Any]:
    """Validate, run, and shape an infrastructure config dict into a JSON-
    serializable payload with annualized statements + KPIs."""
    cfg = _validate(InfrastructureModelConfig, cfg_dict)
    out = InfrastructureModel(cfg).run()
    ppy = _ppy_of(cfg_dict)
    payload = _run_financial_output(out, ppy)
    # Ingresos por contrato (PPA, mercado…) y gastos de explotación, por año.
    streams = ((getattr(out, "revenue_breakdown", None) or {}).get("streams") or {})
    ingresos = {str(k): [round(x) for x in _annual(list(v), ppy)] for k, v in streams.items() if isinstance(v, list)}
    gastos = {"Gastos de explotación": [round(x) for x in _annual(list(out.pnl.get("opex", [])), ppy)]} if "opex" in out.pnl else {}
    if ingresos or gastos:
        payload["lineas"] = {"ingresos": ingresos, "gastos": gastos}
    return payload


def _run_financial_output(out: FinancialOutput, ppy: int) -> dict[str, Any]:
    """Shape any ``FinancialOutput`` into the JSON payload (annualized
    statements + headline KPIs). Shared by infra and business models."""
    pnl = out.pnl
    income_rows = {
        k: [round(x) for x in _annual(pnl[k], ppy)]
        for k in ("revenue", "cogs", "gross_profit", "opex", "ebitda", "depreciation", "ebit", "interest_expense", "ebt", "tax", "net_income")
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
    if getattr(kp, "npv_equity", 0):
        kpis["npv_equity"] = round(kp.npv_equity)
    # Lo que el motor ya calculaba y no se enseñaba (28-sep).
    if getattr(kp, "payback_years", None) is not None:
        kpis["payback_years"] = round(kp.payback_years, 1)
    if getattr(kp, "dscr_avg", None):
        kpis["dscr_avg"] = round(kp.dscr_avg, 2)
    if getattr(kp, "lcoe", None):
        kpis["lcoe"] = round(kp.lcoe, 2)
    val = out.valuation or {}
    if val.get("enterprise_value") is not None:
        kpis["enterprise_value"] = round(val["enterprise_value"])

    def _fin_de_anio(serie: list[float]) -> list[float]:
        return [round(serie[min((y + 1) * ppy, len(serie)) - 1]) for y in range(n_years)] if serie else []

    summary = dict(out.summary)
    payload: dict[str, Any] = {
        "kpis": kpis,
        "income_statement": income_statement,
        "cash_flow": cash_flow,
        "summary": summary,
    }
    # Caja a final de cada año: la del modelo, o la suma de los flujos.
    if "cash" in cf:
        cash_flow["cash"] = _fin_de_anio(list(cf["cash"]))
    elif all(k in cash_flow for k in ("cfo", "cfi", "cff")):
        acc, caja = 0.0, []
        for y in range(n_years):
            acc += cash_flow["cfo"][y] + cash_flow["cfi"][y] + cash_flow["cff"][y]
            caja.append(round(acc))
        cash_flow["cash"] = caja
    # Balance a final de cada año.
    bal = out.balance or {}
    if bal:
        payload["balance"] = {"years": list(range(1, n_years + 1)), **{k: _fin_de_anio(list(v)) for k, v in bal.items() if isinstance(v, list)}}
    # El calendario de la deuda año a año.
    dm = out.debt_metrics or {}
    deuda_anual = summary.pop("deuda_anual", None)
    if "balance" in dm and any(dm["balance"]):
        dscr_p = list(getattr(kp, "dscr_series", []) or [])
        dscr_y: list[float | None] = []
        for y in range(n_years):
            vals = [v for v in dscr_p[y * ppy:(y + 1) * ppy] if v and v > 0 and math.isfinite(v)]
            dscr_y.append(round(sum(vals) / len(vals), 2) if vals else None)
        payload["deuda"] = {
            "years": list(range(1, n_years + 1)),
            "saldo": _fin_de_anio(list(dm["balance"])),
            "intereses": [round(x) for x in _annual(list(dm.get("interest", [])), ppy)],
            "amortizacion": [round(x) for x in _annual(list(dm.get("principal", [])), ppy)],
            "disposiciones": [round(x) for x in _annual(list(dm.get("drawdowns", [])), ppy)],
            "dscr": dscr_y,
        }
    elif isinstance(deuda_anual, dict):
        payload["deuda"] = {
            "years": list(range(1, n_years + 1)),
            **{k: [(round(x, 2) if x is not None and math.isfinite(x) else None) if k == "dscr" else round(x) for x in (v or [])][:n_years] for k, v in deuda_anual.items()},
        }
    # La valoración del modelo (DCF del proyecto).
    if val:
        payload["valoracion"] = {k: round(v) for k, v in val.items() if isinstance(v, (int, float))}
    # Ensure JSON-serializable (Decimals/dates -> str).
    result: dict[str, Any] = json.loads(json.dumps(payload, default=str))
    return result


def _run_business_config(cfg_dict: dict[str, Any]) -> dict[str, Any]:
    """Validate, run, and shape a business config dict (same payload shape)."""
    cfg = _validate(BusinessModelConfig, cfg_dict)
    out = BusinessModel(cfg).run()
    payload = _run_financial_output(out, _ppy_of(cfg_dict))
    # Cada ingreso y gasto por separado (para anotar y comparar lo real).
    from asset_finance_modeler.assets.business.engines import line_series

    years = len(payload["income_statement"]["years"])
    lineas = line_series(cfg.model_dump(), years)
    payload["lineas"] = {g: {k: [round(x) for x in v] for k, v in d.items()} for g, d in lineas.items()}
    return payload


def _run_saas_config(cfg_dict: dict[str, Any]) -> dict[str, Any]:
    """Validate, run, and shape a SaaS config dict into the generic payload
    (P3-6). ``SaasModel.run`` returns ``ModelResults`` (not ``FinancialOutput``),
    so we adapt its pnl/cashflow/valuation into the same
    kpis+income_statement+cash_flow shape every other model exposes.

    SaaS is a P&L/valuation model with no project IRR or DSCR, so those KPIs are
    ``None`` (rendered "n/a"); the enterprise value is surfaced as ``npv`` so the
    portfolio aggregation (which keys off ``npv``) works uniformly.
    """
    cfg = _validate(SaasModelConfig, cfg_dict)
    out: ModelResults = SaasModel(cfg).run()
    ppy = _ppy_of(cfg_dict)

    pnl = out.pnl
    income_rows = {
        k: [round(x) for x in _annual(pnl[k], ppy)]
        for k in ("revenue", "ebitda", "ebit", "interest_expense", "ebt", "tax", "net_income")
        if k in pnl
    }
    n_years = len(next(iter(income_rows.values()))) if income_rows else 0
    income_statement = {"years": list(range(1, n_years + 1)), "rows": income_rows}

    cash_flow: dict[str, Any] = {"years": list(range(1, n_years + 1))}
    for k in ("cfo", "cfi", "cff"):
        if k in out.cashflow:
            cash_flow[k] = [round(x) for x in _annual(out.cashflow[k], ppy)]

    ev = out.valuation.get("enterprise_value", 0.0)
    kpis = {
        "npv": round(ev),
        "irr_project": None,
        "irr_equity": None,
        "dscr_min": None,
        "total_capex": round(float(out.summary.get("total_capex", 0)) or 0),
    }

    payload = {
        "kpis": kpis,
        "income_statement": income_statement,
        "cash_flow": cash_flow,
        "summary": dict(out.summary),
    }
    result: dict[str, Any] = json.loads(json.dumps(payload, default=str))
    return result


def _apply_overrides(cfg: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Apply override-by-path values, converting an invalid path into a 400
    (with the offending path) instead of a 500 (P3-3)."""
    for path, value in (overrides or {}).items():
        try:
            cfg = set_by_path(cfg, path, _coerce(cfg, path, value))
        except InvalidPathError as exc:
            sugeridas = _rutas_parecidas(cfg, str(exc.path))
            raise HTTPException(
                status_code=400,
                detail=f"invalid override path: {exc.path}"
                + (f". Rutas parecidas que si existen: {', '.join(sugeridas)}" if sugeridas else ""),
            ) from exc
    return cfg


def _rutas_parecidas(cfg: dict[str, Any], mala: str, n: int = 6) -> list[str]:
    """Las rutas del modelo que mas se parecen a una que no existe (27-sep: un
    agente puso "losses.degradation" seis veces; la buena era "degradation")."""
    import re as _re

    rutas: list[str] = []

    def recorrer(x: Any, pre: str, prof: int) -> None:
        if prof > 5:
            return
        if isinstance(x, dict):
            for k, v in x.items():
                r = f"{pre}.{k}" if pre else str(k)
                rutas.append(r)
                recorrer(v, r, prof + 1)
        elif isinstance(x, list) and x:
            recorrer(x[0], f"{pre}[0]", prof + 1)

    recorrer(cfg, "", 0)
    trozos = [t for t in _re.split(r"[.\[\]_]+", mala.lower()) if t and not t.isdigit()]
    if not trozos:
        return []
    ultimo = _re.split(r"[.\[\]]+", mala.lower().strip("."))[-1]

    def nota(r: str) -> float:
        rl = r.lower()
        partes = _re.split(r"[.\[\]_]+", rl)
        puntos = sum(1 for t in trozos if t in rl)
        puntos += 2 if rl.split(".")[-1] == ultimo else 0
        puntos += 1 if any(p.startswith(ultimo[:5]) for p in partes) else 0
        return puntos - len(r) / 1000

    buenas = sorted((r for r in rutas if nota(r) >= 1), key=nota, reverse=True)
    return buenas[:n]


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
    for iid in sorted(_INMUEBLE_IDS):
        models.append({"id": iid, "name": "Inmueble en alquiler (compra, hipoteca, fiscalidad y venta)", "asset_type": "real_estate"})
    for sid in _saas_preset_ids():
        models.append(
            {
                "id": sid,
                "name": sid.replace("_", " ").title(),
                "asset_type": "saas",
            }
        )
    return {"models": models}


@router.get("/{model_id}/schema")
def model_schema(model_id: str) -> dict[str, Any]:
    if model_id == "svj_hybrid":
        return {"inputs": svj_input_spec()}

    if model_id in _INMUEBLE_IDS:
        return {"inputs": schema_tree(cargar_inmueble(model_id).model_dump())}

    if model_id in _BUSINESS_IDS:
        cfg = load_business_preset(model_id).model_dump()
        return {"inputs": schema_tree(cfg)}

    if model_id in _SAAS_IDS:
        cfg = load_saas_preset(model_id[len("saas_") :]).model_dump()
        return {"inputs": schema_tree(cfg, asset_type="saas")}

    if model_id not in _preset_ids():
        raise HTTPException(status_code=404, detail=f"unknown model: {model_id}")
    cfg = load_preset(model_id).model_dump()
    return {"inputs": schema_tree(cfg)}


@router.post("/{model_id}/run")
def model_run(model_id: str, body: RunBody) -> dict[str, Any]:
    overrides = body.overrides or {}
    if model_id == "svj_hybrid":
        try:
            return run_svj(overrides)
        except SvjInputError as exc:  # A1: bad override -> 400, not 500
            raise HTTPException(status_code=400, detail=exc.message) from exc

    if model_id in _INMUEBLE_IDS:
        return _run_inmueble_config(_apply_overrides(cargar_inmueble(model_id).model_dump(), overrides))

    if model_id in _BUSINESS_IDS:
        cfg = load_business_preset(model_id).model_dump()
        cfg = _apply_overrides(cfg, overrides)
        return _run_business_config(cfg)

    if model_id in _SAAS_IDS:
        cfg = load_saas_preset(model_id[len("saas_") :]).model_dump()
        cfg = _apply_overrides(cfg, overrides)
        return _run_saas_config(cfg)

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
