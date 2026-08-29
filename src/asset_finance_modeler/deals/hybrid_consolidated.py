"""Vía de consolidación híbrida: generación y almacenamiento bajo una misma
financiación, con estados consolidados y amortización anual.

Los valores por defecto de deuda y descuento son de EJEMPLO, para que el módulo
se pueda ejecutar tal cual. En un caso real se pasan por parámetro.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from pydantic import ValidationError

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
from asset_finance_modeler.web_api.introspect import (
    InvalidPathError,
    schema_tree,
    set_by_path,
)


class HybridConsolidatedInputError(ValueError):
    """A bad hybrid consolidated override (wrong type, out-of-range, or pathological value).

    Carries a human-readable ``message`` so the web layer can return an HTTP
    400 (not a 500) like the generic model-run path does (A1)."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def _to_float(value: Any, field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise HybridConsolidatedInputError(f"invalid override value: {field}: not a number") from exc


def _to_int(value: Any, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise HybridConsolidatedInputError(f"invalid override value: {field}: not an integer") from exc

# Validated deal conventions.
_WACC = 0.06  # ejemplo; se pasa por parámetro en cada caso
_PPY = 12  # monthly presets
_HORIZON_YEARS = 30

# Default capital stack (principal, interest_rate, tenor_years).
_SENIOR_DEFAULTS = {"principal": 2_000_000.0, "interest_rate": 0.04, "tenor_years": 10}
_SUB_DEFAULTS = {"principal": 1_500_000.0, "interest_rate": 0.08, "tenor_years": 7}

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


def hybrid_consolidated_input_spec() -> list[dict[str, Any]]:
    """Full editable input tree: FV + BESS preset trees + debt/valuation.

    Each FV/BESS leaf is prefixed (``fv.`` / ``bess.``) so overrides can be
    routed to the right asset; debt/valuation leaves expose the consolidated
    capital stack and the hybrid WACC.
    """
    fv_leaves = [
        {**leaf, "path": "fv." + leaf["path"], "section": "FV · " + leaf["section"]}
        for leaf in schema_tree(load_preset("hybrid_pv_reference").model_dump())
    ]
    bess_leaves = [
        {**leaf, "path": "bess." + leaf["path"], "section": "BESS · " + leaf["section"]}
        for leaf in schema_tree(load_preset("hybrid_bess_reference").model_dump())
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


def _consolidated_statements(
    fv_out: FinancialOutput, bess_out: FinancialOutput
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Consolidated (FV + BESS) annual P&L and cash flow, shaped like the
    generic /api/models payload (income_statement + cash_flow) so a generic
    client consumes the hybrid like any other model (P3-2).

    The consolidation is the sum of the two asset legs, each run with its own
    leverage, aggregated to annual buckets. This is the operating/accounting
    view of the deal; the headline investor NPV/DSCR/MOIC keys are unchanged.
    """

    def _add(a: list[float], b: list[float]) -> list[float]:
        m = max(len(a), len(b))
        a = a + [0.0] * (m - len(a))
        b = b + [0.0] * (m - len(b))
        return [a[i] + b[i] for i in range(m)]

    income_rows: dict[str, list[float]] = {}
    for k in ("revenue", "ebitda", "ebit", "interest_expense", "ebt", "tax", "net_income"):
        if k in fv_out.pnl or k in bess_out.pnl:
            fv_a = _annual(fv_out.pnl.get(k, []))
            bess_a = _annual(bess_out.pnl.get(k, []))
            income_rows[k] = [round(v) for v in _add(fv_a, bess_a)]
    n_years = len(next(iter(income_rows.values()))) if income_rows else 0
    income_statement = {"years": list(range(1, n_years + 1)), "rows": income_rows}

    cash_flow: dict[str, Any] = {"years": list(range(1, n_years + 1))}
    for k in ("cfo", "cfi", "cff"):
        if k in fv_out.cashflow or k in bess_out.cashflow:
            fv_a = _annual(fv_out.cashflow.get(k, []))
            bess_a = _annual(bess_out.cashflow.get(k, []))
            cash_flow[k] = [round(v) for v in _add(fv_a, bess_a)]
    return income_statement, cash_flow


def _apply_legacy(
    overrides: dict[str, Any],
    fv: dict[str, Any],
    bess: dict[str, Any],
    senior: dict[str, Any],
    subordinated: dict[str, Any],
) -> None:
    """Map the 6 original drivers onto their real targets (mutates in place)."""
    if "fv_ppa_price" in overrides:
        v = _to_float(overrides["fv_ppa_price"], "fv_ppa_price")
        for stream in fv["revenue"]:
            if stream.get("type") == "ppa":
                stream["price_eur_per_unit"] = v

    if "spread_capture" in overrides:
        v = _to_float(overrides["spread_capture"], "spread_capture")
        for stream in bess["revenue"]:
            if stream.get("type") == "arbitrage":
                stream["spread_capture_ratio"] = v

    if "ancillary_base" in overrides:
        v = _to_float(overrides["ancillary_base"], "ancillary_base")
        for stream in bess["revenue"]:
            if stream.get("type") == "ancillary":
                stream["afrr_eur_mw_yr"] = v

    if "bess_capex_eur_kwh" in overrides:
        v = _to_float(overrides["bess_capex_eur_kwh"], "bess_capex_eur_kwh")
        for item in bess["capex"]["items"]:
            if item.get("unit") == "kWh":
                item["amount_per_unit"] = v

    if "sub_rate" in overrides:
        subordinated["interest_rate"] = _to_float(overrides["sub_rate"], "sub_rate")
    if "sub_tenor_years" in overrides:
        subordinated["tenor_years"] = _to_int(
            overrides["sub_tenor_years"], "sub_tenor_years"
        )


def _build_deal(
    overrides: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], float]:
    """Load both presets + default capital stack, apply legacy drivers AND any
    path-addressed override (``fv.*`` / ``bess.*`` / ``senior.*`` /
    ``subordinated.*`` / ``wacc``). Returns (fv, bess, senior, sub, wacc)."""
    fv = load_preset("hybrid_pv_reference").model_dump()
    bess = load_preset("hybrid_bess_reference").model_dump()
    senior = dict(_SENIOR_DEFAULTS)
    subordinated = dict(_SUB_DEFAULTS)
    wacc = _WACC

    # 1) Backward-compat: the 6 legacy drivers (so old saved overrides run).
    _apply_legacy(overrides, fv, bess, senior, subordinated)

    # 2) Generic path-addressed overrides on the full tree. Route them through
    #    the same validation the generic /api/models path uses: an invalid path
    #    or bad-type/pathological value becomes a HybridConsolidatedInputError → HTTP 400, never
    #    an unhandled 500 (A1).
    for key, value in overrides.items():
        if key in _LEGACY_KEYS:
            continue  # already handled above
        try:
            if key.startswith("fv."):
                fv = set_by_path(fv, key[len("fv.") :], value)
            elif key.startswith("bess."):
                bess = set_by_path(bess, key[len("bess.") :], value)
            elif key.startswith("senior."):
                field = key[len("senior.") :]
                senior[field] = (
                    _to_int(value, key) if field == "tenor_years" else _to_float(value, key)
                )
            elif key.startswith("subordinated."):
                field = key[len("subordinated.") :]
                subordinated[field] = (
                    _to_int(value, key) if field == "tenor_years" else _to_float(value, key)
                )
            elif key == "wacc":
                wacc = _to_float(value, "wacc")
        except InvalidPathError as exc:
            raise HybridConsolidatedInputError(f"invalid override path: {exc.path}") from exc

    # Validate the discount rate: a non-positive WACC makes the discount factor
    # (1+r)^t collapse to 0 and ZeroDivisions the NPV — reject it as a 400.
    if not (wacc > 0.0):
        raise HybridConsolidatedInputError("invalid override value: wacc: must be > 0")

    return fv, bess, senior, subordinated, wacc


def _run_infra(config_dict: dict[str, Any]) -> FinancialOutput:
    try:
        cfg = InfrastructureModelConfig.model_validate(config_dict)
    except ValidationError as exc:
        errs = exc.errors()
        if errs:
            e = errs[0]
            loc = ".".join(str(p) for p in e.get("loc", ()))
            msg = e.get("msg", "invalid value")
            detail = (
                f"invalid override value: {loc}: {msg}" if loc else f"invalid override value: {msg}"
            )
        else:  # pragma: no cover — defensive
            detail = "invalid override value"
        raise HybridConsolidatedInputError(detail) from exc
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


def run_hybrid_consolidated(overrides: dict[str, Any]) -> dict[str, Any]:
    """Run the hybrid consolidated deal with the given driver overrides and shape the output."""
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

    # --- Consolidated P&L / CF (generic client payload, P3-2) ---
    income_statement, cash_flow = _consolidated_statements(fv_out, bess_out)

    # --- Per-year subordinated DSCR profile over the sub tenor (operating
    #     periods only — debt aligned to the project COD via IDC) ---
    dscr_profile = _dscr_profile(
        hr.consolidated_ebitda or [], senior, subordinated, hybrid._consolidated_cod_periods()
    )

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
            "irr": round(hr.irr, 4) if hr.irr is not None else None,
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
        # P3-2: consolidated P&L / CF so a generic client consumes the hybrid
        # like any other model (legacy keys above are kept for back-compat).
        "income_statement": income_statement,
        "cash_flow": cash_flow,
    }


def _dscr_profile(
    cons_ebitda: list[float],
    senior: TrancheSpec,
    subordinated: TrancheSpec,
    cod: int = 0,
) -> list[float]:
    """Per-year subordinated DSCR over the sub tenor (net of senior service).

    With ``cod`` > 0 the tranches amortize from the project COD (IDC during
    construction), so the profile covers the operating tenor cod..cod+tenor."""
    if not cons_ebitda:
        return []
    horizon = len(cons_ebitda)
    senior_ds = HybridProject._tranche_debt_service(senior, horizon, cod)
    sub_ds = HybridProject._tranche_debt_service(subordinated, horizon, cod)
    dscrs = compute_waterfall_dscr(cons_ebitda, [senior_ds, sub_ds])
    sub_row = dscrs[1]
    op_end = cod + subordinated.tenor_years
    finite = [round(d, 3) for d in sub_row[cod:op_end] if 0 < d < float("inf")]
    return finite


def build_hybrid_consolidated_xlsx(overrides: dict[str, Any]) -> bytes:
    """Run the hybrid consolidated BESS model and return a multi-sheet Excel workbook as bytes."""
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
