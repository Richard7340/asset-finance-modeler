"""Professional financial report generator.

Generates a self-contained, print-ready HTML report with Chart.js charts,
an executive summary, assumptions table, detailed financial tables, and a
disclaimer.  Designed to look like what a financial advisor would present
to a client.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from asset_finance_modeler.mcp_server.tools.dashboard import (
    _clean_series,
    _fmt_currency,
    _fmt_pct,
    _safe_json,
)
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CONF_HIGH_THRESHOLD: float = 0.80
_CONF_MEDIUM_THRESHOLD: float = 0.50

# ---------------------------------------------------------------------------
# Extra formatters
# ---------------------------------------------------------------------------


def _fmt_num(value: float | None, *, decimals: int = 2) -> str:
    if value is None:
        return "—"
    if not math.isfinite(value):
        return "—"
    return f"{value:.{decimals}f}"


def _annual_labels(n_months: int) -> list[str]:
    """Return year labels Y1, Y2, … for annual table (every 12 periods)."""
    years = n_months // 12
    return [f"Y{y + 1}" for y in range(years)]


def _annual_avg(series: list[float | None], n_months: int) -> list[float | None]:
    """Compute annual totals (sum per year) for a monthly series."""
    years = n_months // 12
    result: list[float | None] = []
    for y in range(years):
        chunk = series[y * 12 : (y + 1) * 12]
        valid = [v for v in chunk if v is not None]
        result.append(sum(valid) if valid else None)
    return result


def _annual_last(series: list[float | None], n_months: int) -> list[float | None]:
    """Take the last value in each year (for balance-sheet style metrics)."""
    years = n_months // 12
    result: list[float | None] = []
    for y in range(years):
        chunk = series[y * 12 : (y + 1) * 12]
        valid = [v for v in chunk if v is not None]
        result.append(valid[-1] if valid else None)
    return result


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------


def _build_cover(scenario_name: str, date_str: str) -> str:
    return f"""\
    <div class="cover">
        <div class="cover-inner">
            <div class="cover-logo">Asset Finance Modeler</div>
            <h1>{scenario_name}</h1>
            <div class="subtitle">Financial Analysis Report</div>
            <div class="date">{date_str}</div>
            <div class="branding">Prepared with Asset Finance Modeler</div>
        </div>
    </div>"""


def _build_executive_summary(
    results: dict[str, Any], scenario_name: str
) -> str:
    summary = results.get("summary", {}) or {}
    kpis = results.get("project_kpis", {}) or {}

    total_capex = summary.get("total_capex")
    ev = summary.get("enterprise_value")
    irr_p = kpis.get("irr_project") or summary.get("irr_project")
    irr_e = kpis.get("irr_equity")
    ebitda_m = summary.get("ebitda_margin_end")
    revenue_y1 = summary.get("revenue_y1")
    lcoe = kpis.get("lcoe") or summary.get("lcoe")
    dscr_min = kpis.get("dscr_min")
    payback = kpis.get("payback_years")

    # Narrative
    irr_str = f"{irr_p * 100:.1f}%" if irr_p is not None else "N/A"
    ev_str = _fmt_currency(ev) if ev is not None else "N/A"
    narrative = (
        f"This report presents a financial analysis of <strong>{scenario_name}</strong>. "
        f"The project generates an estimated IRR of <strong>{irr_str}</strong> "
        f"with an enterprise value of <strong>{ev_str}</strong>. "
        f"Results are based on the assumptions detailed in the Assumptions section below "
        f"and should be reviewed in conjunction with the Disclaimer."
    )

    # KPI cards
    kpi_defs: list[tuple[str, str]] = [
        ("Total CAPEX", _fmt_currency(total_capex)),
        ("Revenue Y1", _fmt_currency(revenue_y1)),
        ("EBITDA Margin", _fmt_pct(ebitda_m)),
        ("Enterprise Value", _fmt_currency(ev)),
        ("IRR Project", _fmt_pct(irr_p)),
        ("IRR Equity", _fmt_pct(irr_e)),
    ]
    if lcoe is not None:
        kpi_defs.append(("LCOE", f"€{lcoe:.1f}/MWh"))
    if dscr_min is not None:
        kpi_defs.append(("DSCR Min", f"{dscr_min:.2f}x"))
    if payback is not None:
        kpi_defs.append(("Payback", f"{payback:.1f} yrs"))

    cards_html = ""
    for label, value in kpi_defs:
        cards_html += f"""\
            <div class="kpi-card">
                <div class="kpi-label">{label}</div>
                <div class="kpi-value">{value}</div>
            </div>
