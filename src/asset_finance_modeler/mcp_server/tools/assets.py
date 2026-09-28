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
    a = get_asset(r["id"], t)
    return {
        "id": r["id"], "name": a["name"], "model_id": a["model_id"], "kpis": (a.get("results_snapshot") or {}).get("kpis", {}),
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
