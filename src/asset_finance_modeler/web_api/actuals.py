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
from pydantic import BaseModel

from asset_finance_modeler.core.scenario import Scenario
from asset_finance_modeler.store.actuals import Actual, SQLiteActualsStore
from asset_finance_modeler.web_api.assets import _db_path, _store
from asset_finance_modeler.web_api.auth import require_token

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


def _get_asset_or_404(asset_id: str) -> Scenario:
    s = _store().get(asset_id)
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
    return None


def _model_start_year(asset: Scenario) -> int:
    """The calendar year that maps to model year index 0. Prefers the
    commissioning_date; falls back to the asset's created_at year."""
    if asset.commissioning_date is not None:
        return asset.commissioning_date.year
    return asset.created_at.year


def _year_index(period_start: str, start_year: int) -> int:
    """Map an actual's period_start (ISO date) to a 0-based model year index."""
    try:
        dt = datetime.fromisoformat(period_start)
    except ValueError:
        # Bare year or unparsable -> try the leading 4 chars.
        dt = datetime(int(period_start[:4]), 1, 1)
    return dt.year - start_year


router = APIRouter(prefix="/api/assets", dependencies=[Depends(require_token)])


class ActualInput(BaseModel):
    period_start: str
    line_path: str
    value: float
    unit: str = ""
    note: str = ""


class PostActualsBody(BaseModel):
    actuals: list[ActualInput]


@router.get("/{asset_id}/lines")
def get_lines(asset_id: str) -> dict[str, Any]:
    asset = _get_asset_or_404(asset_id)
    return {"lines": _trackable_lines(asset.results_snapshot)}


@router.post("/{asset_id}/actuals")
def post_actuals(asset_id: str, body: PostActualsBody) -> dict[str, Any]:
    _get_asset_or_404(asset_id)
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
    return {"ids": ids}


@router.get("/{asset_id}/actuals")
def list_actuals(
    asset_id: str,
    line_path: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> dict[str, Any]:
    _get_asset_or_404(asset_id)
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
def delete_actual(asset_id: str, actual_id: str) -> dict[str, Any]:
    _get_asset_or_404(asset_id)
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
    deviation: list[float | None] = []
    deviation_pct: list[float | None] = []
    for y in range(n):
        av = actual[y]
        if av is None:
            deviation.append(None)
            deviation_pct.append(None)
        else:
            bv = base[y]
            deviation.append(round(av - bv, 4))
            deviation_pct.append(round((av - bv) / bv, 4) if bv else None)

    # Cumulative + fulfillment use only the years that actually have data, so a
    # partially-filled series is not penalised against the full base horizon.
    years_with_data = [y for y in range(n) if actual[y] is not None]
    cumulative_actual = round(sum(actual[y] for y in years_with_data), 4)  # type: ignore[misc]
    cumulative_base = round(sum(base[y] for y in years_with_data), 4)
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
    }


@router.get("/{asset_id}/variance")
def get_variance(asset_id: str, line_path: str | None = None) -> dict[str, Any]:
    asset = _get_asset_or_404(asset_id)
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
