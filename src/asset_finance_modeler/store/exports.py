import csv as _csv
import json as _json
from pathlib import Path
from typing import Any

from asset_finance_modeler.assets.saas.model import ModelResults

_VIEW_KEYS: dict[str, tuple[str, list[str]]] = {
    "pnl": ("pnl", ["revenue", "cogs", "gross_profit", "opex", "ebitda", "ebit", "tax", "net_income"]),
    "cashflow": ("cashflow", ["cfo", "cfi", "cff", "cash"]),
    "balance": ("balance", ["total_assets", "total_liabilities", "equity", "cash", "debt"]),
    "unit_econ": ("unit_econ", ["arpu", "gross_margin", "cac", "ltv", "ltv_cac", "payback_months"]),
}


def to_summary(results: ModelResults) -> dict[str, float | int]:
    """Return the summary dict already computed by SaasModel."""
    return dict(results.summary)


def _section_for_view(view: str) -> tuple[str, list[str]]:
    if view not in _VIEW_KEYS:
        raise ValueError(f"Unknown view {view!r}. Valid: {list(_VIEW_KEYS)}")
    return _VIEW_KEYS[view]


def _format_number(v: float | int) -> str:
    if isinstance(v, float):
        if abs(v) >= 1000:
            return f"{v:,.0f}"
        if abs(v) < 1:
            return f"{v:.4f}"
        return f"{v:.2f}"
    return str(v)


def to_markdown_table(results: ModelResults, view: str, max_periods: int | None = None) -> str:
    """Render a section of the model as a markdown table."""
    attr, columns = _section_for_view(view)
    data: dict[str, list[Any]] = getattr(results, attr)
    n = len(next(iter(data.values())))
    if max_periods is not None:
        n = min(n, max_periods)

    header = ["period"] + columns
    sep = ["---"] * len(header)
    rows = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(sep) + " |",
    ]
    for t in range(n):
        cells = [str(t)] + [_format_number(data[c][t]) for c in columns]
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows)


def to_markdown_report(results: ModelResults) -> str:
    """Narrative markdown report — for email or chat summaries."""
    s = results.summary
    sections: list[str] = []

    sections.append("# Modelo financiero — resumen ejecutivo")
    sections.append("")
    sections.append(f"Generado a partir de {len(results.pnl['revenue'])} periodos.")
    sections.append("")

    sections.append("## Ingresos y rentabilidad")
    sections.append(f"- Revenue Año 1: **{_format_number(s.get('revenue_y1', 0))} €**")
    sections.append(f"- Revenue último periodo: {_format_number(s.get('revenue_end_period', 0))} €")
    sections.append(f"- EBITDA margen último periodo: {s.get('ebitda_margin_end', 0):.1%}")
    sections.append("")

    sections.append("## Clientes y unit economics")
    sections.append(f"- Clientes activos al final: {_format_number(s.get('active_customers_end', 0))}")
    sections.append(f"- Unidades activas al final: {_format_number(s.get('active_units_end', 0))}")
    ltv_cac = s.get("ltv_cac_end", -1)
    if ltv_cac > 0:
        sections.append(f"- LTV/CAC: {ltv_cac:.2f}")
    sections.append("")

    sections.append("## Caja y valoración")
    sections.append(f"- Caja al final: {_format_number(s.get('cash_end', 0))} €")
    runway = s.get("runway_months", -1)
    if runway < 0:
        sections.append("- Runway: indefinido (no se cruza cero)")
    else:
        sections.append(f"- Runway: {runway} meses hasta cash=0")
    sections.append(f"- Enterprise value (DCF): {_format_number(s.get('enterprise_value', 0))} €")
    sections.append("")

    return "\n".join(sections)


def to_csv(results: ModelResults, view: str, path: str) -> None:
    """Write a section to CSV file. Columns: period + view-specific keys."""
    attr, columns = _section_for_view(view)
    data: dict[str, list[Any]] = getattr(results, attr)
    n = len(next(iter(data.values())))
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        writer = _csv.writer(f)
        writer.writerow(["period"] + columns)
        for t in range(n):
            writer.writerow([t] + [data[c][t] for c in columns])


def to_json(results: ModelResults, path: str | None = None) -> str:
    """Return full results as JSON string. Optionally also write to file."""
    payload = {
        "summary": dict(results.summary),
        "pnl": results.pnl,
        "cashflow": results.cashflow,
        "balance": results.balance,
        "unit_econ": results.unit_econ,
        "valuation": results.valuation,
        "sensitivity": results.sensitivity,
        "debt_metrics": results.debt_metrics,
        "revenue_breakdown": results.revenue_breakdown,
    }
    text = _json.dumps(payload, default=str, indent=2)
    if path is not None:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text)
    return text
