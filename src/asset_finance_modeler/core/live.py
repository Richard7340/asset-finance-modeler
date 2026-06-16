"""F3 LIVE reprojection: base-vs-live valuation by overlay of actuals.

Given a frozen BASE output (the asset's ``results_snapshot``: annual
``income_statement`` + ``cash_flow``) and the operator's real (actual) figures
aggregated by model year, ``compute_live`` produces a spliced LIVE projection:

  * past years (year index < ``elapsed_years``) take the REAL value for each
    tracked line; non-tracked past lines keep the base value;
  * future years are the BASE assumptions, untouched;
  * the dependent P&L of past years is minimally re-derived from the base
    year's ratios (so an override of one line flows to EBITDA / net_income /
    CFO consistently);
  * the spliced annual FCF is revalued with the SAME convention as the base
    (``compute_dcf`` for the generic/infra/business case, or a plain discounted
    sum for the SVJ-style consolidate convention), and IRR / DSCR are
    recomputed on the spliced series.

SIMPLIFICATIONS (overlay-by-aggregation, documented per the spec):
  * Annual granularity. The engine projects monthly internally, but the frozen
    snapshot — and therefore this overlay — is annual. Actuals are aggregated to
    the model year before overlaying. A native multi-period engine is v4.
  * Re-derivation is by RATIO of the base year, not a full re-run of the engine
    (we no longer hold the resolved config here): overriding revenue rescales
    ebitda/ebit/ebt/tax/net_income/cfo of that year by the base revenue ratio;
    overriding a margin line (ebitda/ebit/...) shifts the lines below it by the
    same delta. This keeps the statement internally consistent without
    re-running cost/tax engines.
  * DSCR uses EBITDA as the CFADS proxy (matching the engine) and the BASE
    annual debt service derived from base CFF in the operating years
    (``debt_service[y] = max(0, -cff[y])``). The loan schedule does not change
    because operations deviate, so debt service stays at base; only CFADS moves.
  * NPV of the generic case uses ``compute_dcf(..., periods_per_year=1)`` exactly
    as the engine did, so with no actuals LIVE == BASE to the cent.
"""
from __future__ import annotations

import copy
from typing import Any, Literal

from asset_finance_modeler.core.portfolio import consolidate_npv
from asset_finance_modeler.core.valuation import compute_dcf, compute_irr

# P&L rows in top-to-bottom order; everything below a given override line is
# shifted by the same delta when that line is overridden directly.
_PNL_ORDER = ["revenue", "ebitda", "ebit", "ebt", "tax", "net_income"]


def _annual_fcf(income: dict[str, Any], cash_flow: dict[str, Any]) -> list[float]:
    """Valuation FCF = CFO + CFI per year (the engine convention)."""
    cfo = cash_flow.get("cfo") or []
    cfi = cash_flow.get("cfi") or []
    n = max(len(cfo), len(cfi))
    return [
        (cfo[y] if y < len(cfo) else 0.0) + (cfi[y] if y < len(cfi) else 0.0)
        for y in range(n)
    ]


def _npv(
    fcf: list[float],
    discount_rate: float,
    terminal_growth: float,
    terminal_method: str,
    convention: str,
) -> float:
    if convention == "sum":
        return consolidate_npv(fcf, discount_rate)
    if not fcf:
        return 0.0
    try:
        return compute_dcf(
            fcf_series=fcf,
            wacc_annual=discount_rate,
            terminal_growth=terminal_growth,
            periods_per_year=1,
            terminal_method=terminal_method,  # type: ignore[arg-type]
        )["enterprise_value"]
    except ValueError:
        return 0.0


def _irr_series(fcf: list[float]) -> float | None:
    return compute_irr(fcf, 1)


def _dscr(ebitda: list[float], cff: list[float]) -> dict[str, float]:
    """DSCR per year = EBITDA (CFADS proxy) / base debt service, where the base
    debt service in an operating year is ``max(0, -cff[y])`` (drawdown years are
    positive cff -> no service obligation -> skipped)."""
    dscr_series: list[float] = []
    for y in range(len(ebitda)):
        ds = -cff[y] if y < len(cff) else 0.0
        if ds <= 0:
            continue
        cfads = ebitda[y]
        dscr_series.append(cfads / ds if cfads > 0 else 0.0)
    if not dscr_series:
        return {"dscr_min": 0.0, "dscr_avg": 0.0, "series": []}
    return {
        "dscr_min": min(dscr_series),
        "dscr_avg": sum(dscr_series) / len(dscr_series),
        "series": dscr_series,
    }


def _kpis(
    series: dict[str, Any],
    discount_rate: float,
    terminal_growth: float,
    terminal_method: str,
    convention: str,
) -> dict[str, Any]:
    income = series["income_statement"]
    rows = income["rows"]
    cash_flow = series["cash_flow"]
    fcf = _annual_fcf(income, cash_flow)
    npv = _npv(fcf, discount_rate, terminal_growth, terminal_method, convention)
    irr = _irr_series(fcf)
    dscr = _dscr(rows.get("ebitda") or [], cash_flow.get("cff") or [])
    return {
        "npv": round(npv),
        "irr_project": round(irr, 4) if irr is not None else None,
        "dscr_min": round(dscr["dscr_min"], 2),
        "dscr_avg": round(dscr["dscr_avg"], 2),
    }


