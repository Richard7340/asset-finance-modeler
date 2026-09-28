"""Real (actual) operating data + variance for an asset in operation (F2).

Endpoints (all under /api/assets, token-gated):
  GET    /{id}/lines      -> trackable model lines (from the frozen snapshot)
  POST   /{id}/actuals    -> store one or a batch of actuals
  GET    /{id}/actuals    -> list actuals (optional line_path/since/until)
  DELETE /{id}/actuals/{actual_id}
  GET    /{id}/variance   -> base vs actual per line (F2-3)

No valuation reprojection here (that is F3). The base series is the frozen
``results_snapshot`` of the asset; actuals are aggregated by model year.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from asset_finance_modeler.core.scenario import Scenario
from asset_finance_modeler.store.actuals import Actual, SQLiteActualsStore
from asset_finance_modeler.web_api.assets import _db_path, _store
from asset_finance_modeler.web_api.auth import TenantContext, require_token, tenant_ctx

# Human labels + default unit per trackable line key. Units are the model's
# native magnitudes (monetary for P&L/CF). Currency is left generic ("") since
# the engine works in whichever currency the preset is denominated in.
_IS_ROW_LABELS: dict[str, str] = {
    "revenue": "Ingresos",
    "ebitda": "EBITDA",
    "ebit": "EBIT",
    "interest_expense": "Gastos financieros",
    "ebt": "BAI",
    "tax": "Impuestos",
    "net_income": "Beneficio neto",
}
_CF_LABELS: dict[str, str] = {
    "cfo": "Flujo de operaciones",
    "cfi": "Flujo de inversión",
    "cff": "Flujo de financiación",
}


def _actuals_store() -> SQLiteActualsStore:
    store = SQLiteActualsStore(_db_path())
    store.initialize()
    return store


def _get_asset_or_404(asset_id: str, workspace_id: str | None = None) -> Scenario:
    # Scoped to the tenant's workspace so actuals for an asset can only be read
    # or written by the tenant that owns the parent asset. Actuals are child rows
    # of a scenario (no tenant column of their own); gating the parent lookup is
    # the isolation boundary for the whole actuals/variance surface.
    s = _store().get(asset_id, workspace_id=workspace_id)
    if s is None or s.is_deleted:
        raise HTTPException(status_code=404, detail=f"unknown asset: {asset_id}")
    return s


def _trackable_lines(snapshot: dict[str, Any]) -> list[dict[str, str]]:
    """Derive the trackable model lines from a frozen ``results_snapshot``.

    Handles both the generic payload and the svj_hybrid payload (which since
    P3-2 also carries ``income_statement``/``cash_flow``). A line is only listed
    if its series is actually present in the snapshot.
    """
    lines: list[dict[str, str]] = []
    income = snapshot.get("income_statement") or {}
    rows = income.get("rows") or {}
    for key in ("revenue", "ebitda", "ebit", "interest_expense", "ebt", "tax", "net_income"):
        if key in rows:
            lines.append(
                {
                    "path": f"income_statement.rows.{key}",
                    "label": _IS_ROW_LABELS.get(key, key),
                    "unit": "",
                }
            )
    # Modelo SaaS: el snapshot guarda "pnl" (series MENSUALES) y "cashflow".
    # Se exponen como pnl.<linea> para importar actuals contra ellas.
    pnl = snapshot.get("pnl") or {}
    for key in ("revenue", "cogs", "gross_profit", "opex", "ebitda", "ebit", "tax", "net_income"):
        if key in pnl:
            lines.append(
                {
                    "path": f"pnl.{key}",
                    "label": _IS_ROW_LABELS.get(key, key),
                    "unit": "",
                }
            )
    # Cada ingreso y gasto por separado (IBI, comunidad, O&M, PPA…).
    for grupo, prefijo, unidad in (("ingresos", "Ingreso", ""), ("gastos", "Gasto", ""), ("produccion", "Producción", "MWh")):
        for nombre in ((snapshot.get("lineas") or {}).get(grupo) or {}):
            lines.append({"path": f"lineas.{grupo}.{nombre}", "label": f"{prefijo}: {nombre}" if nombre != prefijo else prefijo, "unit": unidad})
    cash_flow = snapshot.get("cash_flow") or {}
    for key in ("cfo", "cfi", "cff"):
        if key in cash_flow:
            lines.append(
                {
                    "path": f"cash_flow.{key}",
                    "label": _CF_LABELS.get(key, key),
                    "unit": "",
                }
            )
    return lines


def _annualize(series: list[float]) -> list[float]:
    """Agrega a años naturales: las series SaaS son mensuales y el motor de
    varianza trabaja por año de modelo. Si no es múltiplo de 12 se devuelve
    tal cual (ya anual u otro grano)."""
    if len(series) > 12 and len(series) % 12 == 0:
        return [round(sum(series[y * 12:(y + 1) * 12]), 4) for y in range(len(series) // 12)]
    return list(series)


def _base_series(snapshot: dict[str, Any], line_path: str) -> list[float] | None:
    """Return the annual base series for a trackable line_path, or None."""
    if line_path.startswith("income_statement.rows."):
        key = line_path.split("income_statement.rows.", 1)[1]
        rows = (snapshot.get("income_statement") or {}).get("rows") or {}
        series = rows.get(key)
        return list(series) if series is not None else None
    if line_path.startswith("cash_flow."):
        key = line_path.split("cash_flow.", 1)[1]
        series = (snapshot.get("cash_flow") or {}).get(key)
        return list(series) if series is not None else None
    if line_path.startswith("pnl."):
        key = line_path.split("pnl.", 1)[1]
        series = (snapshot.get("pnl") or {}).get(key)
        return _annualize(list(series)) if series is not None else None
    if line_path.startswith("lineas."):
        _, grupo, nombre = line_path.split(".", 2)
        series = ((snapshot.get("lineas") or {}).get(grupo) or {}).get(nombre)
        return list(series) if series is not None else None
    if line_path.startswith("cashflow."):
        key = line_path.split("cashflow.", 1)[1]
        series = (snapshot.get("cashflow") or {}).get(key)
        return _annualize(list(series)) if series is not None else None
    return None


def _hoy() -> datetime:
    """Hoy (aparte, para poder fijarlo en las pruebas)."""
    return datetime.now()


def _inicio_del_modelo(asset: Scenario) -> "datetime | None":
    ov = (asset.inputs_snapshot or {}).get("overrides") or asset.overrides or {}
    v = ov.get("meta.start_date")
    try:
        return datetime.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def _model_start_year(asset: Scenario) -> int:
    """The calendar year that maps to model year index 0. Prefers the
    commissioning_date; falls back to the asset's created_at year.

    Si el modelo dice cuando empieza (meta.start_date), manda eso: su año 1
    es ese año (29-sep: una planta de 2025 se comparaba como si fuera de 2026)."""
    inicio = _inicio_del_modelo(asset)
    if inicio is not None:
        return inicio.year
    if asset.commissioning_date is not None:
        return asset.commissioning_date.year
    return asset.created_at.year


# Sentinel year index for a malformed period_start: far outside any model
# horizon so the ``0 <= idx < n`` guard at every call site silently drops it
# (defence in depth — the Pydantic boundary already rejects bad dates on POST,
# but a legacy / direct-written row must never 500 /variance or /live).
_BAD_YEAR_INDEX = -(10**9)


def _year_index(period_start: str, start_year: int) -> int:
    """Map an actual's period_start (ISO date) to a 0-based model year index.

    Defensive: a non-parsable period_start returns ``_BAD_YEAR_INDEX`` (dropped
    by the ``0 <= idx < n`` guard) rather than raising."""
    try:
        dt = datetime.fromisoformat(period_start)
    except (ValueError, TypeError):
        # Bare year ("2026") -> try the leading 4 chars; otherwise drop.
        try:
            dt = datetime(int(period_start[:4]), 1, 1)
        except (ValueError, TypeError):
            return _BAD_YEAR_INDEX
    return dt.year - start_year


router = APIRouter(prefix="/api/assets", dependencies=[Depends(require_token)])


class ActualInput(BaseModel):
    period_start: str
    line_path: str
    value: float
    unit: str = ""
    note: str = ""

    @field_validator("period_start")
    @classmethod
    def _period_start_is_iso(cls, v: str) -> str:
        """Reject a non-ISO period_start at the boundary (-> 422) so it is never
        stored and later 500s /variance and /live (L3)."""
        try:
            datetime.fromisoformat(v)
        except (ValueError, TypeError):
            raise ValueError(
                "period_start must be an ISO date/datetime, e.g. '2026-01-01'"
            )
        return v


class PostActualsBody(BaseModel):
    actuals: list[ActualInput]


@router.get("/{asset_id}/lines")
def get_lines(
    asset_id: str, tenant: TenantContext = Depends(tenant_ctx)
) -> dict[str, Any]:
    asset = _get_asset_or_404(asset_id, workspace_id=tenant.workspace_id)
    return {"lines": _trackable_lines(asset.results_snapshot)}


@router.post("/{asset_id}/actuals")
def post_actuals(
    asset_id: str, body: PostActualsBody, tenant: TenantContext = Depends(tenant_ctx)
) -> dict[str, Any]:
    asset = _get_asset_or_404(asset_id, workspace_id=tenant.workspace_id)
    items = [
        Actual(
            scenario_id=asset_id,
            period_start=a.period_start,
            line_path=a.line_path,
            value=a.value,
            unit=a.unit,
            note=a.note,
        )
        for a in body.actuals
    ]
    ids = _actuals_store().add_batch(items)
    from asset_finance_modeler.web_api.assets import _store, en_operacion_si_tiene_reales  # noqa: PLC0415

    paso = en_operacion_si_tiene_reales(_store(), asset, [a.period_start for a in body.actuals])
    return {"ids": ids, **({"pasado_a_operacion": True} if paso else {})}


@router.get("/{asset_id}/actuals")
def list_actuals(
    asset_id: str,
    line_path: str | None = None,
    since: str | None = None,
    until: str | None = None,
    tenant: TenantContext = Depends(tenant_ctx),
) -> dict[str, Any]:
    _get_asset_or_404(asset_id, workspace_id=tenant.workspace_id)
    rows = _actuals_store().list(
        scenario_id=asset_id, line_path=line_path, since=since, until=until
    )
    return {
        "actuals": [
            {
                "id": r.id,
                "period_start": r.period_start,
                "line_path": r.line_path,
                "value": r.value,
                "unit": r.unit,
                "note": r.note,
                "entered_by": r.entered_by,
                "entered_at": r.entered_at,
            }
            for r in rows
        ]
    }


@router.delete("/{asset_id}/actuals/{actual_id}")
def delete_actual(
    asset_id: str, actual_id: str, tenant: TenantContext = Depends(tenant_ctx)
) -> dict[str, Any]:
    _get_asset_or_404(asset_id, workspace_id=tenant.workspace_id)
    _actuals_store().delete(actual_id)
    return {"ok": True}


def _variance_for_line(
    asset: Scenario,
    actuals: list[Actual],
    line_path: str,
    label: str,
    unit: str,
) -> dict[str, Any]:
    """Compare the frozen annual base series against actuals aggregated by
    model year. Years without any actual stay ``None`` (not invented).
    No valuation reprojection (that is F3)."""
    base = _base_series(asset.results_snapshot, line_path) or []
    n = len(base)
    start_year = _model_start_year(asset)

    # Aggregate actuals (sum) into the model year buckets they fall in.
    agg: dict[int, float] = {}
    for a in actuals:
        if a.line_path != line_path:
            continue
        idx = _year_index(a.period_start, start_year)
        if 0 <= idx < n:
            agg[idx] = agg.get(idx, 0.0) + a.value

    actual: list[float | None] = [agg.get(y) for y in range(n)]
    # El año EN CURSO se compara con su previsión HASTA HOY (lineal), no con el
    # año entero: con tres meses de datos no hay "un 75 % por debajo" (26-sep).
    hoy = _hoy()
    en_curso = hoy.year - start_year
    fraccion = round(((hoy - datetime(hoy.year, 1, 1)).days + 1) / (366 if hoy.year % 4 == 0 else 365), 4)
    comparada: list[float | None] = [None] * n
    deviation: list[float | None] = []
    deviation_pct: list[float | None] = []
    for y in range(n):
        av = actual[y]
        if av is None:
            deviation.append(None)
            deviation_pct.append(None)
        else:
            bv = base[y] * fraccion if y == en_curso else base[y]
            comparada[y] = round(bv, 4)
            deviation.append(round(av - bv, 4))
            deviation_pct.append(round((av - bv) / bv, 4) if bv else None)
    # Mes a mes del año en curso: lo real frente a la previsión mensual (lineal).
    mensual: list[dict[str, Any]] | None = None
    if 0 <= en_curso < n:
        por_mes: dict[int, float] = {}
        for a in actuals:
            if a.line_path != line_path:
                continue
            try:
                dt = datetime.fromisoformat(a.period_start)
            except (ValueError, TypeError):
                continue
            if dt.year == hoy.year:
                por_mes[dt.month] = por_mes.get(dt.month, 0.0) + a.value
        mensual = [{"mes": m, "real": round(por_mes[m], 4) if m in por_mes else None, "prevision": round(base[en_curso] / 12, 4)} for m in range(1, 13)]

    # Cumulative + fulfillment use only the years that actually have data, so a
    # partially-filled series is not penalised against the full base horizon.
    years_with_data = [y for y in range(n) if actual[y] is not None]
    cumulative_actual = round(sum(actual[y] for y in years_with_data), 4)  # type: ignore[misc]
    cumulative_base = round(sum(comparada[y] or 0.0 for y in years_with_data), 4)
    fulfillment_pct: float | None = (
        round(cumulative_actual / cumulative_base, 4)
        if years_with_data and cumulative_base
        else None
    )

    return {
        "line_path": line_path,
        "label": label,
        "unit": unit,
        "base": base,
        "actual": actual,
        "deviation": deviation,
        "deviation_pct": deviation_pct,
        "cumulative_actual": cumulative_actual,
        "cumulative_base": cumulative_base,
        "fulfillment_pct": fulfillment_pct,
        # La previsión con la que se compara cada año (el en curso, hasta hoy).
        "base_comparada": comparada,
        "anio_en_curso": en_curso if 0 <= en_curso < n else None,
        "fraccion_del_anio": fraccion,
        "mensual": mensual,
    }


@router.get("/{asset_id}/variance")
def get_variance(
    asset_id: str,
    line_path: str | None = None,
    tenant: TenantContext = Depends(tenant_ctx),
) -> dict[str, Any]:
    asset = _get_asset_or_404(asset_id, workspace_id=tenant.workspace_id)
    all_lines = _trackable_lines(asset.results_snapshot)
    if line_path is not None:
        all_lines = [ln for ln in all_lines if ln["path"] == line_path]
        if not all_lines:
            raise HTTPException(
                status_code=404, detail=f"untrackable line: {line_path}"
            )
    actuals = _actuals_store().list(scenario_id=asset_id, line_path=line_path)
    return {
        "lines": [
            _variance_for_line(asset, actuals, ln["path"], ln["label"], ln["unit"])
            for ln in all_lines
        ]
    }


# ── Real frente a previsto con la frecuencia que se quiera (28-sep) ─────────
# Cada uno anota lo real como le viene (a diario, por semanas, por meses…) y
# lo ve igual: la previsión anual del modelo se reparte por días, así que un
# día, una semana o un mes tienen su parte (sin estacionalidad todavía).

_CADAS = ("dia", "semana", "mes", "anio")
_MAX_PUNTOS = {"dia": 400, "semana": 260, "mes": 360, "anio": 60}


def _inicio_de(d: "date", cada: str) -> "date":
    from datetime import date, timedelta  # noqa: PLC0415

    if cada == "dia":
        return d
    if cada == "semana":
        return d - timedelta(days=d.weekday())
    if cada == "mes":
        return date(d.year, d.month, 1)
    return date(d.year, 1, 1)


def _siguiente(d: "date", cada: str) -> "date":
    from datetime import date, timedelta  # noqa: PLC0415

    if cada == "dia":
        return d + timedelta(days=1)
    if cada == "semana":
        return d + timedelta(days=7)
    if cada == "mes":
        return date(d.year + (d.month == 12), 1 if d.month == 12 else d.month + 1, 1)
    return date(d.year + 1, 1, 1)


def _etiqueta(d: "date", cada: str) -> str:
    meses = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
    if cada == "dia":
        return f"{d.day} {meses[d.month - 1]}"
    if cada == "semana":
        return f"sem. {d.isocalendar()[1]} · {d.day} {meses[d.month - 1]}"
    if cada == "mes":
        return f"{meses[d.month - 1]} {d.year}"
    return str(d.year)


def pesos_mensuales(asset: Scenario, line_path: str) -> tuple[list[float], str]:
    """Cómo se reparte el año entre los meses para esta línea (28-sep):
    la estacionalidad que puso el usuario (para esa línea o para todas), el
    perfil mensual del modelo (renovables), el típico de la solar en España,
    o igual todos los meses."""
    snap = asset.inputs_snapshot or {}
    est = snap.get("estacionalidad") or {}
    nombre = line_path.split(".")[-1]
    for k in (line_path, nombre, "*"):
        v = est.get(k) if isinstance(est, dict) else None
        if isinstance(v, list) and len(v) == 12 and sum(v) > 0:
            return [float(x) for x in v], "la tuya"
    ov = snap.get("overrides") or asset.overrides or {}
    produce = "produccion" in line_path or line_path.endswith((".revenue", "Producción")) or line_path.startswith("lineas.ingresos")
    for k in ("production.irradiation_profile", "production.production_profile"):
        v = ov.get(k)
        if produce and isinstance(v, list) and len(v) == 12 and sum(v) > 0:
            return [float(x) for x in v], "el perfil de producción del activo"
    if produce and str(asset.base_model).startswith(("solar", "svj_fv")):
        from asset_finance_modeler.mcp_server.tools.assets import PERFIL_SOLAR_ES  # noqa: PLC0415

        return list(PERFIL_SOLAR_ES), "la típica de la solar en España"
    return [1.0] * 12, "igual todos los meses"


def serie_real_vs_prevision(asset: Scenario, actuals: list[Actual], line_path: str, cada: str,
                            desde: str | None = None, hasta: str | None = None) -> dict[str, Any]:
    from datetime import date  # noqa: PLC0415

    base = _base_series(asset.results_snapshot, line_path) or []
    inicio_modelo = _model_start_year(asset)
    hoy = _hoy().date()
    try:
        d0 = date.fromisoformat(desde) if desde else None
    except ValueError:
        d0 = None
    try:
        d1 = date.fromisoformat(hasta) if hasta else hoy
    except ValueError:
        d1 = hoy
    fechas_reales = []
    for a in actuals:
        if a.line_path != line_path:
            continue
        try:
            fechas_reales.append(date.fromisoformat(str(a.period_start)[:10]))
        except ValueError:
            continue
    if d0 is None:
        d0 = min(fechas_reales) if fechas_reales else date(inicio_modelo, 1, 1)
        # Por defecto, no más atrás de lo que cabe en la gráfica.
        atras = {"dia": 90, "semana": 7 * 26, "mes": 365 * 2, "anio": 365 * 30}[cada]
        d0 = max(d0, date.fromordinal(max(1, d1.toordinal() - atras)))
    d0 = _inicio_de(d0, cada)

    pesos, origen_pesos = pesos_mensuales(asset, line_path)
    total_pesos = sum(pesos)

    def prevision_del_dia(d: "date") -> float:
        import calendar  # noqa: PLC0415

        y = d.year - inicio_modelo
        if y < 0 or y >= len(base):
            return 0.0
        # La parte del año que toca a ese mes (estacionalidad), repartida por sus días.
        return float(base[y]) * pesos[d.month - 1] / total_pesos / calendar.monthrange(d.year, d.month)[1]

    real_por_dia: dict["date", float] = {}
    for a in actuals:
        if a.line_path != line_path:
            continue
        try:
            f = date.fromisoformat(str(a.period_start)[:10])
        except ValueError:
            continue
        real_por_dia[f] = real_por_dia.get(f, 0.0) + float(a.value)

    puntos: list[dict[str, Any]] = []
    acc_r = acc_p = 0.0
    cur = d0
    while cur <= d1 and len(puntos) < _MAX_PUNTOS[cada]:
        fin = _siguiente(cur, cada)
        prev = 0.0
        dd = cur
        from datetime import timedelta  # noqa: PLC0415
        while dd < fin and dd <= d1:
            prev += prevision_del_dia(dd)
            dd += timedelta(days=1)
        reales = [v for f, v in real_por_dia.items() if cur <= f < fin]
        real = round(sum(reales), 2) if reales else None
        acc_p += prev
        if real is not None:
            acc_r += real
        puntos.append({
            "desde": cur.isoformat(), "etiqueta": _etiqueta(cur, cada),
            "real": real, "prevision": round(prev, 2),
            "acumulado_real": round(acc_r, 2), "acumulado_prevision": round(acc_p, 2),
            "desviacion_pct": round((real - prev) / prev * 100, 1) if real is not None and prev else None,
        })
        cur = fin
    con_dato = [p for p in puntos if p["real"] is not None]
    prev_con_dato = sum(p["prevision"] for p in con_dato)
    return {
        "line_path": line_path, "cada": cada, "desde": d0.isoformat(), "hasta": d1.isoformat(),
        "estacionalidad": origen_pesos,
        "puntos": puntos,
        "resumen": {
            "real": round(sum(p["real"] for p in con_dato), 2) if con_dato else None,
            "prevision_de_esos_periodos": round(prev_con_dato, 2),
            "cumplimiento_pct": round(sum(p["real"] for p in con_dato) / prev_con_dato * 100, 1) if con_dato and prev_con_dato else None,
            "periodos_con_dato": len(con_dato),
        },
    }


@router.get("/{asset_id}/serie")
def get_serie(
    asset_id: str,
    line_path: str,
    cada: str = "mes",
    desde: str | None = None,
    hasta: str | None = None,
    tenant: TenantContext = Depends(tenant_ctx),
) -> dict[str, Any]:
    if cada not in _CADAS:
        raise HTTPException(status_code=400, detail=f"cada: {', '.join(_CADAS)}")
    asset = _get_asset_or_404(asset_id, workspace_id=tenant.workspace_id)
    if not any(ln["path"] == line_path for ln in _trackable_lines(asset.results_snapshot)):
        raise HTTPException(status_code=404, detail=f"untrackable line: {line_path}")
    actuals = _actuals_store().list(scenario_id=asset_id, line_path=line_path)
    return serie_real_vs_prevision(asset, actuals, line_path, cada, desde, hasta)
