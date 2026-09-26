"""Los ACTIVOS del Portfolio, como herramientas (26-sep).

El agente (o la IA del usuario por el conector) guarda, lista, actualiza y
promueve activos de CUALQUIER tipo (renovables, inmobiliario, empresas, SaaS,
hibridos): los mismos que ve el Portfolio. Reutiliza la API REST del Portfolio
(web_api.assets) con el espacio de la llamada (lo fija /call con el tenant_id).
Antes lo que se modelaba por chat no aparecia en el Portfolio.
"""
from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException

from asset_finance_modeler.store.scenarios import espacio_actual


def _tenant(args: dict[str, Any]):
    from asset_finance_modeler.web_api.auth import TenantContext

    ws = espacio_actual() or args.get("workspace_id")
    if not ws:
        raise ValueError("workspace-required: falta el espacio (tenant_id)")
    return TenantContext(workspace_id=str(ws), user_id=str(args.get("user_id") or "default"))


def _reglas(v: Any) -> list[dict[str, str]]:
    """Reglas de asignacion: [{proveedor?, nif?, linea?}], sin basura."""
    out: list[dict[str, str]] = []
    for r in list(v or [])[:50]:
        if not isinstance(r, dict):
            continue
        x = {k: str(r[k]).strip()[:120] for k in ("proveedor", "nif", "linea") if r.get(k) not in (None, "")}
        if x.get("proveedor") or x.get("nif"):
            out.append(x)
    return out


def _gestion(s: Any, args: dict[str, Any]) -> None:
    """Carpeta y reglas del activo (se guardan con sus datos, no en el modelo)."""
    snap = dict(s.inputs_snapshot or {})
    if args.get("carpeta"):
        snap["carpeta"] = str(args["carpeta"]).strip().strip("/")[:300]
    if "reglas" in args:
        snap["reglas"] = _reglas(args.get("reglas"))
    if isinstance(args.get("fuentes"), dict):
        # De donde sale cada hipotesis (ruta -> {fuente, fecha, nota}); se suman.
        f = dict(snap.get("fuentes") or {})
        for ruta, v in list(args["fuentes"].items())[:200]:
            if v in (None, "", {}):
                f.pop(str(ruta), None)
            elif isinstance(v, dict):
                f[str(ruta)[:200]] = {k: str(v[k])[:500] for k in ("fuente", "fecha", "nota", "valor") if v.get(k) not in (None, "")}
            else:
                f[str(ruta)[:200]] = {"fuente": str(v)[:500]}
        snap["fuentes"] = f
    s.inputs_snapshot = snap


_IPC_INGRESOS = re.compile(r"(^|\.)(revenue[^.]*\.(escalation_pct_yr|growth_pct_yr)|revenue\.sources\[\d+\]\.pricing\.price_escalation_annual|alquiler\.subida_anual)$")
_IPC_GASTOS = re.compile(r"(^|\.)(opex\.(opex_)?escalation_pct_yr|gastos\.subida_anual|meta\.inflation_annual)$")


def aplicar_ipc(model_id: str, overrides: dict[str, Any], ipc: Any) -> tuple[dict[str, Any], list[str]]:
    """El IPC de una vez (26-sep): a las subidas anuales de ingresos, de gastos
    o de todo. Lo que el usuario haya fijado en una ruta manda sobre el IPC.
    `ipc`: 0.03, o {"valor": 0.03, "a": "todo"|"ingresos"|"gastos"}."""
    if ipc in (None, "", {}):
        return overrides, []
    valor, a = (ipc.get("valor"), str(ipc.get("a") or "todo")) if isinstance(ipc, dict) else (ipc, "todo")
    valor = float(valor)
    if not -0.2 <= valor <= 0.5:
        raise ValueError("ipc-fuera-de-rango: el IPC va en tanto por uno (0.03 = 3 %)")
    from asset_finance_modeler.web_api.models import model_schema

    out, aplicadas = dict(overrides or {}), []
    for x in model_schema(model_id).get("inputs", []):
        ruta = str(x.get("path", ""))
        if not isinstance(x.get("value"), (int, float)) or isinstance(x.get("value"), bool) or ruta in out:
            continue
        if (a in ("todo", "ingresos") and _IPC_INGRESOS.search(ruta)) or (a in ("todo", "gastos") and _IPC_GASTOS.search(ruta)):
            out[ruta] = valor
            aplicadas.append(ruta)
    return out, aplicadas


