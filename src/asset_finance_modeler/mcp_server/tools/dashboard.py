"""Dashboard artifact generator.

Generates self-contained HTML files with Chart.js visualisations of
financial model results.  No server required — all data is embedded as
JSON inside <script> tags and Chart.js is loaded from CDN.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from typing import Any

from asset_finance_modeler.store.scenarios import SQLiteScenarioStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FMT_CURRENCY_ABBREV = (
    (1_000_000_000, "B"),
    (1_000_000, "M"),
    (1_000, "k"),
    (1, ""),
)


def _fmt_currency(value: float | None, *, decimals: int = 1) -> str:
    """Format a number as €123.4M / €1.2k / €42 etc."""
    if value is None:
        return "—"
    if not math.isfinite(value):
        return "∞" if value > 0 else "-∞"
    abs_val = abs(value)
    for threshold, suffix in _FMT_CURRENCY_ABBREV:
        if abs_val >= threshold:
            return f"€{value / threshold:.{decimals}f}{suffix}"
    return f"€{value:.0f}"


def _fmt_pct(value: float | None, *, decimals: int = 1) -> str:
    if value is None:
        return "—"
    if not math.isfinite(value):
        return "—"
    return f"{value * 100:.{decimals}f}%"


def _fmt_x(value: float | None, *, decimals: int = 2) -> str:
    if value is None:
        return "—"
    if not math.isfinite(value):
        return "—"
    return f"{value:.{decimals}f}x"


def _clean_series(series: list[Any]) -> list[float | None]:
    """Replace inf / NaN with None so json.dumps produces null."""
    out: list[float | None] = []
    for v in series:
        try:
            f = float(v)
            out.append(None if not math.isfinite(f) else f)
        except (TypeError, ValueError):
            out.append(None)
    return out


def _safe_json(obj: Any) -> str:
    return json.dumps(obj, allow_nan=False)


# ---------------------------------------------------------------------------
# KPI card builder
# ---------------------------------------------------------------------------

def _build_kpi_cards(results: dict[str, Any]) -> str:
    summary = results.get("summary", {})
    kpis = results.get("project_kpis", {}) or {}

    cards: list[tuple[str, str, bool]] = []  # (label, formatted_value, is_negative)

    def _add(label: str, raw: Any, fmt_fn: Any = _fmt_currency, negative: bool = False) -> None:
        val_str = fmt_fn(raw) if raw is not None else "—"
        cards.append((label, val_str, negative))

    _add("Total CAPEX", summary.get("total_capex"))
    _add("Revenue Y1", summary.get("revenue_y1"))

    ebitda_m = summary.get("ebitda_margin_end")
    cards.append(("EBITDA Margin", _fmt_pct(ebitda_m), False))

    _add("Enterprise Value", summary.get("enterprise_value"))

    if kpis:
        irr_p = kpis.get("irr_project")
        irr_e = kpis.get("irr_equity")
        lcoe = kpis.get("lcoe")
        dscr_min = kpis.get("dscr_min")
        payback = kpis.get("payback_years")

        if irr_p is not None:
            cards.append(("IRR Project", _fmt_pct(irr_p), False))
        if irr_e is not None:
            cards.append(("IRR Equity", _fmt_pct(irr_e), False))
        if lcoe is not None:
            cards.append(("LCOE", f"€{lcoe:.1f}/MWh", False))
        if dscr_min is not None:
            cards.append(("DSCR Min", f"{dscr_min:.2f}x", False))
        if payback is not None:
            cards.append(("Payback", f"{payback:.1f} yrs", False))

    parts: list[str] = []
    for label, value, negative in cards:
        neg_cls = " negative" if negative else ""
        parts.append(
            f'<div class="kpi-card">'
            f'<div class="kpi-label">{label}</div>'
            f'<div class="kpi-value{neg_cls}">{value}</div>'
            f"</div>"
        )
    return "\n        ".join(parts)


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{scenario_name} — Financial Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #0f172a;
            color: #e2e8f0;
            padding: 24px;
        }}
        .dashboard {{ max-width: 1400px; margin: 0 auto; }}
        h1 {{ font-size: 28px; margin-bottom: 8px; color: #f1f5f9; }}
        .subtitle {{ color: #94a3b8; margin-bottom: 24px; font-size: 14px; }}
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 16px;
            margin-bottom: 32px;
        }}
        .kpi-card {{
            background: #1e293b;
            border-radius: 12px;
            padding: 20px;
            border: 1px solid #334155;
        }}
        .kpi-label {{
            font-size: 12px;
            color: #94a3b8;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 8px;
        }}
        .kpi-value {{
            font-size: 24px;
            font-weight: 700;
            color: #38bdf8;
        }}
        .kpi-value.negative {{ color: #f87171; }}
        .chart-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 24px;
        }}
        .chart-card {{
            background: #1e293b;
            border-radius: 12px;
            padding: 20px;
            border: 1px solid #334155;
        }}
        .chart-card.full-width {{ grid-column: 1 / -1; }}
        .chart-title {{
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 16px;
            color: #f1f5f9;
        }}
        canvas {{ width: 100% !important; }}
        @media (max-width: 768px) {{ .chart-grid {{ grid-template-columns: 1fr; }} }}
    </style>
</head>
<body>
<div class="dashboard">
    <h1>{scenario_name}</h1>
    <p class="subtitle">Financial Model Dashboard — Generated {date}</p>

    <div class="kpi-grid">
        {kpi_cards}
    </div>

    <div class="chart-grid">
        <div class="chart-card">
            <div class="chart-title">Revenue Timeline</div>
            <canvas id="revenue"></canvas>
        </div>
        <div class="chart-card">
            <div class="chart-title">P&amp;L Overview</div>
            <canvas id="pnl"></canvas>
        </div>
        <div class="chart-card">
            <div class="chart-title">Cash Flow</div>
            <canvas id="cashflow"></canvas>
        </div>
        <div class="chart-card">
            <div class="chart-title">DSCR vs Covenant (1.30x)</div>
            <canvas id="dscr"></canvas>
        </div>
        <div class="chart-card full-width">
            <div class="chart-title">Balance Sheet Evolution</div>
            <canvas id="balance"></canvas>
        </div>
    </div>
</div>

<script>
// ── Embedded data ──────────────────────────────────────────────────────────
const pnlData = {pnl_json};
const cashflowData = {cashflow_json};
const balanceData = {balance_json};
const debtMetrics = {debt_json};

const periods = Array.from({{length: pnlData.revenue.length}}, (_, i) => i + 1);

// ── Global Chart.js defaults ───────────────────────────────────────────────
Chart.defaults.color = '#94a3b8';
Chart.defaults.borderColor = '#334155';
Chart.defaults.plugins.legend.labels.usePointStyle = true;

const tickCurrencyK = v => v == null ? '' : '\\u20ac' + (v / 1000).toFixed(0) + 'k';
const tickCurrencyM = v => v == null ? '' : '\\u20ac' + (v / 1_000_000).toFixed(1) + 'M';
const scaleY = arr => {{
    const max = Math.max(...arr.filter(v => v != null));
    return max >= 500_000 ? tickCurrencyM : tickCurrencyK;
}};

const baseLineOptions = {{
    responsive: true,
    interaction: {{ mode: 'index', intersect: false }},
    plugins: {{ legend: {{ position: 'top' }} }},
    scales: {{
        y: {{ grid: {{ color: '#1e3256' }}, ticks: {{ callback: tickCurrencyK }} }},
        x: {{ grid: {{ display: false }}, ticks: {{ maxTicksLimit: 12 }} }},
    }},
}};

// ── 1. Revenue Timeline ────────────────────────────────────────────────────
new Chart(document.getElementById('revenue'), {{
    type: 'line',
    data: {{
        labels: periods,
        datasets: [{{
            label: 'Revenue',
            data: pnlData.revenue,
            borderColor: '#38bdf8',
            backgroundColor: 'rgba(56,189,248,0.12)',
            fill: true,
            tension: 0.35,
            pointRadius: 0,
        }}],
    }},
    options: {{
        ...baseLineOptions,
        scales: {{
            y: {{
                grid: {{ color: '#1e3256' }},
                ticks: {{ callback: scaleY(pnlData.revenue) }},
            }},
            x: {{ grid: {{ display: false }}, ticks: {{ maxTicksLimit: 12 }} }},
        }},
    }},
}});

// ── 2. P&L Stacked Lines ──────────────────────────────────────────────────
new Chart(document.getElementById('pnl'), {{
    type: 'line',
    data: {{
        labels: periods,
        datasets: [
            {{
                label: 'Revenue',
                data: pnlData.revenue,
                borderColor: '#38bdf8',
                backgroundColor: 'rgba(56,189,248,0.08)',
                fill: false,
                tension: 0.35,
                pointRadius: 0,
            }},
            {{
                label: 'Gross Profit',
                data: pnlData.gross_profit,
                borderColor: '#34d399',
                backgroundColor: 'rgba(52,211,153,0.08)',
                fill: false,
                tension: 0.35,
                pointRadius: 0,
            }},
            {{
                label: 'EBITDA',
                data: pnlData.ebitda,
                borderColor: '#a78bfa',
                backgroundColor: 'rgba(167,139,250,0.08)',
                fill: false,
                tension: 0.35,
                pointRadius: 0,
            }},
            {{
                label: 'Net Income',
                data: pnlData.net_income,
                borderColor: '#fb923c',
                backgroundColor: 'rgba(251,146,60,0.08)',
                fill: false,
                tension: 0.35,
                pointRadius: 0,
            }},
        ],
    }},
    options: {{
        ...baseLineOptions,
        scales: {{
            y: {{
                grid: {{ color: '#1e3256' }},
                ticks: {{ callback: scaleY([
                    ...(pnlData.revenue || []),
                    ...(pnlData.gross_profit || []),
                    ...(pnlData.ebitda || []),
                    ...(pnlData.net_income || []),
                ].filter(v => v != null)) }},
            }},
            x: {{ grid: {{ display: false }}, ticks: {{ maxTicksLimit: 12 }} }},
        }},
    }},
}});

// ── 3. Cash Flow Timeline ─────────────────────────────────────────────────
new Chart(document.getElementById('cashflow'), {{
    type: 'line',
    data: {{
        labels: periods,
        datasets: [
            {{
                label: 'Cumulative Cash',
                data: cashflowData.cash,
                borderColor: '#f1f5f9',
                backgroundColor: 'rgba(241,245,249,0.06)',
                fill: true,
                tension: 0.35,
                pointRadius: 0,
                borderWidth: 2.5,
                order: 0,
            }},
            {{
                label: 'CFO',
                data: cashflowData.cfo,
                borderColor: '#38bdf8',
                backgroundColor: 'transparent',
                tension: 0.35,
                pointRadius: 0,
                borderWidth: 1.5,
                order: 1,
            }},
            {{
                label: 'CFI',
                data: cashflowData.cfi,
                borderColor: '#f87171',
                backgroundColor: 'transparent',
                tension: 0.35,
                pointRadius: 0,
                borderWidth: 1.5,
                order: 2,
            }},
            {{
                label: 'CFF',
                data: cashflowData.cff,
                borderColor: '#fbbf24',
                backgroundColor: 'transparent',
                tension: 0.35,
                pointRadius: 0,
                borderWidth: 1.5,
                order: 3,
            }},
        ],
    }},
    options: {{
        ...baseLineOptions,
        scales: {{
            y: {{
                grid: {{ color: '#1e3256' }},
                ticks: {{ callback: scaleY((cashflowData.cash || []).filter(v => v != null)) }},
            }},
            x: {{ grid: {{ display: false }}, ticks: {{ maxTicksLimit: 12 }} }},
        }},
    }},
}});

// ── 4. DSCR Timeline ──────────────────────────────────────────────────────
const dscrSeries = (debtMetrics.dscr || []).map(v => (v == null || v > 20) ? null : v);
new Chart(document.getElementById('dscr'), {{
    type: 'line',
    data: {{
        labels: periods.slice(0, dscrSeries.length),
        datasets: [
            {{
                label: 'DSCR',
                data: dscrSeries,
                borderColor: '#34d399',
                backgroundColor: 'rgba(52,211,153,0.10)',
                fill: true,
                tension: 0.35,
                pointRadius: 0,
            }},
            {{
                label: 'Covenant (1.30x)',
                data: Array(dscrSeries.length).fill(1.30),
                borderColor: '#f87171',
                borderDash: [6, 4],
                pointRadius: 0,
                fill: false,
                borderWidth: 1.5,
            }},
        ],
    }},
    options: {{
        responsive: true,
        interaction: {{ mode: 'index', intersect: false }},
        plugins: {{ legend: {{ position: 'top' }} }},
        scales: {{
            y: {{
                grid: {{ color: '#1e3256' }},
                min: 0,
                ticks: {{ callback: v => v.toFixed(2) + 'x' }},
            }},
            x: {{ grid: {{ display: false }}, ticks: {{ maxTicksLimit: 12 }} }},
        }},
    }},
}});

// ── 5. Balance Sheet Evolution ────────────────────────────────────────────
new Chart(document.getElementById('balance'), {{
    type: 'line',
    data: {{
        labels: periods.slice(0, (balanceData.total_assets || []).length),
        datasets: [
            {{
                label: 'Total Assets',
                data: balanceData.total_assets,
                borderColor: '#38bdf8',
                backgroundColor: 'rgba(56,189,248,0.10)',
                fill: true,
                tension: 0.35,
                pointRadius: 0,
            }},
            {{
                label: 'Total Liabilities',
                data: balanceData.total_liabilities,
                borderColor: '#f87171',
                backgroundColor: 'rgba(248,113,113,0.10)',
                fill: true,
                tension: 0.35,
                pointRadius: 0,
            }},
            {{
                label: 'Equity',
                data: balanceData.equity,
                borderColor: '#34d399',
                backgroundColor: 'rgba(52,211,153,0.08)',
                fill: false,
                tension: 0.35,
                pointRadius: 0,
                borderWidth: 2.5,
            }},
        ],
    }},
    options: {{
        responsive: true,
        interaction: {{ mode: 'index', intersect: false }},
        plugins: {{ legend: {{ position: 'top' }} }},
        scales: {{
            y: {{
                grid: {{ color: '#1e3256' }},
                ticks: {{
                    callback: scaleY([
                        ...(balanceData.total_assets || []),
                        ...(balanceData.total_liabilities || []),
                    ].filter(v => v != null)),
                }},
            }},
            x: {{ grid: {{ display: false }}, ticks: {{ maxTicksLimit: 12 }} }},
        }},
    }},
}});
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_dashboard(
    results: dict[str, Any],
    scenario_name: str,
    output_path: str | None = None,
) -> dict[str, Any]:
    """Generate a self-contained HTML dashboard for scenario results.

    Args:
        results: Full scenario results dict (from run_scenario or get_results
                 with view="all").
        scenario_name: Name shown in the dashboard title.
        output_path: Optional file path.  If None, HTML is returned as string.

    Returns:
        {"html": str, "path": str | None, "charts": list[str]}
    """
    pnl = results.get("pnl", {}) or {}
    cashflow = results.get("cashflow", {}) or {}
    balance = results.get("balance", {}) or {}
    debt_metrics = results.get("debt_metrics", {}) or {}

    # Sanitise all series (inf/NaN → None → JSON null)
    pnl_clean = {
        "revenue": _clean_series(pnl.get("revenue", [])),
        "gross_profit": _clean_series(pnl.get("gross_profit", [])),
        "ebitda": _clean_series(pnl.get("ebitda", [])),
        "net_income": _clean_series(pnl.get("net_income", [])),
    }
    cashflow_clean = {
        "cfo": _clean_series(cashflow.get("cfo", [])),
        "cfi": _clean_series(cashflow.get("cfi", [])),
        "cff": _clean_series(cashflow.get("cff", [])),
        "cash": _clean_series(cashflow.get("cash", [])),
    }
    balance_clean = {
        "total_assets": _clean_series(balance.get("total_assets", [])),
        "total_liabilities": _clean_series(balance.get("total_liabilities", [])),
        "equity": _clean_series(balance.get("equity", [])),
    }
    debt_clean = {
        "dscr": _clean_series(debt_metrics.get("dscr", [])),
    }

    kpi_cards_html = _build_kpi_cards(results)
    date_str = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")

    html = _HTML_TEMPLATE.format(
        scenario_name=scenario_name,
        date=date_str,
        kpi_cards=kpi_cards_html,
        pnl_json=_safe_json(pnl_clean),
        cashflow_json=_safe_json(cashflow_clean),
        balance_json=_safe_json(balance_clean),
        debt_json=_safe_json(debt_clean),
    )

    if output_path is not None:
        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write(html)

    charts = ["revenue", "pnl", "cashflow", "dscr", "balance"]
    return {"html": html, "path": output_path, "charts": charts}


# ---------------------------------------------------------------------------
# MCP factory
# ---------------------------------------------------------------------------

def make_generate_dashboard(store: SQLiteScenarioStore) -> Any:
    """Return an MCP handler that loads results from the store and calls
    generate_dashboard."""

    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        scenario_id = args["scenario_id"]
        output_path: str | None = args.get("output_path")

        scenario = store.get(scenario_id)
        if scenario is None:
            return {"error": f"scenario_id {scenario_id!r} not found"}
        if not scenario.results_snapshot:
            return {
                "error": (
                    f"scenario {scenario_id!r} has no results — "
                    "call finance.simulate.run first"
                )
            }

        results = scenario.results_snapshot
        scenario_name = scenario.name

        result = generate_dashboard(results, scenario_name, output_path=output_path)

        # If no output_path was requested, trim the html from the MCP response
        # to avoid flooding the context — just confirm it was generated.
        if output_path is None:
            return {
                "scenario_id": scenario_id,
                "charts": result["charts"],
                "html_length": len(result["html"]),
                "html": result["html"],
            }
        return {
            "scenario_id": scenario_id,
            "path": result["path"],
            "charts": result["charts"],
        }

    return _handle
