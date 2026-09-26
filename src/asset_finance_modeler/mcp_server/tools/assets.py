"""Los ACTIVOS del Portfolio, como herramientas (26-sep).

El agente (o la IA del usuario por el conector) guarda, lista, actualiza y
promueve activos de CUALQUIER tipo (renovables, inmobiliario, empresas, SaaS,
hibridos): los mismos que ve el Portfolio. Reutiliza la API REST del Portfolio
(web_api.assets) con el espacio de la llamada (lo fija /call con el tenant_id).
Antes lo que se modelaba por chat no aparecia en el Portfolio.
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from asset_finance_modeler.store.scenarios import espacio_actual


def _tenant(args: dict[str, Any]):
    from asset_finance_modeler.web_api.auth import TenantContext

    ws = espacio_actual() or args.get("workspace_id")
    if not ws:
        raise ValueError("workspace-required: falta el espacio (tenant_id)")
    return TenantContext(workspace_id=str(ws), user_id=str(args.get("user_id") or "default"))


def _seguro(fn):
    """Los errores de la API (404, 400) como {error}, nunca una excepcion."""
    def envuelto(args: dict[str, Any]) -> dict[str, Any]:
        try:
            return fn(args or {})
        except HTTPException as exc:
            return {"error": "invalid_input" if exc.status_code == 400 else "not_found", "detail": exc.detail}
        except ValueError as exc:
            return {"error": str(exc)}
    return envuelto


@_seguro
def handle_models(_args: dict[str, Any]) -> dict[str, Any]:
    from asset_finance_modeler.web_api.models import list_models

    return list_models()


@_seguro
def handle_schema(args: dict[str, Any]) -> dict[str, Any]:
    from asset_finance_modeler.web_api.models import model_schema

    return model_schema(str(args["model_id"]))


@_seguro
def handle_save(args: dict[str, Any]) -> dict[str, Any]:
    from asset_finance_modeler.web_api.assets import SaveAssetBody, get_asset, save_asset

    t = _tenant(args)
    body = SaveAssetBody(
        model_id=str(args["model_id"]), name=str(args["name"]), overrides=args.get("overrides") or {},
        tags=args.get("tags") or [], location=args.get("location"), lat=args.get("lat"), lon=args.get("lon"),
    )
    r = save_asset(body, t)
    a = get_asset(r["id"], t)
    return {"id": r["id"], "name": a["name"], "model_id": a["model_id"], "kpis": (a.get("results_snapshot") or {}).get("kpis", {})}


@_seguro
def handle_list(args: dict[str, Any]) -> dict[str, Any]:
    from asset_finance_modeler.web_api.assets import list_assets

    return list_assets(args.get("lifecycle"), _tenant(args))


@_seguro
def handle_get(args: dict[str, Any]) -> dict[str, Any]:
    from asset_finance_modeler.web_api.assets import get_asset

    a = get_asset(str(args["asset_id"]), _tenant(args))
    rs = a.get("results_snapshot") or {}
    # Lo esencial: sus datos, KPIs y las series anuales (no el volcado entero).
    return {
        "id": a["id"], "name": a["name"], "model_id": a["model_id"], "overrides": a.get("overrides", {}),
        "kpis": rs.get("kpis", {}), "income_statement": rs.get("income_statement"), "cash_flow": rs.get("cash_flow"),
        "location": a.get("location"),
    }


@_seguro
def handle_update(args: dict[str, Any]) -> dict[str, Any]:
    """Cambia hipotesis (se suman a las que tenia) o el nombre, y lo recalcula.
    Un activo en OPERACION tiene su base bloqueada: se compara con la realidad,
    no se reescribe (para cambiarla hay que devolverlo a oportunidad)."""
    from asset_finance_modeler.store.scenarios import SQLiteScenarioStore  # noqa: F401 (tipo)
    from asset_finance_modeler.web_api.assets import _run_model, _store

    t = _tenant(args)
    store = _store()
    s = store.get(str(args["asset_id"]), workspace_id=t.workspace_id)
    if s is None or s.is_deleted:
        return {"error": "not_found"}
    if s.base_locked and args.get("overrides"):
        return {"error": "base_locked", "detail": "Activo en operacion: su base no se cambia (se compara con los reales). Para cambiarla, finance.asset.set_lifecycle a opportunity."}
    snap = dict(s.inputs_snapshot or {})
    overrides = {**(snap.get("overrides") or s.overrides or {}), **(args.get("overrides") or {})}
    for k in list(args.get("quitar") or []):
        overrides.pop(k, None)
    results = _run_model(s.base_model, overrides)
    s.overrides = overrides
    snap["overrides"] = overrides
    for k in ("location", "lat", "lon"):
        if k in args:
            snap[k] = args[k]
    s.inputs_snapshot = snap
    s.results_snapshot = results
    if args.get("name"):
        s.name = str(args["name"])
    store.save(s)
    return {"id": s.id, "name": s.name, "kpis": results.get("kpis", {})}


@_seguro
def handle_lifecycle(args: dict[str, Any]) -> dict[str, Any]:
    from asset_finance_modeler.web_api.assets import LifecycleBody, set_lifecycle

    body = LifecycleBody(
        lifecycle=args["lifecycle"], tracking_frequency=args.get("tracking_frequency"),
        commissioning_date=args.get("commissioning_date"),
    )
    return set_lifecycle(str(args["asset_id"]), body, _tenant(args))


@_seguro
def handle_delete(args: dict[str, Any]) -> dict[str, Any]:
    from asset_finance_modeler.web_api.assets import delete_asset

    return delete_asset(str(args["asset_id"]), _tenant(args))