"""

    return f"""\
    <div class="section">
        <div class="section-title">Executive Summary</div>
        <p class="narrative">{narrative}</p>
        <div class="kpi-grid">
{cards_html}        </div>
    </div>"""


def _conf_class(confidence: float | None) -> str:
    if confidence is None:
        return ""
    if confidence > _CONF_HIGH_THRESHOLD:
        return "conf-high"
    if confidence >= _CONF_MEDIUM_THRESHOLD:
        return "conf-medium"
    return "conf-low"


def _build_assumptions(
    resolved_inputs: list[dict] | None,
    results: dict[str, Any],
) -> str:
    rows_html = ""

    if resolved_inputs:
        for inp in resolved_inputs:
            field = inp.get("field_path", "")
            value = inp.get("value", "")
            source = inp.get("source", "")
            provenance = inp.get("provenance", "")
            confidence = inp.get("confidence")
            conf_pct = f"{confidence * 100:.0f}%" if confidence is not None else "—"
            cls = _conf_class(confidence)
            rows_html += f"""\
            <tr>
                <td><code>{field}</code></td>
                <td>{value}</td>
                <td>{source}</td>
                <td>{provenance}</td>
                <td class="{cls}">{conf_pct}</td>
            </tr>
"""
    else:
        # Fallback: try inputs_resolved or raw summary as key-value pairs
        inputs = results.get("inputs_resolved") or results.get("summary") or {}
        if isinstance(inputs, dict):
            for key, val in inputs.items():
                if val is None:
                    continue
                rows_html += f"""\
            <tr>
                <td><code>{key}</code></td>
                <td>{val}</td>
                <td>—</td>
                <td>—</td>
                <td>—</td>
            </tr>
"""

    if not rows_html:
        rows_html = '<tr><td colspan="5" style="color:#9ca3af;">No assumptions data available.</td></tr>'

    return f"""\
    <div class="section">
        <div class="section-title">Assumptions</div>
        <p class="narrative">
            Confidence legend:
            <span class="conf-high">&#9632; High (&gt;80%)</span>
            &nbsp;
            <span class="conf-medium">&#9632; Medium (50-80%)</span>
            &nbsp;
            <span class="conf-low">&#9632; Low (&lt;50%)</span>
        </p>
        <table>
            <thead>
                <tr>
                    <th>Field</th>
                    <th>Value</th>
                    <th>Source</th>
                    <th>Provenance</th>
                    <th>Confidence</th>
                </tr>
            </thead>
            <tbody>
{rows_html}            </tbody>
        </table>
    </div>"""


def _build_charts_section(results: dict[str, Any]) -> str:
    """Return the charts div with embedded Chart.js."""
    pnl = results.get("pnl", {}) or {}
    cashflow = results.get("cashflow", {}) or {}
    balance = results.get("balance", {}) or {}
    debt_metrics = results.get("debt_metrics", {}) or {}

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

    embedded_data = f"""\
const pnlData = {_safe_json(pnl_clean)};
const cashflowData = {_safe_json(cashflow_clean)};
const balanceData = {_safe_json(balance_clean)};
const debtMetrics = {_safe_json(debt_clean)};"""

    charts_html = """\
    <div class="section charts-section">
        <div class="section-title">Charts</div>
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
            <div class="chart-card full">
                <div class="chart-title">Balance Sheet Evolution</div>
                <canvas id="balance"></canvas>
            </div>
        </div>
    </div>"""

    charts_js = f"""\
