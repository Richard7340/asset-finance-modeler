"""Tests for the professional financial report generator."""
from asset_finance_modeler.mcp_server.tools.report import generate_report


def _mock_results():
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
            "cogs": [0] * n,
            "opex": [70_000] * n,
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
            "icr": [3.0] * n,
            "leverage": [0.6] * n,
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


def _mock_resolved_inputs():
    return [
        {
            "field_path": "production.capacity_mwp",
            "value": 50,
            "source": "user",
            "provenance": "User @ 2026-05-25",
            "confidence": 1.0,
        },
        {
            "field_path": "capex.items[0].amount_per_unit",
            "value": 550,
            "source": "benchmark",
            "provenance": "Lazard LCOE v17.0",
            "confidence": 0.92,
        },
        {
            "field_path": "financing.max_leverage",
            "value": 0.75,
            "source": "preset",
            "provenance": "quick_start default",
            "confidence": 0.30,
        },
    ]


def test_report_returns_html():
    result = generate_report(_mock_results(), "Solar PV 50MW Test")
    assert "html" in result
    assert len(result["html"]) > 2000
    assert "sections" in result


def test_report_has_cover_page():
    result = generate_report(_mock_results(), "My Solar Project")
    assert "My Solar Project" in result["html"]
    assert "Financial Analysis Report" in result["html"]


def test_report_has_executive_summary():
    result = generate_report(_mock_results(), "Test")
    html = result["html"]
    assert "Executive Summary" in html


def test_report_has_kpis():
    result = generate_report(_mock_results(), "Test")
    html = result["html"]
    assert "IRR" in html or "irr" in html


def test_report_has_assumptions_table():
    result = generate_report(
        _mock_results(), "Test", resolved_inputs=_mock_resolved_inputs()
    )
    html = result["html"]
    assert "Assumptions" in html
    assert "Lazard" in html
    assert "conf-high" in html or "conf-medium" in html


def test_report_has_charts():
    result = generate_report(_mock_results(), "Test")
    html = result["html"]
    assert 'id="revenue"' in html or 'id="chart-revenue"' in html
    assert "Chart" in html


def test_report_has_disclaimer():
    result = generate_report(_mock_results(), "Test")
    assert "disclaimer" in result["html"].lower()
    assert "informational purposes" in result["html"].lower()


def test_report_writes_to_file(tmp_path):
    path = str(tmp_path / "report.html")
    result = generate_report(_mock_results(), "Test", output_path=path)
    assert result["path"] == path
    with open(path) as f:
        content = f.read()
    assert "<html" in content


def test_report_without_resolved_inputs():
    result = generate_report(_mock_results(), "Test")
    assert "html" in result


def test_report_without_project_kpis():
    results = _mock_results()
    del results["project_kpis"]
    result = generate_report(results, "SaaS Test")
    assert "html" in result


def test_report_has_annual_tables():
    result = generate_report(_mock_results(), "Test")
    html = result["html"]
    assert "table" in html.lower()
