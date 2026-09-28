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
from asset_finance_modeler.store.actuals import SQLiteActualsStore
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore
from asset_finance_modeler.web_api.auth import TenantContext, require_token, tenant_ctx
from asset_finance_modeler.web_api.models import (
    _BUSINESS_IDS,
    _SAAS_IDS,
    _apply_overrides,
    _preset_ids,
    _run_business_config,
    _run_config,
    _run_saas_config,
    load_saas_preset,
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


def _actuals_store() -> SQLiteActualsStore:
    store = SQLiteActualsStore(_db_path())
    store.initialize()
    return store


def _last_update_iso(scenario: Scenario, actuals: SQLiteActualsStore) -> str:
    """Most-recent-activity timestamp for an asset, as an ISO string.

    Operational assets are tracked by ingesting real actuals, so the freshest
    signal a reader cares about is the latest actual's ``entered_at``. When there
    are no actuals (every opportunity, and operational assets not yet tracked),
    fall back to the scenario's ``created_at``. Returns the max of the two so a
    re-saved scenario never appears staler than its actuals.
    """
    created = scenario.created_at.isoformat()
    latest_actual = actuals.max_entered_at(scenario.id)
    if latest_actual and latest_actual > created:
        return latest_actual
    return created


_CACHE_DE_MODELOS: dict[str, dict[str, Any]] = {}


def _run_model_cacheado(model_id: str, overrides: dict[str, Any]) -> dict[str, Any]:
    """La cartera recalculaba TODOS los modelos en cada visita (28-sep): con
    los mismos datos el resultado es el mismo, así que se guarda (máx. 256)."""
    import json as _json  # noqa: PLC0415

    clave = model_id + "|" + _json.dumps(overrides or {}, sort_keys=True, default=str)
    r = _CACHE_DE_MODELOS.get(clave)
    if r is None:
        r = _run_model(model_id, overrides)
        if len(_CACHE_DE_MODELOS) >= 256:
            _CACHE_DE_MODELOS.pop(next(iter(_CACHE_DE_MODELOS)))
        _CACHE_DE_MODELOS[clave] = r
    return r


def _tipo_de_modelo(model_id: str) -> str:
    from asset_finance_modeler.web_api.models import _INMUEBLE_IDS  # noqa: PLC0415

    if model_id in _INMUEBLE_IDS or model_id == "real_estate_rental":
        return "inmueble"
    if model_id in _SAAS_IDS:
        return "saas"
    if model_id in _BUSINESS_IDS:
        return "negocio"
    if model_id.startswith(("solar", "wind", "bess", "svj")):
        return "renovable"
    return "infraestructura"


def _run_model(model_id: str, overrides: dict[str, Any]) -> dict[str, Any]:
    """Run a model and return its JSON-serializable result payload (with a
    top-level 'kpis' key). Mirrors web_api.models.model_run dispatch."""
    if model_id == "svj_hybrid":
        return run_svj(overrides)
    from asset_finance_modeler.web_api.models import _INMUEBLE_IDS, _run_inmueble_config
    if model_id in _INMUEBLE_IDS:
        from asset_finance_modeler.assets.inmobiliario.cargador import cargar_inmueble
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


router = APIRouter(prefix="/api/assets", dependencies=[Depends(require_token)])


class SaveAssetBody(BaseModel):
    model_id: str
    name: str
    overrides: dict[str, Any] = {}
    tags: list[str] = []
    # Optional location for the portfolio map (F4-2). Free text + optional
    # coordinates; stored in inputs_snapshot so no DB migration is needed.
    location: str | None = None
    lat: float | None = None
    lon: float | None = None


def _location_of(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Extract the optional location block persisted in inputs_snapshot."""
    return {
        "location": snapshot.get("location"),
        "lat": snapshot.get("lat"),
        "lon": snapshot.get("lon"),
    }


def _gestion_of(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Como lo lleva su agente (26-sep): la carpeta del activo en el VDR y las
    reglas para asignarle solo lo que llega (proveedor/NIF -> linea)."""
    return {"carpeta": snapshot.get("carpeta"), "reglas": snapshot.get("reglas") or [], "fuentes": snapshot.get("fuentes") or {}}


@router.post("")
def save_asset(
    body: SaveAssetBody, tenant: TenantContext = Depends(tenant_ctx)
) -> dict[str, Any]:
    overrides = body.overrides or {}
    results = _run_model(body.model_id, overrides)
    scenario = Scenario(
        id=new_scenario_id(),
        name=body.name,
        base_model=body.model_id,
        overrides=overrides,
        inputs_snapshot={
            "model_id": body.model_id,
            "overrides": overrides,
            # Persist location alongside the inputs (optional; map-only).
            "location": body.location,
            "lat": body.lat,
            "lon": body.lon,
        },
        results_snapshot=results,
        tags=body.tags or [],
        # Stamp the owning tenant so it is only ever listed/read/deleted by it.
        user_id=tenant.user_id,
        workspace_id=tenant.workspace_id,
    )
    _store().save(scenario)
    return {"id": scenario.id}


@router.get("")
def list_assets(
    lifecycle: str | None = None, tenant: TenantContext = Depends(tenant_ctx)
) -> dict[str, Any]:
    scenarios = _store().list(lifecycle=lifecycle, workspace_id=tenant.workspace_id)
    actuals = _actuals_store()
    return {
        "assets": [
            {
                "id": s.id,
                "name": s.name,
                "model_id": s.base_model,
                "created_at": s.created_at.isoformat(),
                "last_update": _last_update_iso(s, actuals),
                "kpis": s.results_snapshot.get("kpis", {}),
                "lifecycle": s.lifecycle,
                "commissioning_date": (
                    s.commissioning_date.isoformat() if s.commissioning_date else None
                ),
                "tracking_frequency": s.tracking_frequency,
                **_location_of(s.inputs_snapshot or {}),
                **_gestion_of(s.inputs_snapshot or {}),
            }
            for s in scenarios
        ]
    }


@router.get("/{asset_id}")
def get_asset(
    asset_id: str, tenant: TenantContext = Depends(tenant_ctx)
) -> dict[str, Any]:
    s = _store().get(asset_id, workspace_id=tenant.workspace_id)
    if s is None or s.is_deleted:
        raise HTTPException(status_code=404, detail=f"unknown asset: {asset_id}")
    return {
        "id": s.id,
        "name": s.name,
        "model_id": s.base_model,
        "lifecycle": s.lifecycle,
        "overrides": s.inputs_snapshot.get("overrides", s.overrides),
        "results_snapshot": s.results_snapshot,
        "created_at": s.created_at.isoformat(),
        "last_update": _last_update_iso(s, _actuals_store()),
        **_location_of(s.inputs_snapshot or {}),
        **_gestion_of(s.inputs_snapshot or {}),
    }


@router.delete("/{asset_id}")
def delete_asset(
    asset_id: str, tenant: TenantContext = Depends(tenant_ctx)
) -> dict[str, Any]:
    # A user must be able to delete their own asset, even after promotion to
    # operational (which sets is_canonical=True). force_delete clears the
    # canonical flag and soft-deletes, so this never 500s (FIX 1). Scoped to the
    # tenant's workspace: deleting another tenant's asset id is a silent no-op.
    _store().force_delete(asset_id, workspace_id=tenant.workspace_id)
    return {"ok": True}


class LifecycleBody(BaseModel):
    lifecycle: Literal["opportunity", "operational"]
    tracking_frequency: Literal["daily", "monthly", "quarterly"] | None = None
    commissioning_date: str | None = None  # ISO; si falta al promover, se usa ahora


def en_operacion_si_tiene_reales(store: Any, s: Any, periodos: list[str]) -> bool:  # noqa: ARG001
    """Si se anotan datos reales de una oportunidad, es que ya funciona (29-sep):
    la planta de prueba tenía producción real y la Cartera salía vacía porque
    seguía como oportunidad. Pasa a operación; la puesta en marcha es la del
    modelo (meta.start_date) o la de alta. Devuelve si ha cambiado."""
    if s is None or s.lifecycle == "operational":
        return False
    from asset_finance_modeler.web_api.actuals import _inicio_del_modelo  # noqa: PLC0415

    s.lifecycle = "operational"
    s.base_locked = True
    s.is_canonical = True
    s.tracking_frequency = s.tracking_frequency or "monthly"
    if s.commissioning_date is None:
        # La del modelo si la dice; si no, la de alta: así la comparación con
        # lo previsto no se mueve de año al pasar a operación.
        s.commissioning_date = _inicio_del_modelo(s) or s.created_at
    store.save(s)
    return True


@router.patch("/{asset_id}/lifecycle")
def set_lifecycle(
    asset_id: str, body: LifecycleBody, tenant: TenantContext = Depends(tenant_ctx)
) -> dict[str, Any]:
    store = _store()
    s = store.get(asset_id, workspace_id=tenant.workspace_id)
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
def portfolio(
    ids: str | None = None,
    lifecycle: str | None = None,
    tenant: TenantContext = Depends(tenant_ctx),
) -> dict[str, Any]:
    """Aggregate saved (non-deleted) assets by re-running each one fresh, so
    valuations reflect current inputs. Optional ?ids=id1,id2 limits the set.
    Assets that fail to run are reported in `skipped` (not silently dropped,
    not fatal) so a broken asset stays visible (FIX 4). Scoped to the tenant's
    workspace so a portfolio never aggregates another tenant's assets."""
    wanted: set[str] | None = None
    if ids:
        wanted = {i.strip() for i in ids.split(",") if i.strip()}

    assets: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    totals = {"npv": 0.0, "capex": 0.0, "revenue_y1": 0.0, "count": 0, "irr_weighted": 0.0}
    _irr_capex_sum = 0.0
    consolidado: dict[int, dict[str, float]] = {}
    ytd_total = {"real": 0.0, "prevision": 0.0}
    for s in _store().list(lifecycle=lifecycle, workspace_id=tenant.workspace_id):
        if wanted is not None and s.id not in wanted:
            continue
        snapshot = s.inputs_snapshot or {}
        model_id = snapshot.get("model_id", s.base_model)
        overrides = snapshot.get("overrides", s.overrides) or {}
        try:
            result = _run_model_cacheado(model_id, overrides)
            metrics = _normalize_run(result)
        except Exception as exc:  # noqa: BLE001 — surface failures, don't 500
            skipped.append(
                {"id": s.id, "name": s.name, "model_id": model_id, "error": str(exc)}
            )
            continue
        extra = _extra_de_cartera(s, result)
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
                **_location_of(snapshot),
                **extra,
            }
        )
        _sumar_consolidado(consolidado, extra)
        for k in ("enterprise_value", "valor_para_el_dueno", "deuda_viva", "caja", "ingresos_anio", "ebitda_anio"):
            if extra.get(k) is not None:
                totals[k] = totals.get(k, 0.0) + float(extra[k])
        if extra.get("ytd"):
            ytd_total["real"] += extra["ytd"]["real"]
            ytd_total["prevision"] += extra["ytd"]["prevision"]
        totals["npv"] += metrics["npv"]
        totals["capex"] += metrics["capex"]
        totals["revenue_y1"] += metrics["revenue_y1"]
        totals["count"] += 1
        _irr_capex_sum += metrics["irr"] * metrics["capex"]

    if totals["capex"]:
        totals["irr_weighted"] = round(_irr_capex_sum / totals["capex"], 4)

    if ytd_total["prevision"]:
        totals["cumplimiento_ytd_pct"] = round(ytd_total["real"] / ytd_total["prevision"] * 100, 1)
        totals["ytd"] = {k: round(v) for k, v in ytd_total.items()}
    anios = sorted(consolidado)
    serie = {"years": anios, **{k: [round(consolidado[a].get(k, 0.0)) for a in anios] for k in ("revenue", "ebitda", "net_income", "flujo_caja", "deuda")}}
    return {"assets": assets, "totals": totals, "skipped": skipped, "consolidado": serie}