<script>
// ── Embedded data ──────────────────────────────────────────────────────────
{embedded_data}

const periods = Array.from({{length: pnlData.revenue.length}}, (_, i) => i + 1);

// ── Color palette (professional blue) ─────────────────────────────────────
const COLORS = {{
    primary: '#3b82f6',
    secondary: '#10b981',
    tertiary: '#f59e0b',
    danger: '#ef4444',
    purple: '#8b5cf6',
    gray: '#6b7280',
    light: '#e5e7eb',
}};

// ── Global Chart.js defaults ───────────────────────────────────────────────
Chart.defaults.color = '#374151';
Chart.defaults.borderColor = '#e5e7eb';
Chart.defaults.plugins.legend.labels.usePointStyle = true;
Chart.defaults.plugins.legend.labels.font = {{ size: 11 }};

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
        y: {{ grid: {{ color: '#f1f5f9' }}, ticks: {{ callback: tickCurrencyK, font: {{ size: 10 }} }} }},
        x: {{ grid: {{ display: false }}, ticks: {{ maxTicksLimit: 12, font: {{ size: 10 }} }} }},
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
            borderColor: COLORS.primary,
            backgroundColor: 'rgba(59,130,246,0.10)',
            fill: true,
            tension: 0.35,
            pointRadius: 0,
        }}],
    }},
    options: {{
        ...baseLineOptions,
        scales: {{
            y: {{
                grid: {{ color: '#f1f5f9' }},
                ticks: {{ callback: scaleY(pnlData.revenue), font: {{ size: 10 }} }},
            }},
            x: {{ grid: {{ display: false }}, ticks: {{ maxTicksLimit: 12, font: {{ size: 10 }} }} }},
        }},
    }},
}});

// ── 2. P&L Overview ───────────────────────────────────────────────────────
new Chart(document.getElementById('pnl'), {{
    type: 'line',
    data: {{
        labels: periods,
        datasets: [
            {{
                label: 'Revenue',
                data: pnlData.revenue,
                borderColor: COLORS.primary,
                fill: false,
                tension: 0.35,
                pointRadius: 0,
            }},
            {{
                label: 'Gross Profit',
                data: pnlData.gross_profit,
                borderColor: COLORS.secondary,
                fill: false,
                tension: 0.35,
                pointRadius: 0,
            }},
            {{
                label: 'EBITDA',
                data: pnlData.ebitda,
                borderColor: COLORS.purple,
                fill: false,
                tension: 0.35,
                pointRadius: 0,
            }},
            {{
                label: 'Net Income',
                data: pnlData.net_income,
                borderColor: COLORS.tertiary,
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
                grid: {{ color: '#f1f5f9' }},
                ticks: {{ callback: scaleY([
                    ...(pnlData.revenue || []),
                    ...(pnlData.gross_profit || []),
                    ...(pnlData.ebitda || []),
                    ...(pnlData.net_income || []),
                ].filter(v => v != null)), font: {{ size: 10 }} }},
            }},
            x: {{ grid: {{ display: false }}, ticks: {{ maxTicksLimit: 12, font: {{ size: 10 }} }} }},
        }},
    }},
}});

