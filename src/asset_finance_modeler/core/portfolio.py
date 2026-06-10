from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PortfolioEntry:
    scenario_id: str
    name: str
    asset_type: str
    summary: dict[str, Any]


@dataclass
class PortfolioAnalysis:
    entries: list[PortfolioEntry]
    aggregated: dict[str, float]  # totals and weighted averages
    comparison_table: list[dict[str, Any]]  # side-by-side
    narrative: str


def analyze_portfolio(scenarios: list[dict[str, Any]]) -> PortfolioAnalysis:
    """Analyze a portfolio of scenarios.

    Each scenario dict should have: id, name, base_model, summary, project_kpis (optional)
    """
    entries: list[PortfolioEntry] = []
    for s in scenarios:
        summary = dict(s.get("summary", {}))
        kpis = s.get("project_kpis", {})
        if isinstance(kpis, dict):
            summary.update(kpis)
        entries.append(PortfolioEntry(
            scenario_id=s.get("id", ""),
            name=s.get("name", ""),
            asset_type=s.get("base_model", s.get("asset_type", "")),
            summary=summary,
        ))

    # Aggregated metrics
    total_capex = sum(e.summary.get("total_capex", 0) for e in entries)
    total_revenue_y1 = sum(e.summary.get("revenue_y1", 0) for e in entries)
    total_ev = sum(e.summary.get("enterprise_value", 0) for e in entries)

    # Weighted average IRR (by CAPEX weight)
    irr_weighted = 0.0
    if total_capex > 0:
        for e in entries:
            capex = e.summary.get("total_capex", 0)
            irr = e.summary.get("irr_project", 0)
            if isinstance(irr, (int, float)) and isinstance(capex, (int, float)):
                irr_weighted += irr * capex / total_capex

    # Worst DSCR
    dscr_values = [e.summary.get("dscr_min", float("inf")) for e in entries
                   if isinstance(e.summary.get("dscr_min"), (int, float))]
    worst_dscr = min(dscr_values) if dscr_values else 0

    aggregated = {
        "total_capex": total_capex,
        "total_revenue_y1": total_revenue_y1,
        "total_enterprise_value": total_ev,
        "weighted_avg_irr_project": irr_weighted,
        "worst_dscr_min": worst_dscr,
        "project_count": len(entries),
    }

    # Comparison table
    comparison = []
    for e in entries:
        row: dict[str, Any] = {"name": e.name, "asset_type": e.asset_type}
        for key in ("total_capex", "revenue_y1", "enterprise_value", "irr_project",
                    "irr_equity", "lcoe", "dscr_min", "payback_years"):
            row[key] = e.summary.get(key, "—")
        comparison.append(row)

    # Narrative
    parts = [f"Portfolio of {len(entries)} project(s)."]
    parts.append(f"Total CAPEX: €{total_capex:,.0f}.")
    parts.append(f"Combined enterprise value: €{total_ev:,.0f}.")
    if irr_weighted > 0:
        parts.append(f"Weighted avg project IRR: {irr_weighted:.1%}.")
    if worst_dscr > 0 and worst_dscr < float("inf"):
        parts.append(f"Worst DSCR across portfolio: {worst_dscr:.2f}x.")
    narrative = " ".join(parts)

    return PortfolioAnalysis(
        entries=entries, aggregated=aggregated,
        comparison_table=comparison, narrative=narrative,
    )


def consolidate_series(series_list: list[list[float]]) -> list[float]:
    """Sum several per-period series element-wise. Shorter series are treated
    as 0 in the periods they don't cover (ramp-up / different horizons)."""
    n = max((len(s) for s in series_list), default=0)
    return [sum(s[t] for s in series_list if t < len(s)) for t in range(n)]


def consolidate_npv(fcf: list[float], discount_rate_annual: float) -> float:
    """NPV of a consolidated annual FCF series with the year-0 outlay at t=0
    (plain discounted sum, no terminal value). Convention matches equity NPV."""
    return sum(cf / ((1.0 + discount_rate_annual) ** t) for t, cf in enumerate(fcf))
