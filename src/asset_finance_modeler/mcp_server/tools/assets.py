"""Los ACTIVOS del Portfolio, como herramientas (26-sep).

El agente (o la IA del usuario por el conector) guarda, lista, actualiza y
promueve activos de CUALQUIER tipo (renovables, inmobiliario, empresas, SaaS,
hibridos): los mismos que ve el Portfolio. Reutiliza la API REST del Portfolio
(web_api.assets) con el espacio de la llamada (lo fija /call con el tenant_id).
Antes lo que se modelaba por chat no aparecia en el Portfolio.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
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
        # Los modelos a veces usan otros nombres (lineaActivo, vendor...).
        r = {**r, "linea": r.get("linea") or r.get("lineaActivo") or r.get("linea_activo") or r.get("line"),
             "proveedor": r.get("proveedor") or r.get("vendor") or r.get("supplier"), "nif": r.get("nif") or r.get("cif")}
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
    curva = ipc.get("curva") if isinstance(ipc, dict) else (ipc if isinstance(ipc, list) else None)
    a = str(ipc.get("a") or "todo") if isinstance(ipc, dict) else "todo"
    con_bloque = model_id.startswith("business_") or model_id == "real_estate_rental" or model_id.startswith("inmueble")
    if not curva and con_bloque:
        # Empresas y pisos (27-sep): el IPC va a su bloque de inflacion, que lo
        # SUMA al crecimiento real de cada linea. Antes sustituia el crecimiento
        # (un "5 % real + IPC" se quedaba en el IPC) y se acumulaba al rehacerlo.
        curva = [ipc.get("valor") if isinstance(ipc, dict) else ipc]
    if curva:
        # Curva anio a anio: la llevan las empresas y el piso (en renovables,
        # la curva va en el precio de cada linea: price_points).
        if not con_bloque:
            raise ValueError("curva-no-soportada: la curva de IPC va en empresas y en inmueble_alquiler; en renovables usa price_points de cada linea")
        valores = [float(x) for x in curva][:60]
        if any(not -0.2 <= x <= 0.5 for x in valores):
            raise ValueError("ipc-fuera-de-rango: cada anio en tanto por uno (0.03 = 3 %)")
        out = dict(overrides or {})
        out["inflacion"] = {"curva": valores, "aplicar_a": a if a in ("todo", "ingresos", "gastos") else "todo"}
        return out, ["inflacion"]
    valor = float(ipc.get("valor") if isinstance(ipc, dict) else ipc)
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


_CLAVE = re.compile(r"(corporate_income_tax_rate|tipo_sociedades|tipo_marginal_irpf|regimen|discount_rate_annual|tasa_descuento|terminal_growth_rate|horizon\.periods|horizon\.frequency|horizonte_anios|receivable_days|payable_days|inventory_days|tax_loss_carryforward)$")


def supuestos_clave(model_id: str, overrides: dict[str, Any], result: dict[str, Any] | None = None) -> dict[str, Any]:
    """Lo que el modelo supone aunque el usuario no lo haya dicho (impuestos,
    tasa, duracion, cobros y pagos, inversion), para no explicarlo mal: el
    27-sep un agente dijo "no he incluido el impuesto de sociedades" y si iba."""
    from asset_finance_modeler.web_api.models import model_schema

    out: dict[str, Any] = {}
    for x in model_schema(model_id).get("inputs", []):
        ruta = str(x.get("path", ""))
        if _CLAVE.search(ruta):
            out[ruta] = overrides.get(ruta, x.get("value"))
    if "inflacion" in (overrides or {}):
        out["inflacion"] = overrides["inflacion"]
    if result is not None:
        out["inversion_total"] = (result.get("kpis") or {}).get("total_capex")
    return out


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


def _id_de(args: dict[str, Any]) -> str:
    """El id del activo; si le pasan su NOMBRE (lo hacen los modelos), el del
    activo del espacio que se llama asi (27-sep)."""
    pedido = str(args.get("asset_id") or "").strip()
    if not pedido or pedido.startswith("scn-"):
        return pedido
    from asset_finance_modeler.web_api.assets import list_assets

    import unicodedata

    def plano(x: Any) -> str:
        t = unicodedata.normalize("NFD", str(x or "").lower())
        t = "".join(c for c in t if unicodedata.category(c) != "Mn")
        return " ".join(re.sub(r"[^a-z0-9]+", " ", t).split())

    activos = list_assets(None, _tenant(args))["assets"]
    iguales = [a["id"] for a in activos if plano(a["name"]) == plano(pedido)]
    if not iguales and plano(pedido):
        # "clinica-dental" para "Clínica Dental Centro": solo si encaja uno.
        iguales = [a["id"] for a in activos if plano(pedido) in plano(a["name"])]
    return iguales[0] if len(iguales) == 1 else pedido


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


_MAX_ESQUEMA = 3500  # el bucle del agente corta cada resultado a 4.000 caracteres

# Listas y bloques que por defecto estan vacios y por eso no salen en las rutas
# (27-sep: un agente pidio el esquema 35 veces buscando como meter un prestamo).
_EST_EMPRESA = {
    "financing.prestamos": [{"nombre": "ICO", "tipo": "prestamo|hipoteca|leasing|poliza", "importe": 120000, "tipo_interes": 0.045,
                             "plazo_anios": 5, "carencia_meses": 0, "amortizacion": "french|linear|bullet", "anio_inicio": 0,
                             "comision_apertura_pct": 0.0, "valor_residual": 0, "ya_dispuesto": True}],
    "inflacion": {"curva": [0.03, 0.025, 0.02], "aplicar_a": "todo|ingresos|gastos"},
    "revenue": [{"name": "Ventas", "year1_amount": 600000, "growth_pct_yr": 0.05}],
    "opex.fixed_lines": [{"name": "Alquiler", "year1_amount": 36000, "growth_pct_yr": None}],
    "capex.items": [{"name": "Equipos", "amount": 30000, "period": 0, "depreciation_years": 8}],
}
_EST_RENOVABLES = {
    "degradation": {"type": "custom", "curve": [1.0, 0.99, 0.986]},
    "losses.curtailment_curve": [0.0, 0.02, 0.03],
    "losses.equipment_events": [{"year": 8, "loss_pct": 0.05, "years": 1, "label": "Inversores"}],
    "opex.other_lines": [{"name": "Representacion de mercado", "eur_yr": 0, "eur_per_mw_yr": 0, "eur_per_mwh": 0.8, "escalation_pct_yr": None}],
    "opex.decommissioning": {"cost_eur": 1500000, "accrue_years": 5},
    "capex_events": [{"year": 18, "amount": 4000000, "resets_degradation": True, "capacity_uplift_pct": 0.15, "label": "Repowering"}],
    "financing.equity.lockup_dscr": 1.2,
    "sin deuda (100 % fondos propios)": {"financing.max_leverage": 0, "financing.senior.tenor_years": 0},
}
_EST_INMUEBLE = {"inflacion": {"curva": [0.03, 0.025, 0.02], "aplicar_a": "todo|ingresos|gastos"}}


def _estructuras(model_id: str) -> dict[str, Any]:
    if model_id.startswith("business_") or model_id == "real_estate_rental":
        return _EST_EMPRESA
    if model_id.startswith("inmueble"):
        return _EST_INMUEBLE
    if model_id.startswith(("solar", "wind", "bess", "svj_fv", "svj_bess")):
        return _EST_RENOVABLES
    return {}


@_seguro
def handle_schema(args: dict[str, Any]) -> dict[str, Any]:
    """Las rutas del modelo con su valor de serie, compactas ({ruta: valor}).
    `seccion` (o varias) filtra por el principio de la ruta ("opex", "losses",
    "degradation"…). 27-sep: el esquema entero (9.900 caracteres en la solar)
    llegaba cortado al agente y nunca veia degradation ni losses."""
    import json as _json

    from asset_finance_modeler.web_api.models import model_schema

    model_id = str(args["model_id"])
    rutas = {str(x["path"]): x.get("value") for x in model_schema(model_id).get("inputs", [])}
    pedidas = args.get("seccion") or args.get("secciones") or args.get("section") or args.get("include")
    if isinstance(pedidas, str):
        pedidas = [t.strip() for t in re.split(r"[,\s]+", pedidas) if t.strip()]
    if pedidas:
        rutas = {r: v for r, v in rutas.items() if any(r == p or r.startswith(p + ".") or r.startswith(p + "[") for p in pedidas)}
    secciones: dict[str, int] = {}
    for r in model_schema(model_id).get("inputs", []):
        cab = re.split(r"[.\[]", str(r["path"]))[0]
        secciones[cab] = secciones.get(cab, 0) + 1
    est = _estructuras(model_id)
    if pedidas:
        est = {k: v for k, v in est.items() if any(k == p or k.startswith(p + ".") or p.startswith(k) or p == "estructuras" for p in pedidas)}
    out: dict[str, Any] = {"model_id": model_id, "rutas": rutas}
    if est:
        out["estructuras"] = est
        out["como"] = "Las estructuras (listas y bloques) se pasan enteras en overrides con esa clave, p.ej. {\"financing.prestamos\": [...]}."
        if len(_json.dumps(out, default=str)) > _MAX_ESQUEMA and not pedidas:
            out.pop("estructuras")
            out["como"] = "Hay listas y bloques que no salen aqui (prestamos, curvas, averias, repowering…): pidelos con seccion \"estructuras\"."
    if len(_json.dumps(out, default=str)) > _MAX_ESQUEMA:
        # No cabe: lo que quepa y el indice, para pedir el resto por seccion.
        parcial: dict[str, Any] = {}
        for r, v in rutas.items():
            parcial[r] = v
            if len(_json.dumps(parcial, default=str)) > _MAX_ESQUEMA - 600:
                parcial.pop(r)
                break
        out = {"model_id": model_id, "rutas": parcial, "secciones": secciones,
               "nota": "Faltan rutas: pide las de una seccion con seccion (p.ej. \"opex\", \"losses\", \"degradation\", \"financing\")"
               + (" o las listas y bloques con seccion \"estructuras\"." if est else ".")}
    elif not pedidas:
        out["secciones"] = secciones
    return out


@_seguro
def handle_save(args: dict[str, Any]) -> dict[str, Any]:
    from asset_finance_modeler.web_api.assets import SaveAssetBody, get_asset, save_asset

    t = _tenant(args)
    # Guardar otro con el mismo nombre suele ser un error (se queria cambiar el
    # que ya hay: reglas, hipotesis…). El 27-sep el agente duplico una clinica.
    if not args.get("duplicar"):
        from asset_finance_modeler.web_api.assets import list_assets

        plano = lambda x: " ".join(str(x or "").lower().split())  # noqa: E731
        ya = [a for a in list_assets(None, t)["assets"] if plano(a["name"]) == plano(args["name"])]
        if ya:
            return {"error": "ya-existe", "asset_id": ya[0]["id"],
                    "detail": f"Ya hay un activo \"{ya[0]['name']}\" ({ya[0]['id']}). Para cambiarlo (hipotesis, reglas, carpeta, fuentes) usa finance.asset.update con ese asset_id; para crear otro igual, duplicar: true o otro nombre."}
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
    en_marcha = args.get("en_operacion_desde") or args.get("commissioning_date")
    if en_marcha and str(en_marcha)[:10] <= datetime.now(UTC).date().isoformat():
        # Ya produce: va a la Cartera, no a Oportunidades (29-sep).
        from asset_finance_modeler.web_api.assets import LifecycleBody, set_lifecycle

        set_lifecycle(r["id"], LifecycleBody(lifecycle="operational", commissioning_date=str(en_marcha)[:10]), t)
    a = get_asset(r["id"], t)
    return {
        "id": r["id"], "name": a["name"], "model_id": a["model_id"], "lifecycle": a.get("lifecycle"), "kpis": (a.get("results_snapshot") or {}).get("kpis", {}),
        "carpeta": a.get("carpeta"), "reglas": a.get("reglas"),
        **({"ipc_aplicado_a": con_ipc} if con_ipc else {}),
        "supuestos_clave": supuestos_clave(a["model_id"], a.get("overrides") or {}, a.get("results_snapshot") or {}),
    }


@_seguro
def handle_list(args: dict[str, Any]) -> dict[str, Any]:
    from asset_finance_modeler.web_api.assets import list_assets

    return list_assets(args.get("lifecycle"), _tenant(args))


@_seguro
def handle_get(args: dict[str, Any]) -> dict[str, Any]:
    from asset_finance_modeler.web_api.assets import get_asset

    a = get_asset(_id_de(args), _tenant(args))
    rs = a.get("results_snapshot") or {}
    # Lo esencial: sus datos, KPIs y las series anuales (no el volcado entero).
    return {
        "id": a["id"], "name": a["name"], "model_id": a["model_id"], "overrides": a.get("overrides", {}),
        "kpis": rs.get("kpis", {}), "income_statement": rs.get("income_statement"), "cash_flow": rs.get("cash_flow"),
        "location": a.get("location"), "carpeta": a.get("carpeta"), "reglas": a.get("reglas"),
        "fuentes": a.get("fuentes") or {}, "lifecycle": a.get("lifecycle"),
        "supuestos_clave": supuestos_clave(a["model_id"], a.get("overrides") or {}, rs),
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
    s = store.get(_id_de(args), workspace_id=t.workspace_id)
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
    return {"id": s.id, "name": s.name, "kpis": results.get("kpis", {}), **({"ipc_aplicado_a": con_ipc} if con_ipc else {}),
            "supuestos_clave": supuestos_clave(s.base_model, overrides, results)}


@_seguro
def handle_lifecycle(args: dict[str, Any]) -> dict[str, Any]:
    from asset_finance_modeler.web_api.assets import LifecycleBody, set_lifecycle

    body = LifecycleBody(
        lifecycle=args["lifecycle"], tracking_frequency=args.get("tracking_frequency"),
        commissioning_date=args.get("commissioning_date"),
    )
    return set_lifecycle(_id_de(args), body, _tenant(args))


@_seguro
def handle_delete(args: dict[str, Any]) -> dict[str, Any]:
    from asset_finance_modeler.web_api.assets import delete_asset

    return delete_asset(_id_de(args), _tenant(args))


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
        a = get_asset(_id_de(args), _tenant(args))
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
    # Sin deuda neta dicha: la de los prestamos que ya tiene el negocio.
    deuda_de_prestamos = None
    if args.get("deuda_neta") is None:
        ya = [p for p in (overrides.get("financing.prestamos") or []) if isinstance(p, dict) and p.get("ya_dispuesto")]
        if ya:
            deuda_de_prestamos = sum(float(p.get("importe") or 0) for p in ya)
    deuda_neta = float(args.get("deuda_neta") if args.get("deuda_neta") is not None else (deuda_de_prestamos or 0))
    v = valorar(
        result, model_id=model_id, tasa=float(tasa if tasa is not None else 0.08),
        crecimiento=float(g if g is not None else 0.02),
        perpetuidad=args.get("perpetuidad"), multiplo_ebitda=args.get("multiplo_ebitda"),
        deuda_neta=deuda_neta, ebitda_referencia=args.get("ebitda_referencia"),
    )
    if deuda_de_prestamos is not None:
        v["notas"] = ["Deuda neta tomada de los préstamos que ya tiene (sin descontar su caja; pásala si tiene)."] + [
            n for n in v.get("notas", []) if not n.startswith("Sin deuda neta")]
    return {"activo": nombre, "model_id": model_id, **v}


# ── Lo que se ve en la app, también para el agente y la IA del conector (28-sep) ──

def _norm(t: Any) -> str:
    import unicodedata  # noqa: PLC0415

    return "".join(c for c in unicodedata.normalize("NFD", str(t or "").lower()) if unicodedata.category(c) != "Mn")


@_seguro
def handle_series(args: dict[str, Any]) -> dict[str, Any]:
    """Lo real frente a lo previsto de una línea (ingresos, producción, un
    gasto…) por día, semana, mes o año. `linea` admite la ruta o su nombre."""
    from asset_finance_modeler.web_api.actuals import _actuals_store, _get_asset_or_404, _trackable_lines, serie_real_vs_prevision  # noqa: PLC0415

    t = _tenant(args)
    s = _get_asset_or_404(_id_de(args), workspace_id=t.workspace_id)
    lineas = _trackable_lines(s.results_snapshot)
    pedida = str(args.get("linea") or args.get("line_path") or "").strip()
    elegida = None
    if pedida:
        n = _norm(pedida)
        elegida = next((x for x in lineas if x["path"] == pedida), None) \
            or next((x for x in lineas if _norm(x["label"]) == n or _norm(x["path"].split(".")[-1]) == n), None) \
            or next((x for x in lineas if n in _norm(x["label"]) or n in _norm(x["path"])), None)
    else:
        # Sin línea: la que más se sigue (producción, ingresos…).
        orden = sorted(lineas, key=lambda x: (0 if "produccion" in x["path"] else 1 if x["path"].endswith(".revenue") else 2))
        elegida = orden[0] if orden else None
    if elegida is None:
        return {"error": "linea-desconocida", "lineas": [x["label"] for x in lineas][:30]}
    cada = str(args.get("cada") or "mes")
    if cada not in ("dia", "semana", "mes", "anio"):
        return {"error": "cada-invalido", "detail": "dia, semana, mes o anio"}
    reales = _actuals_store().list(scenario_id=s.id, line_path=elegida["path"])
    r = serie_real_vs_prevision(s, reales, elegida["path"], cada, args.get("desde"), args.get("hasta"))
    # Compacto (el agente ve 4.000 caracteres): los últimos periodos.
    puntos = [{"p": x["etiqueta"], "real": x["real"], "prev": round(x["prevision"])} for x in r["puntos"]][-24:]
    return {
        "activo": s.name, "asset_id": s.id, "linea": elegida["label"], "unidad": elegida.get("unit") or "€", "cada": cada,
        "resumen": r["resumen"], "periodos": puntos,
        "ver_en_la_app": {"app": "portfolio", "ruta": f"asset/{s.id}/real"},
    }


@_seguro
def handle_overview(args: dict[str, Any]) -> dict[str, Any]:
    """El cuadro general de la cartera: totales, cada activo con su valor,
    deuda y cómo va el año, y la serie de la cartera por año natural."""
    from asset_finance_modeler.web_api.assets import portfolio  # noqa: PLC0415

    r = portfolio(ids=None, lifecycle=args.get("lifecycle"), tenant=_tenant(args))
    activos = []
    for a in r.get("assets", []):
        ytd = a.get("ytd")
        activos.append({
            "id": a["id"], "nombre": a["name"], "tipo": a.get("tipo"), "fase": a.get("lifecycle"),
            "van": round(a.get("npv") or 0), "tir": a.get("irr"), "valor": a.get("enterprise_value"),
            "deuda_viva": a.get("deuda_viva"), "ingresos_anio": a.get("ingresos_anio"),
            "cumplimiento_anio_pct": round(ytd["real"] / ytd["prevision"] * 100, 1) if ytd and ytd.get("prevision") else None,
        })
    c = r.get("consolidado") or {}
    return {
        "totales": {k: (round(v) if isinstance(v, float) else v) for k, v in (r.get("totals") or {}).items()},
        "activos": activos,
        "cartera_por_anio": [{"anio": y, "ingresos": c["revenue"][i], "ebitda": c["ebitda"][i], "flujo_caja": c["flujo_caja"][i], "deuda": c["deuda"][i]} for i, y in enumerate(c.get("years", []))][:15],
        "con_error": [x.get("name") for x in r.get("skipped", [])],
        "ver_en_la_app": {"app": "portfolio", "ruta": "cartera"},
    }


@_seguro
def handle_debt(args: dict[str, Any]) -> dict[str, Any]:
    """La deuda de un activo año a año: saldo, intereses, amortización y DSCR."""
    from asset_finance_modeler.web_api.assets import _run_model_cacheado, get_asset  # noqa: PLC0415

    a = get_asset(_id_de(args), _tenant(args))
    r = _run_model_cacheado(a["model_id"], a.get("overrides") or {})
    d = r.get("deuda")
    if not d or not any(d.get("disposiciones") or []):
        return {"activo": a["name"], "asset_id": a["id"], "sin_deuda": True, "nota": "Este activo no tiene deuda en su modelo."}
    dscr = [x for x in d.get("dscr", []) if x is not None]
    return {
        "activo": a["name"], "asset_id": a["id"],
        "pedida": round(sum(d.get("disposiciones", []))), "intereses_totales": round(sum(d.get("intereses", []))),
        "dscr_minimo": min(dscr) if dscr else None,
        "por_anio": [{"anio": y, "saldo": d["saldo"][i], "intereses": d["intereses"][i], "amortizacion": d["amortizacion"][i], "dscr": d["dscr"][i]} for i, y in enumerate(d["years"])][:30],
        "ver_en_la_app": {"app": "portfolio", "ruta": f"asset/{a['id']}/deuda"},
    }


# ── Configurar un activo en lenguaje de negocio (28-sep) ────────────────────
# El agente o la IA del conector dicen «precio de mercado con la curva X»,
# «degradación 0,5 %», «repowering el año 18», «estas ventas año a año»,
# «en agosto vendemos el doble»… y aquí se traduce a las rutas del modelo.

# Reparto mensual típico de la producción solar en España (aprox., % del año).
PERFIL_SOLAR_ES = [5.5, 6.5, 8.5, 9.3, 10.5, 10.9, 11.3, 10.6, 9.0, 7.5, 5.6, 4.8]


def _doce(v: Any) -> list[float] | None:
    if isinstance(v, dict):
        v = [v.get(k) for k in ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")]
    if not isinstance(v, (list, tuple)) or len(v) != 12:
        return None
    try:
        xs = [float(x) for x in v]
    except (TypeError, ValueError):
        return None
    return xs if sum(xs) > 0 and all(x >= 0 for x in xs) else None


def _config_actual(model_id: str, overrides: dict[str, Any]) -> dict[str, Any]:
    from asset_finance_modeler.web_api.models import _apply_overrides, _BUSINESS_IDS, load_business_preset, load_preset  # noqa: PLC0415

    base = load_business_preset(model_id).model_dump() if model_id in _BUSINESS_IDS else load_preset(model_id).model_dump()
    return _apply_overrides(base, overrides)


def _lineas(actuales: list[dict[str, Any]], pedidas: Any, cambios: list[str], que: str) -> list[dict[str, Any]]:
    """Mezcla líneas por nombre: cambia las que existen y añade las nuevas."""
    out = [dict(x) for x in actuales]
    for p in list(pedidas or [])[:40]:
        if not isinstance(p, dict) or not str(p.get("nombre") or p.get("name") or "").strip():
            continue
        nombre = str(p.get("nombre") or p.get("name")).strip()
        ln = next((x for x in out if _norm(x.get("name")) == _norm(nombre)), None)
        if ln is None:
            ln = {"name": nombre, "year1_amount": 0.0}
            out.append(ln)
        if p.get("quitar"):
            out.remove(ln)
            cambios.append(f"{que}: quitado «{nombre}»")
            continue
        if p.get("importe") is not None:
            ln["year1_amount"] = float(p["importe"])
        if p.get("crecimiento") is not None:
            ln["growth_pct_yr"] = float(p["crecimiento"])
        if isinstance(p.get("curva"), list) and p["curva"]:
            ln["curva"] = [float(x) for x in p["curva"]][:60]
            ln["year1_amount"] = ln["curva"][0]
            ln["crecimientos"] = None
        if isinstance(p.get("crecimientos"), list) and p["crecimientos"]:
            ln["crecimientos"] = [float(x) for x in p["crecimientos"]][:60]
            ln["curva"] = None
        cambios.append(f"{que}: «{nombre}» " + ("con su curva año a año" if ln.get("curva") else "con sus subidas año a año" if ln.get("crecimientos") else f"{ln['year1_amount']:,.0f} € el primer año".replace(",", ".")))
    return out


@_seguro
def handle_configure(args: dict[str, Any]) -> dict[str, Any]:
    """Configura un activo por bloques: ingresos/gastos (curva o subidas por
    año), precio (curva de mercado, puntos o fijo), producción (perfil mensual,
    producible), estacionalidad, IPC, años, degradación, repowering, averías y
    recortes. Lo que no aplique a su tipo se dice, no se inventa."""
    from asset_finance_modeler.web_api.assets import _store  # noqa: PLC0415
    from asset_finance_modeler.web_api.models import _BUSINESS_IDS, _INMUEBLE_IDS  # noqa: PLC0415

    t = _tenant(args)
    store = _store()
    s = store.get(_id_de(args), workspace_id=t.workspace_id)
    if s is None or s.is_deleted:
        return {"error": "not_found"}
    model_id = s.base_model
    snap = dict(s.inputs_snapshot or {})
    overrides_previos = dict(snap.get("overrides") or s.overrides or {})
    es_empresa = model_id in _BUSINESS_IDS
    es_inmueble = model_id in _INMUEBLE_IDS
    es_renovable = model_id.startswith(("solar", "wind", "bess"))
    cambios: list[str] = []
    avisos: list[str] = []
    ov: dict[str, Any] = {}

    # Estacionalidad (para comparar lo real): se guarda con el activo.
    if args.get("estacionalidad") is not None:
        e = args["estacionalidad"]
        if isinstance(e, dict) and _doce(e) is None:
            por_linea = {str(k): _doce(v) for k, v in e.items()}
            if not all(por_linea.values()):
                return {"error": "estacionalidad-invalida", "detail": "12 números (uno por mes, ene…dic) o {linea: [12 números]}."}
            snap["estacionalidad"] = por_linea
        else:
            d = _doce(e)
            if d is None:
                return {"error": "estacionalidad-invalida", "detail": "12 números (uno por mes, ene…dic): pesos o % de cada mes."}
            snap["estacionalidad"] = {"*": d}
        cambios.append("estacionalidad mensual para comparar lo real con lo previsto")

    try:
        cfg = _config_actual(model_id, overrides_previos) if (es_empresa or es_renovable) else {}
    except Exception:  # noqa: BLE001
        cfg = {}

    if args.get("ingresos") or args.get("gastos"):
        if es_empresa:
            if args.get("ingresos"):
                ov["revenue"] = _lineas(cfg.get("revenue") or [], args["ingresos"], cambios, "ingreso")
            if args.get("gastos"):
                ov["opex.fixed_lines"] = _lineas((cfg.get("opex") or {}).get("fixed_lines") or [], args["gastos"], cambios, "gasto")
        else:
            avisos.append("Ingresos y gastos línea a línea con curva: en empresas. " + ("En inmuebles, la renta y los gastos van con sus hipótesis (overrides) y el IPC." if es_inmueble else "En renovables, el ingreso sale de la producción y el precio (usa `precio`)."))

    if args.get("precio") is not None:
        if not es_renovable:
            avisos.append("`precio` es para renovables (€/MWh).")
        else:
            p = args["precio"] if isinstance(args["precio"], dict) else {"fijo": args["precio"]}
            fuentes = [dict(x) for x in (cfg.get("revenue") or [])]
            quiere = _norm(p.get("contrato") or "merchant")
            idx = next((i for i, x in enumerate(fuentes) if _norm(x.get("type")) == quiere or _norm(x.get("name")) == quiere), None)
            if idx is None:
                return {"error": "contrato-desconocido", "detail": "contratos: " + ", ".join(f"{x.get('type')} ({x.get('name')})" for x in fuentes)}
            f = fuentes[idx]
            if p.get("curva"):
                f["price_curve_name"], f["price_points"] = str(p["curva"]), None
                cambios.append(f"precio {f.get('name')}: curva de mercado «{p['curva']}»")
            elif isinstance(p.get("puntos"), list):
                f["price_points"], f["price_curve_name"] = [float(x) for x in p["puntos"]][:60], None
                cambios.append(f"precio {f.get('name')}: {len(f['price_points'])} años de precio propio")
            elif p.get("fijo") is not None:
                k = "price_eur_per_unit" if f.get("type") == "ppa" else "base_price_eur_per_unit"
                f[k], f["price_curve_name"], f["price_points"] = float(p["fijo"]), None, None
                cambios.append(f"precio {f.get('name')}: {float(p['fijo'])} €/MWh")
            if p.get("subida") is not None:
                f["escalation_pct_yr"] = float(p["subida"])
            if p.get("volumen") is not None:
                f["volume_fraction"] = float(p["volumen"])
            if p.get("anios") is not None and f.get("type") == "ppa":
                f["tenor_years"] = int(p["anios"])
            fuentes[idx] = f
            ov["revenue"] = fuentes

    if args.get("produccion") is not None:
        if not es_renovable:
            avisos.append("`produccion` es para renovables.")
        else:
            p = args["produccion"] if isinstance(args["produccion"], dict) else {}
            tipo = (cfg.get("production") or {}).get("type")
            perfil = _doce(p.get("perfil_mensual"))
            if perfil:
                ov["production.irradiation_profile" if tipo == "solar_pv" else "production.production_profile"] = perfil
                cambios.append("producción mes a mes con su perfil")
            if p.get("producible") is not None and tipo == "solar_pv":
                ov["production.specific_yield_kwh_kwp"] = float(p["producible"])
                cambios.append(f"producible {float(p['producible'])} kWh/kWp")
            if p.get("factor_capacidad") is not None and tipo == "wind_onshore":
                ov["production.capacity_factor"] = float(p["factor_capacidad"])
                cambios.append(f"factor de capacidad {float(p['factor_capacidad'])}")

    if args.get("degradacion") is not None:
        if not es_renovable:
            avisos.append("`degradacion` es para renovables.")
        else:
            d = args["degradacion"]
            ov["degradation"] = {"type": "custom", "curve": [float(x) for x in d][:60]} if isinstance(d, list) else {"type": "time_based", "annual_rate": float(d)}
            cambios.append("degradación " + ("con su curva año a año" if isinstance(d, list) else f"{float(d) * 100:.2f} % al año"))

    if args.get("repowering") is not None:
        if not es_renovable:
            avisos.append("`repowering` es para renovables.")
        else:
            ev = []
            for r in list(args["repowering"] or [])[:10]:
                if isinstance(r, dict) and r.get("anio"):
                    ev.append({"year": max(0, int(r["anio"]) - 1), "amount": float(r.get("inversion") or 0),
                               "resets_degradation": bool(r.get("vuelve_a_placa", True)),
                               "capacity_uplift_pct": float(r.get("mas_potencia_pct") or 0), "label": str(r.get("nombre") or "Repowering")})
            ov["capex_events"] = ev
            cambios.append(f"{len(ev)} repowering" + ("s" if len(ev) != 1 else ""))

    if args.get("averias") is not None:
        if not es_renovable:
            avisos.append("`averias` es para renovables.")
        else:
            ev = [{"year": int(a["anio"]), "loss_pct": float(a.get("perdida_pct") or 0), "years": int(a.get("anios") or 1), "label": str(a.get("nombre") or "")}
                  for a in list(args["averias"] or [])[:20] if isinstance(a, dict) and a.get("anio")]
            ov["losses.equipment_events"] = ev
            cambios.append(f"{len(ev)} caída" + ("s" if len(ev) != 1 else "") + " de producción por equipos")

    if args.get("recortes") is not None:
        if not es_renovable:
            avisos.append("`recortes` es para renovables.")
        else:
            r = args["recortes"]
            if isinstance(r, list):
                ov["losses.curtailment_curve"] = [float(x) for x in r][:60]
            else:
                ov["losses.curtailment_pct"] = float(r)
            cambios.append("recortes de producción")

    # Lo del modelo, por el mismo camino que una actualización (valida, recalcula
    # y respeta la base bloqueada de un activo en marcha).
    resultado: dict[str, Any] = {}
    if ov or args.get("ipc") not in (None, "", {}) or args.get("anios"):
        if args.get("ipc") not in (None, "", {}):
            cambios.append("IPC")
        if args.get("anios"):
            cambios.append(f"{args['anios']} años de proyección")
        s.inputs_snapshot = snap
        store.save(s)
        resultado = handle_update({"asset_id": s.id, "workspace_id": t.workspace_id, "user_id": t.user_id,
                                   "overrides": ov, "ipc": args.get("ipc"), "anios": args.get("anios")})
        if resultado.get("error"):
            return {**resultado, "cambios_pedidos": cambios}
    else:
        s.inputs_snapshot = snap
        store.save(s)
    if es_renovable and model_id.startswith("solar") and "estacionalidad" not in snap and not (overrides_previos.get("production.irradiation_profile") or ov.get("production.irradiation_profile")):
        avisos.append("Para comparar lo real mes a mes se usa el reparto típico de la solar en España; si tienes el tuyo, pásalo en `produccion.perfil_mensual`.")
    return {
        "id": s.id, "activo": s.name, "cambios": cambios or ["nada que cambiar"], "avisos": avisos,
        **({"kpis": resultado.get("kpis")} if resultado.get("kpis") else {}),
        "ver_en_la_app": {"app": "portfolio", "ruta": f"asset/{s.id}/curvas"},
    }