_POR_ANIO = {"M": 12, "Q": 4, "Y": 1}


def aplicar_anios(model_id: str, overrides: dict[str, Any], anios: Any) -> dict[str, Any]:
    """Los anios de proyeccion (26-sep), sea cual sea la unidad del modelo: los
    modelos van por meses (periods=120 son 10 anios), el del piso por anios."""
    if anios in (None, ""):
        return overrides
    n = int(anios)
    if not 1 <= n <= 60:
        raise ValueError("anios-fuera-de-rango: entre 1 y 60 anios")
    from asset_finance_modeler.web_api.models import model_schema

    out = dict(overrides or {})
    valores = {x["path"]: x.get("value") for x in model_schema(model_id).get("inputs", [])}
    for ruta in valores:
        if ruta == "horizonte_anios":
            out[ruta] = n
        elif ruta.endswith("meta.horizon.periods"):
            f = str(out.get(ruta[: -len("periods")] + "frequency") or valores.get(ruta[: -len("periods")] + "frequency") or "Y")
            out[ruta] = n * _POR_ANIO.get(f, 1)
    return out


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
    overrides, con_ipc = aplicar_ipc(str(args["model_id"]), args.get("overrides") or {}, args.get("ipc"))
    overrides = aplicar_anios(str(args["model_id"]), overrides, args.get("anios"))
    body = SaveAssetBody(
        model_id=str(args["model_id"]), name=str(args["name"]), overrides=overrides,
        tags=args.get("tags") or [], location=args.get("location"), lat=args.get("lat"), lon=args.get("lon"),
    )
    r = save_asset(body, t)
    if args.get("carpeta") or args.get("reglas") or args.get("fuentes") or con_ipc:
        from asset_finance_modeler.web_api.assets import _store

        s = _store().get(r["id"], workspace_id=t.workspace_id)
        _gestion(s, args)
        if con_ipc:
            s.inputs_snapshot = {**(s.inputs_snapshot or {}), "ipc_aplicado_a": con_ipc}
        _store().save(s)
    a = get_asset(r["id"], t)
    return {
        "id": r["id"], "name": a["name"], "model_id": a["model_id"], "kpis": (a.get("results_snapshot") or {}).get("kpis", {}),
        "carpeta": a.get("carpeta"), "reglas": a.get("reglas"),
        **({"ipc_aplicado_a": con_ipc} if con_ipc else {}),
    }


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
        "location": a.get("location"), "carpeta": a.get("carpeta"), "reglas": a.get("reglas"),
        "fuentes": a.get("fuentes") or {}, "lifecycle": a.get("lifecycle"),
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
    if not args.get("overrides") and not args.get("quitar") and not args.get("name") and ("carpeta" in args or "reglas" in args or "fuentes" in args):
        # Solo como lo gestiona el agente: vale tambien en operacion.
        _gestion(s, args)
        store.save(s)
        snap = s.inputs_snapshot or {}
        return {"id": s.id, "name": s.name, "carpeta": snap.get("carpeta"), "reglas": snap.get("reglas") or [], "fuentes": snap.get("fuentes") or {}}
    if s.base_locked and (args.get("overrides") or args.get("ipc") not in (None, "", {}) or args.get("anios")):
        return {"error": "base_locked", "detail": "Activo en operacion: su base no se cambia (se compara con los reales). Para cambiarla, finance.asset.set_lifecycle a opportunity."}
    snap = dict(s.inputs_snapshot or {})
    overrides = {**(snap.get("overrides") or s.overrides or {}), **(args.get("overrides") or {})}
    for k in list(args.get("quitar") or []):
        overrides.pop(k, None)
    con_ipc: list[str] = []
    if args.get("ipc") not in (None, "", {}):
        # El nuevo IPC sustituye al anterior, salvo en lo que se fije ahora a mano.
        previas = {r for r in (snap.get("ipc_aplicado_a") or []) if r not in (args.get("overrides") or {})}
        overrides, con_ipc = aplicar_ipc(s.base_model, {k: v for k, v in overrides.items() if k not in previas}, args["ipc"])
        snap["ipc_aplicado_a"] = con_ipc
    overrides = aplicar_anios(s.base_model, overrides, args.get("anios"))
    results = _run_model(s.base_model, overrides)
    s.overrides = overrides
    snap["overrides"] = overrides
    for k in ("location", "lat", "lon"):
        if k in args:
            snap[k] = args[k]
    s.inputs_snapshot = snap
    _gestion(s, args)
    s.results_snapshot = results
    if args.get("name"):
        s.name = str(args["name"])
    store.save(s)
    return {"id": s.id, "name": s.name, "kpis": results.get("kpis", {}), **({"ipc_aplicado_a": con_ipc} if con_ipc else {})}


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


