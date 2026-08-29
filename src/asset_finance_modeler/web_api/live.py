"""F3-2: GET /api/assets/{id}/live — base-vs-live valuation reprojection.

Loads the asset (Scenario), its frozen ``results_snapshot`` (the BASE) and its
stored actuals, aggregates the actuals to model years, computes how many model
years have elapsed since ``commissioning_date``, and calls ``compute_live`` to
splice the real past years over the base and revalue. Returns base + live
statements + a headline comparison for the frontend.

LIVE only applies to OPERATIONAL assets (an opportunity has no real operating
data to overlay) -> 422 otherwise. The base NPV in the ``comparison`` is the
asset's REAL stored engine NPV (``results_snapshot`` kpis ``npv``/``npv_hybrid``)
— ``compute_live`` is anchored to it so ``npv_base`` is the TRUE base for every
asset type regardless of footing, and ``npv_live`` is that stored base shifted
by the actuals-driven delta (computed on a consistent CFO+CFI footing for both
recomputed base and live). See ``core/live`` for the documented
overlay-by-aggregation simplifications.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from asset_finance_modeler.assets.business.loader import load_business_preset
from asset_finance_modeler.assets.infrastructure.loader import load_preset
from asset_finance_modeler.assets.saas.loader import load_preset as load_saas_preset
from asset_finance_modeler.core.live import compute_live
from asset_finance_modeler.core.scenario import Scenario, apply_overrides
from asset_finance_modeler.deals.hybrid_consolidated import _WACC
from asset_finance_modeler.store.actuals import Actual
from asset_finance_modeler.web_api.actuals import (
    _actuals_store,
    _model_start_year,
    _trackable_lines,
    _year_index,
)
from asset_finance_modeler.web_api.assets import _store
from asset_finance_modeler.web_api.auth import TenantContext, require_token, tenant_ctx
from asset_finance_modeler.web_api.models import _BUSINESS_IDS, _SAAS_IDS, _preset_ids

router = APIRouter(prefix="/api/assets", dependencies=[Depends(require_token)])


def _get_asset_or_404(asset_id: str, workspace_id: str | None = None) -> Scenario:
    # Tenant-scoped: LIVE reprojection only resolves an asset the caller's
    # workspace owns.
    s = _store().get(asset_id, workspace_id=workspace_id)
    if s is None or s.is_deleted:
        raise HTTPException(status_code=404, detail=f"unknown asset: {asset_id}")
    return s


def _resolve_valuation(asset: Scenario) -> tuple[float, float, str, str, float]:
    """Resolve (discount_rate, terminal_growth, terminal_method, npv_convention,
    residual_value) for an asset by re-resolving its base model config (the
    snapshot does not store the discount rate / terminal). ``residual_value`` is
    the base valuation's exit/terminal inflow at horizon end (e.g. a real-estate
    sale) so the LIVE recomputation can honour the SAME terminal as the base —
    otherwise the recomputed base NPV is spuriously negative for residual-backed
    assets. Falls back to a generic 8% / no-terminal / no-residual if the config
    cannot be resolved."""
    model_id = (asset.inputs_snapshot or {}).get("model_id") or asset.base_model
    overrides = (asset.inputs_snapshot or {}).get("overrides", asset.overrides) or {}

    # hybrid consolidated hybrid: consolidated unlevered NPV at the deal WACC (no terminal).
    if model_id == "hybrid_consolidated":
        wacc = float(overrides.get("wacc", _WACC))
        return wacc, 0.0, "none", "sum", 0.0

    try:
        if model_id in _BUSINESS_IDS:
            cfg = load_business_preset(model_id).model_dump()
        elif model_id in _SAAS_IDS:
            cfg = load_saas_preset(model_id[len("saas_"):]).model_dump()
        elif model_id in _preset_ids():
            cfg = load_preset(model_id).model_dump()
        else:
            return 0.08, 0.0, "none", "dcf", 0.0
        cfg = apply_overrides(cfg, overrides)
        val = cfg.get("valuation") or {}
        return (
            float(val.get("discount_rate_annual", 0.08)),
            float(val.get("terminal_growth_rate", 0.0) or 0.0),
            str(val.get("terminal_method", "none")),
            "dcf",
            float(val.get("residual_value", 0.0) or 0.0),
        )
    except Exception:  # noqa: BLE001 — conservative fallback, never 500 on this
        return 0.08, 0.0, "none", "dcf", 0.0


def _elapsed_years(asset: Scenario, n_years: int) -> int:
    """Whole model years elapsed since commissioning (clamped to [0, n_years])."""
    if asset.commissioning_date is None:
        return 0
    start = asset.commissioning_date
    now = datetime.now(start.tzinfo) if start.tzinfo else datetime.now()
    elapsed = now.year - start.year
    if (now.month, now.day) < (start.month, start.day):
        elapsed -= 1
    return max(0, min(elapsed, n_years))


def _aggregate_actuals(
    asset: Scenario, actuals: list[Actual], snapshot: dict[str, Any]
) -> dict[str, dict[int, float]]:
    """Aggregate (sum) actuals into {line_path: {year_index: value}} buckets,
    only for trackable lines and years inside the model horizon."""
    trackable = {ln["path"] for ln in _trackable_lines(snapshot)}
    rows = (snapshot.get("income_statement") or {}).get("rows") or {}
    cf = snapshot.get("cash_flow") or {}
    n = len(next(iter(rows.values()))) if rows else len(cf.get("cfo") or [])
    start_year = _model_start_year(asset)

    by_line: dict[str, dict[int, float]] = {}
    for a in actuals:
        if a.line_path not in trackable:
            continue
        idx = _year_index(a.period_start, start_year)
        if 0 <= idx < n:
            by_line.setdefault(a.line_path, {})
            by_line[a.line_path][idx] = by_line[a.line_path].get(idx, 0.0) + a.value
    return by_line


def _statements(series: dict[str, Any]) -> dict[str, Any]:
    return {
        "income_statement": series["income_statement"],
        "cash_flow": series["cash_flow"],
    }


@router.get("/{asset_id}/live")
def get_live(
    asset_id: str, tenant: TenantContext = Depends(tenant_ctx)
) -> dict[str, Any]:
    asset = _get_asset_or_404(asset_id, workspace_id=tenant.workspace_id)
    if asset.lifecycle != "operational":
        raise HTTPException(
            status_code=422,
            detail=(
                "LIVE reprojection only applies to assets in operation "
                "(operational). Promote the asset to operational first."
            ),
        )

    snapshot = asset.results_snapshot or {}
    rows = (snapshot.get("income_statement") or {}).get("rows") or {}
    cf = snapshot.get("cash_flow") or {}
    n_years = len(next(iter(rows.values()))) if rows else len(cf.get("cfo") or [])
    if n_years == 0:
        raise HTTPException(
            status_code=422,
            detail="asset snapshot has no annual statements to reproject",
        )

    (
        discount_rate,
        terminal_growth,
        terminal_method,
        convention,
        residual_value,
    ) = _resolve_valuation(asset)
    elapsed = _elapsed_years(asset, n_years)
    actuals = _actuals_store().list(scenario_id=asset_id)
    by_line = _aggregate_actuals(asset, actuals, snapshot)

    # The REAL stored engine NPV (unlevered NOPAT FCF for business/real-estate,
    # consolidated unlevered for hybrid_consolidated). The base-vs-live panel anchors to
    # this so ``npv_base`` is the TRUE base for every asset type; live is the
    # stored base shifted by the actuals-driven delta. ``None`` (no stored NPV)
    # falls back to the CFO+CFI recompute inside ``compute_live``.
    stored_kpis = snapshot.get("kpis") or {}
    stored_base_npv = stored_kpis.get("npv", stored_kpis.get("npv_hybrid"))
    stored_base_npv = (
        float(stored_base_npv) if stored_base_npv is not None else None
    )

    result = compute_live(
        base_output=snapshot,
        actuals_by_line_by_year=by_line,
        elapsed_years=elapsed,
        discount_rate=discount_rate,
        terminal_growth=terminal_growth,
        terminal_method=terminal_method,
        npv_convention=convention,  # type: ignore[arg-type]
        residual_value=residual_value,
        stored_base_npv=stored_base_npv,
    )

    base_kpis = result["base"]["kpis"]
    live_kpis = result["live"]["kpis"]
    base_stmts = _statements(result["base"]["series"])
    live_stmts = _statements(result["live"]["series"])

    comparison = {
        "npv_base": base_kpis["npv"],
        "npv_live": live_kpis["npv"],
        "delta": live_kpis["npv"] - base_kpis["npv"],
        "irr_base": base_kpis["irr_project"],
        "irr_live": live_kpis["irr_project"],
        "dscr_min_base": base_kpis["dscr_min"],
        "dscr_min_live": live_kpis["dscr_min"],
        "elapsed_years": elapsed,
        "n_years": n_years,
    }

    return {
        "base": {
            "kpis": base_kpis,
            "income_statement": base_stmts["income_statement"],
            "cash_flow": base_stmts["cash_flow"],
        },
        "live": {
            "kpis": live_kpis,
            "income_statement": live_stmts["income_statement"],
            "cash_flow": live_stmts["cash_flow"],
        },
        "comparison": comparison,
    }