// ── 3. Cash Flow ──────────────────────────────────────────────────────────
new Chart(document.getElementById('cashflow'), {{
    type: 'line',
    data: {{
        labels: periods,
        datasets: [
            {{
                label: 'Cumulative Cash',
                data: cashflowData.cash,
                borderColor: '#1e40af',
                backgroundColor: 'rgba(30,64,175,0.08)',
                fill: true,
                tension: 0.35,
                pointRadius: 0,
                borderWidth: 2.5,
                order: 0,
            }},
            {{
                label: 'CFO',
                data: cashflowData.cfo,
                borderColor: COLORS.primary,
                fill: false,
                tension: 0.35,
                pointRadius: 0,
                borderWidth: 1.5,
                order: 1,
            }},
            {{
                label: 'CFI',
                data: cashflowData.cfi,
                borderColor: COLORS.danger,
                fill: false,
                tension: 0.35,
                pointRadius: 0,
                borderWidth: 1.5,
                order: 2,
            }},
            {{
                label: 'CFF',
                data: cashflowData.cff,
                borderColor: COLORS.tertiary,
                fill: false,
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
                grid: {{ color: '#f1f5f9' }},
                ticks: {{ callback: scaleY((cashflowData.cash || []).filter(v => v != null)), font: {{ size: 10 }} }},
            }},
            x: {{ grid: {{ display: false }}, ticks: {{ maxTicksLimit: 12, font: {{ size: 10 }} }} }},
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
                borderColor: COLORS.secondary,
                backgroundColor: 'rgba(16,185,129,0.10)',
                fill: true,
                tension: 0.35,
                pointRadius: 0,
            }},
            {{
                label: 'Covenant (1.30x)',
                data: Array(dscrSeries.length).fill(1.30),
                borderColor: COLORS.danger,
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
                grid: {{ color: '#f1f5f9' }},
                min: 0,
                ticks: {{ callback: v => v.toFixed(2) + 'x', font: {{ size: 10 }} }},
            }},
            x: {{ grid: {{ display: false }}, ticks: {{ maxTicksLimit: 12, font: {{ size: 10 }} }} }},
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
                borderColor: COLORS.primary,
                backgroundColor: 'rgba(59,130,246,0.08)',
                fill: true,
                tension: 0.35,
                pointRadius: 0,
            }},
            {{
                label: 'Total Liabilities',
                data: balanceData.total_liabilities,
                borderColor: COLORS.danger,
                backgroundColor: 'rgba(239,68,68,0.08)',
                fill: true,
                tension: 0.35,
                pointRadius: 0,
            }},
            {{
                label: 'Equity',
                data: balanceData.equity,
                borderColor: COLORS.secondary,
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
                grid: {{ color: '#f1f5f9' }},
                ticks: {{
                    callback: scaleY([
                        ...(balanceData.total_assets || []),
                        ...(balanceData.total_liabilities || []),
                    ].filter(v => v != null)),
                    font: {{ size: 10 }},
                }},
            }},
            x: {{ grid: {{ display: false }}, ticks: {{ maxTicksLimit: 12, font: {{ size: 10 }} }} }},
        }},
    }},
}});
</script>"""

    return charts_html, charts_js


def _build_pnl_table(pnl: dict[str, Any]) -> str:
    n = len(pnl.get("revenue", []))
    if n == 0:
        return ""

    revenue_c = _clean_series(pnl.get("revenue", []))
    cogs_c = _clean_series(pnl.get("cogs", []))
    gross_c = _clean_series(pnl.get("gross_profit", []))
    opex_c = _clean_series(pnl.get("opex", []))
    ebitda_c = _clean_series(pnl.get("ebitda", []))
    net_c = _clean_series(pnl.get("net_income", []))

    # Annual data
    years = n // 12
    if years == 0:
        # treat as 1 period per year (quarterly or annual model)
        years = min(n, 10)
        revenue_a = revenue_c[:years]
        cogs_a = cogs_c[:years]
        gross_a = gross_c[:years]
        opex_a = opex_c[:years]
        ebitda_a = ebitda_c[:years]
        net_a = net_c[:years]
    else:
        revenue_a = _annual_avg(revenue_c, n)
        cogs_a = _annual_avg(cogs_c, n)
        gross_a = _annual_avg(gross_c, n)
        opex_a = _annual_avg(opex_c, n)
        ebitda_a = _annual_avg(ebitda_c, n)
        net_a = _annual_avg(net_c, n)

    display_years = min(len(revenue_a), 10)
    labels = [f"Y{y + 1}" for y in range(display_years)]

    header = "".join(f"<th>{lbl}</th>" for lbl in labels)

    def row(label: str, series: list[float | None], bold: bool = False) -> str:
        cells = "".join(
            f"<td>{_fmt_currency(v)}</td>" for v in series[:display_years]
        )
        tag = "strong" if bold else "span"
        return f"<tr><td><{tag}>{label}</{tag}></td>{cells}</tr>\n"

    rows = (
        row("Revenue", revenue_a, bold=True)
        + row("COGS", cogs_a)
        + row("Gross Profit", gross_a, bold=True)
        + row("OPEX", opex_a)
        + row("EBITDA", ebitda_a, bold=True)
        + row("Net Income", net_a, bold=True)
    )

    return f"""\
    <div class="section">
        <div class="section-title">P&amp;L Summary (Annual)</div>
        <table>
            <thead>
                <tr><th>Line Item</th>{header}</tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
    </div>"""


def _build_cashflow_table(cashflow: dict[str, Any]) -> str:
    n = len(cashflow.get("cfo", []))
    if n == 0:
        return ""

    cfo_c = _clean_series(cashflow.get("cfo", []))
    cfi_c = _clean_series(cashflow.get("cfi", []))
    cff_c = _clean_series(cashflow.get("cff", []))
    cash_c = _clean_series(cashflow.get("cash", []))

    years = n // 12
    if years == 0:
        years = min(n, 10)
        cfo_a, cfi_a, cff_a = cfo_c[:years], cfi_c[:years], cff_c[:years]
        cash_a = cash_c[:years]
    else:
        cfo_a = _annual_avg(cfo_c, n)
        cfi_a = _annual_avg(cfi_c, n)
        cff_a = _annual_avg(cff_c, n)
        cash_a = _annual_last(cash_c, n)

    display_years = min(len(cfo_a), 10)
    labels = [f"Y{y + 1}" for y in range(display_years)]
    header = "".join(f"<th>{lbl}</th>" for lbl in labels)

    def row(label: str, series: list[float | None], bold: bool = False) -> str:
        cells = "".join(
            f"<td>{_fmt_currency(v)}</td>" for v in series[:display_years]
        )
        tag = "strong" if bold else "span"
        return f"<tr><td><{tag}>{label}</{tag}></td>{cells}</tr>\n"

    rows = (
        row("CFO", cfo_a, bold=True)
        + row("CFI", cfi_a)
        + row("CFF", cff_a)
        + row("Ending Cash", cash_a, bold=True)
    )

    return f"""\
    <div class="section">
        <div class="section-title">Cash Flow Summary (Annual)</div>
        <table>
            <thead>
                <tr><th>Line Item</th>{header}</tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
    </div>"""


def _build_debt_table(debt_metrics: dict[str, Any]) -> str:
    if not debt_metrics:
        return ""
    dscr = _clean_series(debt_metrics.get("dscr", []))
    icr = _clean_series(debt_metrics.get("icr", []))
    leverage = _clean_series(debt_metrics.get("leverage", []))

    n = len(dscr)
    if n == 0:
        return ""

    years = n // 12
    if years == 0:
        years = min(n, 10)
        dscr_a = dscr[:years]
        icr_a = icr[:years]
        lev_a = leverage[:years]
    else:
        dscr_a = _annual_last(dscr, n)
        icr_a = _annual_last(icr, n)
        lev_a = _annual_last(leverage, n)

    display_years = min(len(dscr_a), 10)
    labels = [f"Y{y + 1}" for y in range(display_years)]
    header = "".join(f"<th>{lbl}</th>" for lbl in labels)

    def row(label: str, series: list[float | None], fmt: Any = _fmt_num) -> str:
        cells = "".join(f"<td>{fmt(v)}</td>" for v in series[:display_years])
        return f"<tr><td>{label}</td>{cells}</tr>\n"

    rows = (
        row("DSCR", dscr_a, fmt=lambda v: _fmt_num(v) + "x" if v is not None else "—")
        + row("ICR", icr_a, fmt=lambda v: _fmt_num(v) + "x" if v is not None else "—")
        + row("Leverage", lev_a, fmt=lambda v: _fmt_pct(v) if v is not None else "—")
    )

    return f"""\
    <div class="section">
        <div class="section-title">Debt Metrics (Annual)</div>
        <table>
            <thead>
                <tr><th>Metric</th>{header}</tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
    </div>"""


def _build_disclaimer() -> str:
    return """\
    <div class="section">
        <div class="section-title">Disclaimer</div>
        <div class="disclaimer">
            This report is generated automatically and is for informational purposes only.
            It does not constitute financial, legal, or investment advice. The projections
            and metrics presented herein are based on modelled assumptions and historical
            benchmarks; actual results may differ materially. Inputs marked as
            &ldquo;benchmark&rdquo; are estimates derived from third-party sources and should
            be independently verified before any investment decision is made. Past
            performance is not indicative of future results. Asset Finance Modeler and its
            contributors accept no liability for decisions taken on the basis of this report.
        </div>
    </div>"""


# ---------------------------------------------------------------------------
# CSS and HTML skeleton
# ---------------------------------------------------------------------------

_CSS = """\
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #ffffff;
    color: #1a1a2e;
    padding: 40px;
    line-height: 1.6;
}
.report { max-width: 1100px; margin: 0 auto; }

