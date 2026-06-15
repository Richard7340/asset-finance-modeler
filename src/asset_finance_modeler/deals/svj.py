"""SVJ hybrid deal — single source of truth.

Builds and runs the validated SVJ deal (FV + BESS in Cordoba, with senior +
subordinated debt) and shapes its output for the web API. PROJECT NPV is
UNLEVERED (each asset run with no leverage, FCF discounted at the WACC);
investor metrics (DSCR / MOIC / recovery) come from the consolidated
HybridProject with the real capital stack.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from asset_finance_modeler.assets.hybrid.model import HybridProject, TrancheSpec
from asset_finance_modeler.assets.infrastructure.loader import load_preset
from asset_finance_modeler.assets.infrastructure.model import InfrastructureModel
from asset_finance_modeler.assets.infrastructure.schema import (
    InfrastructureModelConfig,
)
from asset_finance_modeler.assets.saas.model import ModelResults
from asset_finance_modeler.core.curves import Curve
from asset_finance_modeler.core.financing import compute_waterfall_dscr
from asset_finance_modeler.core.portfolio import consolidate_npv
from asset_finance_modeler.core.protocols import FinancialOutput
from asset_finance_modeler.store.exports import to_xlsx
from asset_finance_modeler.web_api.introspect import schema_tree, set_by_path

# Validated deal conventions.
_WACC = 0.0537
_PPY = 12  # monthly presets
_HORIZON_YEARS = 30

# Default capital stack (principal, interest_rate, tenor_years).
_SENIOR_DEFAULTS = {"principal": 2_220_000.0, "interest_rate": 0.032, "tenor_years": 10}
_SUB_DEFAULTS = {"principal": 1_841_000.0, "interest_rate": 0.085, "tenor_years": 7}

# Backward-compat: the 6 original drivers and where they really live.
_LEGACY_KEYS = frozenset(
    {
        "fv_ppa_price",
        "spread_capture",
        "ancillary_base",
        "bess_capex_eur_kwh",
        "sub_rate",
        "sub_tenor_years",
    }
)


def svj_input_spec() -> list[dict[str, Any]]:
    """Full editable input tree: FV + BESS preset trees + debt/valuation.

    Each FV/BESS leaf is prefixed (``fv.`` / ``bess.``) so overrides can be
    routed to the right asset; debt/valuation leaves expose the consolidated
    capital stack and the hybrid WACC.
    """
    fv_leaves = [
        {**leaf, "path": "fv." + leaf["path"], "section": "FV · " + leaf["section"]}
        for leaf in schema_tree(load_preset("svj_fv_cordoba").model_dump())
    ]
    bess_leaves = [
        {**leaf, "path": "bess." + leaf["path"], "section": "BESS · " + leaf["section"]}
        for leaf in schema_tree(load_preset("svj_bess_cordoba").model_dump())
    ]
    sec = "Deuda / Valoración"

    def _debt_leaf(path: str, value: float) -> dict[str, Any]:
        return {
            "path": path,
            "value": value,
            "type": "number",
            "section": sec,
            "label": path.rsplit(".", 1)[-1].replace("_", " "),
        }

    debt_leaves = [
        _debt_leaf("senior.principal", _SENIOR_DEFAULTS["principal"]),
        _debt_leaf("senior.interest_rate", _SENIOR_DEFAULTS["interest_rate"]),
        _debt_leaf("senior.tenor_years", float(_SENIOR_DEFAULTS["tenor_years"])),
        _debt_leaf("subordinated.principal", _SUB_DEFAULTS["principal"]),
        _debt_leaf("subordinated.interest_rate", _SUB_DEFAULTS["interest_rate"]),
        _debt_leaf("subordinated.tenor_years", float(_SUB_DEFAULTS["tenor_years"])),
        _debt_leaf("wacc", _WACC),
    ]
    return fv_leaves + bess_leaves + debt_leaves


def _annual(series: list[float]) -> list[float]:
    """Aggregate a monthly series into annual buckets."""
    return [sum(series[y * _PPY : (y + 1) * _PPY]) for y in range(len(series) // _PPY)]


def _apply_legacy(
    overrides: dict[str, Any],
    fv: dict[str, Any],
    bess: dict[str, Any],
    senior: dict[str, Any],
    subordinated: dict[str, Any],
) -> None:
    """Map the 6 original drivers onto their real targets (mutates in place)."""
    if "fv_ppa_price" in overrides:
        for stream in fv["revenue"]:
            if stream.get("type") == "ppa":
                stream["price_eur_per_unit"] = float(overrides["fv_ppa_price"])

    if "spread_capture" in overrides:
        for stream in bess["revenue"]:
            if stream.get("type") == "arbitrage":
                stream["spread_capture_ratio"] = float(overrides["spread_capture"])

    if "ancillary_base" in overrides:
        for stream in bess["revenue"]:
            if stream.get("type") == "ancillary":
                stream["afrr_eur_mw_yr"] = float(overrides["ancillary_base"])

    if "bess_capex_eur_kwh" in overrides:
        for item in bess["capex"]["items"]:
            if item.get("unit") == "kWh":
                item["amount_per_unit"] = float(overrides["bess_capex_eur_kwh"])

    if "sub_rate" in overrides:
        subordinated["interest_rate"] = float(overrides["sub_rate"])
    if "sub_tenor_years" in overrides:
        subordinated["tenor_years"] = int(overrides["sub_tenor_years"])


def _build_deal(
    overrides: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], float]:
    """Load both presets + default capital stack, apply legacy drivers AND any
    path-addressed override (``fv.*`` / ``bess.*`` / ``senior.*`` /
    ``subordinated.*`` / ``wacc``). Returns (fv, bess, senior, sub, wacc)."""
    fv = load_preset("svj_fv_cordoba").model_dump()
    bess = load_preset("svj_bess_cordoba").model_dump()
    senior = dict(_SENIOR_DEFAULTS)
    subordinated = dict(_SUB_DEFAULTS)
    wacc = _WACC

    # 1) Backward-compat: the 6 legacy drivers (so old saved overrides run).
    _apply_legacy(overrides, fv, bess, senior, subordinated)

    # 2) Generic path-addressed overrides on the full tree.
    for key, value in overrides.items():
        if key in _LEGACY_KEYS:
            continue  # already handled above
        if key.startswith("fv."):
            fv = set_by_path(fv, key[len("fv.") :], value)
        elif key.startswith("bess."):
            bess = set_by_path(bess, key[len("bess.") :], value)
        elif key.startswith("senior."):
            field = key[len("senior.") :]
            senior[field] = int(value) if field == "tenor_years" else float(value)
        elif key.startswith("subordinated."):
            field = key[len("subordinated.") :]
            subordinated[field] = int(value) if field == "tenor_years" else float(value)
        elif key == "wacc":
            wacc = float(value)

    return fv, bess, senior, subordinated, wacc


def _run_infra(config_dict: dict[str, Any]) -> FinancialOutput:
    cfg = InfrastructureModelConfig.model_validate(config_dict)
    return InfrastructureModel(cfg).run()


def _unlevered_npv(config_dict: dict[str, Any], wacc: float = _WACC) -> float:
    """Project NPV with NO leverage: discount annual (CFO + CFI) at the WACC."""
    levered_free = dict(config_dict)
    levered_free["financing"] = {"max_leverage": 0.0}
    out = _run_infra(levered_free)
    cfo = _annual(out.cashflow["cfo"])
    cfi = _annual(out.cashflow["cfi"])
    fcf = [cfo[i] + cfi[i] for i in range(len(cfo))]
    return consolidate_npv(fcf, wacc)


def _ancillary_effective(bess: dict[str, Any], ancillary_base: float) -> list[float]:
    """Effective ancillary revenue series (€/MW · year): base × decay multiplier.

    The BESS preset's ancillary stream carries ``curve_points`` (a 0..1 decay
    multiplier per year). Multiply the year-1 base by it; fall back to the
    ``ancillary_afrr_es`` curve library if the preset has none.
    """
    points: list[float] | None = None
    for stream in bess["revenue"]:
        if stream.get("type") == "ancillary":
            points = stream.get("curve_points")
            break
    if points:
        series = [ancillary_base * float(p) for p in points]
    else:
        series = Curve.from_library("ancillary_afrr_es").to_list(_HORIZON_YEARS)
    # Normalise length to the horizon.
    if len(series) < _HORIZON_YEARS:
        series = series + [series[-1] if series else 0.0] * (_HORIZON_YEARS - len(series))
    return series[:_HORIZON_YEARS]


def run_svj(overrides: dict[str, Any]) -> dict[str, Any]:
    """Run the SVJ deal with the given driver overrides and shape the output."""
    fv, bess, senior_cfg, sub_cfg, wacc = _build_deal(overrides)

    # --- Project NPVs (unlevered, using the OVERRIDDEN dicts + deal WACC) ---
    npv_fv = _unlevered_npv(fv, wacc)
    npv_bess = _unlevered_npv(bess, wacc)
    npv_hybrid = npv_fv + npv_bess

    # --- Annual EBITDA series for each asset (as configured, with debt) ---
    fv_out = _run_infra(fv)
    bess_out = _run_infra(bess)
    fv_ebitda = _annual(fv_out.pnl["ebitda"])
    bess_ebitda = _annual(bess_out.pnl["ebitda"])

    # --- Hybrid CAPEX and year-1 revenue (for portfolio aggregation) ---
    total_capex = float(fv_out.summary["total_capex"]) + float(bess_out.summary["total_capex"])
    fv_rev_y1 = _annual(fv_out.pnl["revenue"])
    bess_rev_y1 = _annual(bess_out.pnl["revenue"])
    revenue_y1 = (fv_rev_y1[0] if fv_rev_y1 else 0.0) + (bess_rev_y1[0] if bess_rev_y1 else 0.0)

    # --- Investor metrics from the consolidated hybrid with the capital stack ---
    senior = TrancheSpec(**senior_cfg)
    subordinated = TrancheSpec(**sub_cfg)
    hybrid = HybridProject(
        [
            InfrastructureModelConfig.model_validate(fv),
            InfrastructureModelConfig.model_validate(bess),
        ],
        discount_rate_annual=wacc,
        senior=senior,
        subordinated=subordinated,
    )
    hr = hybrid.run()

    # --- Per-year subordinated DSCR profile over the sub tenor ---
    dscr_profile = _dscr_profile(hr.consolidated_ebitda or [], senior, subordinated)

    years = list(range(1, _HORIZON_YEARS + 1))
    spread_curve = Curve.from_library("spread_da_es").to_list(_HORIZON_YEARS)
    ancillary_curve = _ancillary_effective(bess, float(overrides.get("ancillary_base", 74000.0)))

    return {
        "kpis": {
            "npv_fv": round(npv_fv),
            "npv_bess": round(npv_bess),
            "npv_hybrid": round(npv_hybrid),
            "dscr_sub_min": round(hr.dscr_subordinated_min, 2),
            "dscr_sub_avg": round(hr.dscr_subordinated_avg, 2),
            "dscr_senior_min": round(hr.dscr_senior_min, 2),
            "moic_sub": round(hr.moic_subordinated, 3),
            "recovery": round(hr.recovery_going_concern, 2),
            "total_capex": round(total_capex),
            "revenue_y1": round(revenue_y1),
            "irr": round(hr.irr, 4),
        },
        "cashflows": {
            "years": years,
            "fv": [round(v) for v in fv_ebitda],
            "bess": [round(v) for v in bess_ebitda],
        },
        "curves": {
            "spread": [round(v, 2) for v in spread_curve],
            "ancillary": [round(v) for v in ancillary_curve],
        },
        "bridge": {"fv": round(npv_fv), "bess": round(npv_bess), "hybrid": round(npv_hybrid)},
        "dscr_profile": dscr_profile,
    }


def _dscr_profile(
    cons_ebitda: list[float], senior: TrancheSpec, subordinated: TrancheSpec
) -> list[float]:
    """Per-year subordinated DSCR over the sub tenor (net of senior service)."""
    if not cons_ebitda:
        return []
    horizon = len(cons_ebitda)
    senior_ds = HybridProject._tranche_debt_service(senior, horizon)
    sub_ds = HybridProject._tranche_debt_service(subordinated, horizon)
    dscrs = compute_waterfall_dscr(cons_ebitda, [senior_ds, sub_ds])
    sub_row = dscrs[1]
    finite = [round(d, 3) for d in sub_row[: subordinated.tenor_years] if 0 < d < float("inf")]
    return finite


def build_svj_xlsx(overrides: dict[str, Any]) -> bytes:
    """Run the SVJ BESS model and return a multi-sheet Excel workbook as bytes."""
    _, bess, _, _, _ = _build_deal(overrides)
    out = _run_infra(bess)
    # The shared xlsx exporter renders a "UnitEcon" sheet from the unit_econ
    # dict; infrastructure models don't produce one, so supply zero-filled
    # series of the right length (it has no meaning for project finance).
    n_periods = len(out.pnl["revenue"])
    unit_econ = {
        col: [0.0] * n_periods
        for col in ("arpu", "gross_margin", "cac", "ltv", "ltv_cac", "payback_months")
    }
    results = ModelResults(
        pnl=out.pnl,
        cashflow=out.cashflow,
        balance=out.balance,
        unit_econ=unit_econ,
        valuation=out.valuation,
        sensitivity=out.sensitivity,
        debt_metrics=out.debt_metrics,
        revenue_breakdown=out.revenue_breakdown,
        summary=out.summary,
        inputs_resolved=out.inputs_resolved,
    )
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        to_xlsx(results, tmp_path)
        return Path(tmp_path).read_bytes()
    finally:
        Path(tmp_path).unlink(missing_ok=True)