def _por_defecto(model_id: str, overrides: dict[str, Any], fin: tuple[str, ...]) -> float | None:
    """El valor de una hipotesis (la del activo, o la de serie del modelo)."""
    for k, v in (overrides or {}).items():
        if k.endswith(fin) and isinstance(v, (int, float)):
            return float(v)
    from asset_finance_modeler.web_api.models import model_schema

    for x in model_schema(model_id).get("inputs", []):
        if str(x.get("path", "")).endswith(fin) and isinstance(x.get("value"), (int, float)):
            return float(x["value"])
    return None


@_seguro
def handle_value(args: dict[str, Any]) -> dict[str, Any]:
    """Cuanto vale hoy un activo guardado (asset_id) o un modelo con hipotesis
    (model_id + overrides): flujos descontados, multiplo opcional, deuda neta y
    sensibilidad. `tasa`, `crecimiento`, `multiplo_ebitda`, `deuda_neta`,
    `perpetuidad` y `ebitda_referencia` mandan sobre lo del modelo."""
    from asset_finance_modeler.valoracion import valorar
    from asset_finance_modeler.web_api.assets import _run_model, get_asset

    if args.get("asset_id"):
        a = get_asset(str(args["asset_id"]), _tenant(args))
        model_id, overrides, result = a["model_id"], a.get("overrides") or {}, a.get("results_snapshot") or {}
        nombre = a["name"]
    elif args.get("model_id"):
        model_id = str(args["model_id"])
        overrides, _ = aplicar_ipc(model_id, dict(args.get("overrides") or {}), args.get("ipc"))
        overrides = aplicar_anios(model_id, overrides, args.get("anios"))
        result, nombre = _run_model(model_id, overrides), model_id
    else:
        return {"error": "asset_id-o-model_id-required"}
    tasa = args.get("tasa")
    if tasa is None:
        tasa = _por_defecto(model_id, overrides, ("discount_rate_annual", "tasa_descuento"))
    g = args.get("crecimiento")
    if g is None:
        g = _por_defecto(model_id, overrides, ("terminal_growth_rate",))
    v = valorar(
        result, model_id=model_id, tasa=float(tasa if tasa is not None else 0.08),
        crecimiento=float(g if g is not None else 0.02),
        perpetuidad=args.get("perpetuidad"), multiplo_ebitda=args.get("multiplo_ebitda"),
        deuda_neta=float(args.get("deuda_neta") or 0), ebitda_referencia=args.get("ebitda_referencia"),
    )
    return {"activo": nombre, "model_id": model_id, **v}