/* Cover */
.cover {
    display: flex;
    align-items: center;
    justify-content: center;
    text-align: center;
    padding: 120px 40px;
    page-break-after: always;
    min-height: 60vh;
}
.cover-logo {
    font-size: 13px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 2px;
    color: #3b82f6;
    margin-bottom: 40px;
}
.cover h1 { font-size: 36px; color: #1a1a2e; margin-bottom: 12px; font-weight: 800; }
.cover .subtitle { font-size: 20px; color: #6b7280; margin-bottom: 24px; }
.cover .date { font-size: 14px; color: #9ca3af; margin-top: 12px; }
.cover .branding { font-size: 12px; color: #d1d5db; margin-top: 60px; }

/* Narrative text */
.narrative { color: #374151; margin-bottom: 24px; font-size: 14px; }

/* Sections */
.section { margin-bottom: 48px; }
.section-title {
    font-size: 22px;
    font-weight: 700;
    color: #1a1a2e;
    border-bottom: 2px solid #3b82f6;
    padding-bottom: 8px;
    margin-bottom: 24px;
}

/* KPI Cards */
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 16px;
    margin-bottom: 32px;
}
.kpi-card {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 16px;
    text-align: center;
}
.kpi-label {
    font-size: 11px;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.kpi-value {
    font-size: 22px;
    font-weight: 700;
    color: #1e40af;
    margin-top: 4px;
}

/* Tables */
table { width: 100%; border-collapse: collapse; font-size: 13px; margin-bottom: 24px; }
th {
    background: #f1f5f9;
    color: #374151;
    font-weight: 600;
    text-align: left;
    padding: 10px 12px;
    border-bottom: 2px solid #e2e8f0;
}
td { padding: 8px 12px; border-bottom: 1px solid #f1f5f9; }
tr:hover { background: #f8fafc; }
code { font-size: 12px; background: #f1f5f9; padding: 1px 4px; border-radius: 3px; }

/* Confidence colors */
.conf-high { color: #059669; font-weight: 600; }
.conf-medium { color: #d97706; font-weight: 600; }
.conf-low { color: #dc2626; font-weight: 600; }

/* Charts */
.chart-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 24px;
    margin-bottom: 32px;
}
.chart-card {
    background: #fafafa;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 20px;
}
.chart-card.full { grid-column: 1 / -1; }
.chart-title { font-size: 14px; font-weight: 600; margin-bottom: 12px; color: #374151; }
canvas { width: 100% !important; }

/* Disclaimer */
.disclaimer {
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 20px;
    font-size: 11px;
    color: #6b7280;
    line-height: 1.5;
}

/* Print */
@media print {
    body { padding: 20px; }
    .chart-grid { grid-template-columns: repeat(2, 1fr); }
    .kpi-grid { grid-template-columns: repeat(4, 1fr); }
    .section { page-break-inside: avoid; }
    .cover { page-break-after: always; }
    .charts-section { page-break-before: always; }
}

@media (max-width: 768px) {
    .chart-grid { grid-template-columns: 1fr; }
    .kpi-grid { grid-template-columns: repeat(2, 1fr); }
}
"""


def _build_html(
    scenario_name: str,
    date_str: str,
    cover_html: str,
    exec_summary_html: str,
    assumptions_html: str,
    charts_section_html: str,
    pnl_table_html: str,
    cashflow_table_html: str,
    debt_table_html: str,
    disclaimer_html: str,
    charts_js: str,
) -> str:
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{scenario_name} — Financial Analysis Report</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
    <style>
{_CSS}
    </style>
</head>
<body>
<div class="report">
{cover_html}
{exec_summary_html}
{assumptions_html}
{charts_section_html}
{pnl_table_html}
{cashflow_table_html}
{debt_table_html}
{disclaimer_html}
</div>
{charts_js}
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_report(
    results: dict[str, Any],
    scenario_name: str,
    output_path: str | None = None,
    resolved_inputs: list[dict] | None = None,
) -> dict[str, Any]:
    """Generate a professional financial analysis report.

    Args:
        results: Full scenario results (from run with view="all").
        scenario_name: Project name for the cover page.
        output_path: File path. If None, returns HTML string only.
        resolved_inputs: List of ResolvedInput dicts (from wizard finalize)
            for assumptions table. Each dict should have: field_path, value,
            source, provenance, confidence.

    Returns:
        {"html": str, "path": str | None, "sections": list[str]}
    """
    date_str = datetime.now(tz=UTC).strftime("%Y-%m-%d")

    cover_html = _build_cover(scenario_name, date_str)
    exec_summary_html = _build_executive_summary(results, scenario_name)
    assumptions_html = _build_assumptions(resolved_inputs, results)
    charts_section_html, charts_js = _build_charts_section(results)

    pnl = results.get("pnl", {}) or {}
    cashflow = results.get("cashflow", {}) or {}
    debt_metrics = results.get("debt_metrics", {}) or {}

    pnl_table_html = _build_pnl_table(pnl)
    cashflow_table_html = _build_cashflow_table(cashflow)
    debt_table_html = _build_debt_table(debt_metrics)
    disclaimer_html = _build_disclaimer()

    html = _build_html(
        scenario_name=scenario_name,
        date_str=date_str,
        cover_html=cover_html,
        exec_summary_html=exec_summary_html,
        assumptions_html=assumptions_html,
        charts_section_html=charts_section_html,
        pnl_table_html=pnl_table_html,
        cashflow_table_html=cashflow_table_html,
        debt_table_html=debt_table_html,
        disclaimer_html=disclaimer_html,
        charts_js=charts_js,
    )

    if output_path is not None:
        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write(html)

    sections = [
        "cover",
        "executive_summary",
        "assumptions",
        "charts",
        "pnl_table",
        "cashflow_table",
        "disclaimer",
    ]
    if debt_table_html:
        sections.insert(-1, "debt_table")

    return {"html": html, "path": output_path, "sections": sections}


# ---------------------------------------------------------------------------
# MCP factory
# ---------------------------------------------------------------------------


def make_generate_report(store: SQLiteScenarioStore) -> Any:
    """Return an MCP handler that loads results from the store and calls
    generate_report."""

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

        # Try to get resolved_inputs from the scenario metadata if present
        resolved_inputs: list[dict] | None = None
        meta = getattr(scenario, "metadata", None) or {}
        if isinstance(meta, dict):
            resolved_inputs = meta.get("resolved_inputs")

        result = generate_report(
            results,
            scenario_name,
            output_path=output_path,
            resolved_inputs=resolved_inputs,
        )

        if output_path is None:
            return {
                "scenario_id": scenario_id,
                "sections": result["sections"],
                "html_length": len(result["html"]),
                "html": result["html"],
            }
        return {
            "scenario_id": scenario_id,
            "path": result["path"],
            "sections": result["sections"],
        }

    return _handle