def _anio_de_inicio(s: Scenario) -> int:
    from asset_finance_modeler.web_api.actuals import _model_start_year  # noqa: PLC0415

    return _model_start_year(s)


def _extra_de_cartera(s: Scenario, result: dict[str, Any]) -> dict[str, Any]:
    """Lo que el cuadro general necesita de cada activo (28-sep): tipo, fase,
    valor, deuda viva y caja de este año, sus series anuales (para su curva y
    la consolidada) y cómo va el año real frente a lo previsto."""
    inicio = _anio_de_inicio(s)
    hoy = datetime.now(UTC).year
    i = max(0, hoy - inicio)
    rows = (result.get("income_statement") or {}).get("rows") or {}
    cf = result.get("cash_flow") or {}
    deuda = result.get("deuda") or {}
    kp = result.get("kpis") or {}
    def en(serie: list[float] | None) -> float | None:
        return float(serie[i]) if serie and i < len(serie) and serie[i] is not None else None
    flujo = [((cf.get("cfo") or [0] * 99)[y] if y < len(cf.get("cfo") or []) else 0) + ((cf.get("cfi") or [])[y] if y < len(cf.get("cfi") or []) else 0) + ((cf.get("cff") or [])[y] if y < len(cf.get("cff") or []) else 0)
             for y in range(len(cf.get("cfo") or []))]
    extra: dict[str, Any] = {
        "tipo": _tipo_de_modelo(str(s.base_model if not (s.inputs_snapshot or {}).get("model_id") else s.inputs_snapshot["model_id"])),
        "lifecycle": getattr(s, "lifecycle", None),
        "anio_inicio": inicio,
        # El valor de verdad (el mismo que da «¿cuánto vale?»), no el VAN (28-sep).
        **_valor_de(s, result, en(deuda.get("saldo"))),
        "deuda_viva": en(deuda.get("saldo")),
        "caja": en(cf.get("cash")),
        "ingresos_anio": en(rows.get("revenue")),
        "ebitda_anio": en(rows.get("ebitda")),
        "series": {
            "revenue": rows.get("revenue") or [],
            "ebitda": rows.get("ebitda") or [],
            "net_income": rows.get("net_income") or [],
            "flujo_caja": [round(x) for x in flujo],
            "deuda": deuda.get("saldo") or [],
        },
    }
    # El año en curso, real frente a lo previsto hasta hoy (solo si hay datos reales).
    try:
        from asset_finance_modeler.web_api.actuals import _variance_for_line  # noqa: PLC0415

        reales = _actuals_store().list(scenario_id=s.id, line_path="income_statement.rows.revenue")
        if reales:
            v = _variance_for_line(s, reales, "income_statement.rows.revenue", "Ingresos", "")
            ac = v.get("anio_en_curso")
            if isinstance(ac, int) and v["actual"][ac] is not None and (v["base_comparada"][ac] or 0) > 0:
                extra["ytd"] = {"real": float(v["actual"][ac]), "prevision": float(v["base_comparada"][ac])}
    except Exception:  # noqa: BLE001 — la cartera no se cae por el seguimiento
        pass
    return extra


