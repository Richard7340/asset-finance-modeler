"""Tests for the dashboard artifact generator."""

import json
import math

from asset_finance_modeler.mcp_server.tools.dashboard import generate_dashboard

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _mock_results() -> dict:
    n = 60
    return {
        "summary": {
            "total_capex": 22_500_000,
            "revenue_y1": 3_200_000,
            "ebitda_margin_end": 0.65,
            "enterprise_value": 15_000_000,
            "irr_project": 0.085,
            "lcoe": 42.5,
        },
        "pnl": {
            "revenue": [270_000] * n,
            "gross_profit": [270_000] * n,
            "ebitda": [200_000] * n,
            "net_income": [120_000] * n,
        },
        "cashflow": {
            "cfo": [150_000] * n,
            "cfi": [-50_000] + [0] * (n - 1),
            "cff": [0] * n,
            "cash": [100_000 + i * 100_000 for i in range(n)],
        },
        "balance": {
            "total_assets": [20_000_000] * n,
            "total_liabilities": [12_000_000] * n,
            "equity": [8_000_000] * n,
        },
        "debt_metrics": {
            "dscr": [1.45] * n,
        },
        "project_kpis": {
            "irr_project": 0.085,
            "irr_equity": 0.12,
            "npv": 15_000_000,
            "lcoe": 42.5,
            "lcos": None,
            "payback_years": 8.5,
            "dscr_min": 1.32,
            "dscr_avg": 1.45,
        },
    }


# ---------------------------------------------------------------------------
# Core behaviour
# ---------------------------------------------------------------------------

def test_generate_dashboard_returns_html():
    result = generate_dashboard(_mock_results(), "Solar PV 50MW Test")
    assert "html" in result
    assert "charts" in result
    assert len(result["html"]) > 1000
    assert "chart.js" in result["html"].lower()


def test_dashboard_contains_scenario_name():
    result = generate_dashboard(_mock_results(), "My Solar Project")
    assert "My Solar Project" in result["html"]


def test_dashboard_contains_kpis():
    result = generate_dashboard(_mock_results(), "Test")
    html = result["html"]
    # Total CAPEX = 22_500_000 → formatted as €22.5M
    assert "22.5" in html or "22,500,000" in html
    # LCOE = 42.5
    assert "42.5" in html


def test_dashboard_has_chart_canvases():
    result = generate_dashboard(_mock_results(), "Test")
    html = result["html"]
    assert 'id="revenue"' in html
    assert 'id="pnl"' in html
    assert 'id="cashflow"' in html
    assert 'id="dscr"' in html
    assert 'id="balance"' in html


def test_dashboard_charts_list():
    result = generate_dashboard(_mock_results(), "Test")
    assert set(result["charts"]) == {"revenue", "pnl", "cashflow", "dscr", "balance"}


def test_dashboard_path_none_by_default():
    result = generate_dashboard(_mock_results(), "Test")
    assert result["path"] is None


def test_dashboard_writes_to_file(tmp_path):
    path = str(tmp_path / "dashboard.html")
    result = generate_dashboard(_mock_results(), "Test", output_path=path)
    assert result["path"] == path
    with open(path, encoding="utf-8") as f:
        content = f.read()
    assert "<html" in content
    assert "Test" in content


def test_dashboard_file_content_matches_returned_html(tmp_path):
    path = str(tmp_path / "dash.html")
    result = generate_dashboard(_mock_results(), "FileCheck", output_path=path)
    with open(path, encoding="utf-8") as f:
        on_disk = f.read()
    assert on_disk == result["html"]


# ---------------------------------------------------------------------------
# Robustness
# ---------------------------------------------------------------------------

def test_dashboard_without_project_kpis():
    """Omitting project_kpis should not raise."""
    results = _mock_results()
    del results["project_kpis"]
    result = generate_dashboard(results, "SaaS Test")
    assert "html" in result
    assert "SaaS Test" in result["html"]


def test_dashboard_without_debt_metrics():
    results = _mock_results()
    del results["debt_metrics"]
    result = generate_dashboard(results, "No Debt")
    assert "html" in result


def test_dashboard_empty_series():
    """Empty series (no data yet) should produce valid HTML, not crash."""
    results = {
        "summary": {},
        "pnl": {"revenue": [], "gross_profit": [], "ebitda": [], "net_income": []},
        "cashflow": {"cfo": [], "cfi": [], "cff": [], "cash": []},
        "balance": {"total_assets": [], "total_liabilities": [], "equity": []},
        "debt_metrics": {"dscr": []},
    }
    result = generate_dashboard(results, "Empty")
    assert "html" in result
    assert len(result["html"]) > 500


def test_dashboard_inf_values_produce_valid_json():
    """Infinite DSCR values must be serialised as JSON null, not break the HTML."""
    results = _mock_results()
    results["debt_metrics"]["dscr"] = [math.inf] * 60
    result = generate_dashboard(results, "Inf Test")
    # The HTML must not contain literal 'Infinity' (that's invalid JSON)
    assert "Infinity" not in result["html"]
    # Find the JSON blob and verify it parses
    start = result["html"].find("const debtMetrics = ") + len("const debtMetrics = ")
    end = result["html"].find(";\n", start)
    parsed = json.loads(result["html"][start:end])
    assert all(v is None for v in parsed["dscr"])


def test_dashboard_is_self_contained():
    """No local resource references — only the CDN script tag is external."""
    result = generate_dashboard(_mock_results(), "SelfContained")
    html = result["html"]
    # Should not reference any relative paths for scripts/styles
    assert 'src="/' not in html
    assert "require(" not in html
    # Must include the CDN Chart.js reference
    assert "cdn.jsdelivr.net/npm/chart.js" in html


def test_dashboard_data_embedded_as_json():
    """P&L data must be embedded as valid JSON inside the HTML."""
    n = 60
    results = _mock_results()
    result = generate_dashboard(results, "DataEmbed")
    html = result["html"]

    marker = "const pnlData = "
    start = html.find(marker) + len(marker)
    end = html.find(";\n", start)
    parsed = json.loads(html[start:end])
    assert parsed["revenue"] == [270_000] * n
    assert parsed["ebitda"] == [200_000] * n