def _overlay_one(
    rows: dict[str, list[float]],
    cash_flow: dict[str, list[float]],
    line_path: str,
    year: int,
    real: float,
) -> None:
    if line_path.startswith("income_statement.rows."):
        key = line_path.split("income_statement.rows.", 1)[1]
        if key not in rows or year >= len(rows[key]):
            return
        old = rows[key][year]
        if key == "revenue":
            # Rescale the whole P&L of that year by the revenue ratio (keeps the
            # base year's cost & tax ratios), then propagate to CFO.
            ratio = (real / old) if old else 1.0
            for k in _PNL_ORDER:
                if k in rows and year < len(rows[k]):
                    rows[k][year] = rows[k][year] * ratio
            rows["revenue"][year] = real  # exact (avoid float drift)
            # CFO is shifted by the net_income delta in compute_live (the caller
            # captures NI before/after this overlay). Add-backs (D&A) unchanged.
            return
        # A margin / cost line overridden directly: shift it and everything
        # below it (ebit, ebt, tax, net_income) by the same delta. Lines above
        # (revenue) are unchanged.
        delta = real - old
        if key in _PNL_ORDER:
            idx = _PNL_ORDER.index(key)
            for k in _PNL_ORDER[idx:]:
                if k in rows and year < len(rows[k]):
                    rows[k][year] = rows[k][year] + delta
        else:
            rows[key][year] = real
        _shift_cfo(cash_flow, year, delta)
        return

    if line_path.startswith("cash_flow."):
        key = line_path.split("cash_flow.", 1)[1]
        if key not in cash_flow or year >= len(cash_flow[key]):
            return
        cash_flow[key][year] = real
        return


def _shift_cfo(cash_flow: dict[str, list[float]], year: int, ni_delta: float) -> None:
    """Shift CFO of ``year`` by the change in net_income (add-backs unchanged)."""
    cfo = cash_flow.get("cfo")
    if cfo is not None and year < len(cfo):
        cfo[year] = cfo[year] + ni_delta


def compute_live(
    base_output: dict[str, Any],
    actuals_by_line_by_year: dict[str, dict[int, float]],
    elapsed_years: int,
    discount_rate: float,
    terminal_growth: float = 0.0,
    terminal_method: str = "none",
    npv_convention: Literal["dcf", "sum"] = "dcf",
) -> dict[str, Any]:
    """Return ``{base: {series, kpis}, live: {series, kpis}, deviation_summary}``.

    ``base_output`` is the frozen snapshot shape (``income_statement`` with
    ``rows`` + ``cash_flow``). ``actuals_by_line_by_year`` maps a trackable
    line_path to ``{year_index: aggregated_real_value}``. ``elapsed_years`` is
    the number of model years already elapsed (past). See the module docstring
    for the documented simplifications.
    """
    base_series = {
        "income_statement": copy.deepcopy(base_output.get("income_statement") or {"rows": {}}),
        "cash_flow": copy.deepcopy(base_output.get("cash_flow") or {}),
    }
    base_series["income_statement"].setdefault("rows", {})

    live_series = copy.deepcopy(base_series)

    # net_income delta for the revenue path: capture before/after to shift CFO.
    rows = live_series["income_statement"]["rows"]
    cash_flow = live_series["cash_flow"]
    for line_path, by_year in actuals_by_line_by_year.items():
        for year, real in by_year.items():
            if year >= elapsed_years or year < 0:
                continue
            ni_before = rows["net_income"][year] if (
                "net_income" in rows and year < len(rows["net_income"])
            ) else None
            _overlay_one(rows, cash_flow, line_path, year, real)
            if line_path == "income_statement.rows.revenue" and ni_before is not None:
                ni_after = rows["net_income"][year]
                _shift_cfo(cash_flow, year, ni_after - ni_before)

    base_kpis = _kpis(
        base_series, discount_rate, terminal_growth, terminal_method, npv_convention
    )
    live_kpis = _kpis(
        live_series, discount_rate, terminal_growth, terminal_method, npv_convention
    )

    deviation_summary = {
        "npv_base": base_kpis["npv"],
        "npv_live": live_kpis["npv"],
        "npv_delta": live_kpis["npv"] - base_kpis["npv"],
        "irr_base": base_kpis["irr_project"],
        "irr_live": live_kpis["irr_project"],
        "dscr_min_base": base_kpis["dscr_min"],
        "dscr_min_live": live_kpis["dscr_min"],
        "elapsed_years": elapsed_years,
    }

    return {
        "base": {"series": base_series, "kpis": base_kpis},
        "live": {"series": live_series, "kpis": live_kpis},
        "deviation_summary": deviation_summary,
    }