_CACHE_DE_VALOR: dict[str, dict[str, Any]] = {}


def _valor_de(s: Scenario, result: dict[str, Any], deuda_viva: float | None) -> dict[str, Any]:
    """Cuánto vale hoy el activo (flujos descontados, sin la inversión de
    partida) y lo que queda para el dueño tras su deuda. Guardado por resultado."""
    import json as _json  # noqa: PLC0415

    snapshot = s.inputs_snapshot or {}
    model_id = str(snapshot.get("model_id", s.base_model))
    overrides = snapshot.get("overrides", s.overrides) or {}
    clave = model_id + "|" + _json.dumps(overrides, sort_keys=True, default=str) + "|" + str(round(deuda_viva or 0))
    if clave in _CACHE_DE_VALOR:
        return _CACHE_DE_VALOR[clave]
    out: dict[str, Any] = {"enterprise_value": (result.get("kpis") or {}).get("enterprise_value")}
    try:
        from asset_finance_modeler.mcp_server.tools.assets import _por_defecto  # noqa: PLC0415
        from asset_finance_modeler.valoracion import valorar  # noqa: PLC0415

        tasa = _por_defecto(model_id, overrides, ("discount_rate_annual", "tasa_descuento"))
        g = _por_defecto(model_id, overrides, ("terminal_growth_rate",))
        v = valorar(result, model_id=model_id, tasa=float(tasa if tasa is not None else 0.08),
                    crecimiento=float(g if g is not None else 0.02), deuda_neta=float(deuda_viva or 0))
        out = {"enterprise_value": round(v["valor_empresa"]), "valor_para_el_dueno": round(v["valor_para_el_dueno"])}
    except Exception:  # noqa: BLE001 — sin valoración, el del modelo
        pass
    if len(_CACHE_DE_VALOR) >= 256:
        _CACHE_DE_VALOR.pop(next(iter(_CACHE_DE_VALOR)))
    _CACHE_DE_VALOR[clave] = out
    return out


def _sumar_consolidado(acc: dict[int, dict[str, float]], extra: dict[str, Any]) -> None:
    """Suma las series de un activo por AÑO NATURAL (cada uno empieza cuando empieza)."""
    inicio = int(extra.get("anio_inicio") or 0)
    for k, serie in (extra.get("series") or {}).items():
        for y, v in enumerate(serie or []):
            if v is None:
                continue
            fila = acc.setdefault(inicio + y, {})
            fila[k] = fila.get(k, 0.0) + float(v)


@router.get("/{asset_id}/valoracion")
def valoracion_del_activo(
    asset_id: str,
    tasa: float | None = None,
    crecimiento: float | None = None,
    multiplo_ebitda: float | None = None,
    deuda_neta: float | None = None,
    tenant: TenantContext = Depends(tenant_ctx),
) -> dict[str, Any]:
    """Cuánto vale hoy el activo (28-sep), para la ficha: el mismo cálculo que
    le pide el agente (finance.asset.value), con rango y la tabla tasa ×
    crecimiento. Solo dentro de su espacio."""
    from asset_finance_modeler.mcp_server.tools.assets import handle_value  # noqa: PLC0415
    from asset_finance_modeler.store.scenarios import en_espacio  # noqa: PLC0415

    args: dict[str, Any] = {"asset_id": asset_id, "workspace_id": tenant.workspace_id, "user_id": tenant.user_id}
    for k, v in (("tasa", tasa), ("crecimiento", crecimiento), ("multiplo_ebitda", multiplo_ebitda), ("deuda_neta", deuda_neta)):
        if v is not None:
            args[k] = v
    with en_espacio(tenant.workspace_id):
        try:
            r = handle_value(args)
        except (KeyError, LookupError) as exc:
            raise HTTPException(status_code=404, detail="asset not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if isinstance(r, dict) and r.get("error"):
        raise HTTPException(status_code=404 if "not" in str(r["error"]) else 400, detail=str(r["error"]))
    return r
