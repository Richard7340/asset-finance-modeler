"""End-to-end test: MCP flow for infrastructure models.

list_models → load_baseline → run → get_results → dashboard
"""
import pytest

from asset_finance_modeler.mcp_server.registry import build_registry
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore


@pytest.fixture()
def registry(tmp_path):
    store = SQLiteScenarioStore(str(tmp_path / "e2e.db"))
    store.initialize()
    return build_registry(store)


def test_e2e_solar_pv_mcp_flow(registry, tmp_path):
    """Full MCP flow: list → load → run → results → dashboard."""
    # 1. List models — should include infrastructure
    list_result = registry["finance.simulate.list_models"].handler({})
    model_names = [m["name"] for m in list_result["models"]]
    assert "solar_pv_50mw_spain" in model_names

    # 2. Load baseline
    load_result = registry["finance.simulate.load_baseline"].handler({
        "model": "solar_pv_50mw_spain",
        "preset": "solar_pv_50mw_spain",
    })
    assert "scenario_id" in load_result
    scenario_id = load_result["scenario_id"]

    # 3. Run scenario
    run_result = registry["finance.simulate.run"].handler({
        "scenario_id": scenario_id,
    })
    assert "error" not in run_result
    assert "summary" in run_result

    # 4. Get results — full view
    results = registry["finance.simulate.get_results"].handler({
        "scenario_id": scenario_id,
        "view": "all",
    })
    assert "pnl" in results
    assert "cashflow" in results
    assert "balance" in results
    assert len(results["pnl"]["revenue"]) > 0

    # 5. Generate dashboard
    dashboard_path = str(tmp_path / "solar_dashboard.html")
    dash_result = registry["finance.dashboard.generate"].handler({
        "scenario_id": scenario_id,
        "output_path": dashboard_path,
    })
    assert "error" not in dash_result
    assert dash_result.get("path") == dashboard_path

    # Verify HTML file exists and is valid
    with open(dashboard_path) as f:
        html = f.read()
    assert "<html" in html
    assert "Chart" in html
    assert "Solar" in html or "solar" in html


def test_e2e_bess_mcp_flow(registry, tmp_path):
    """BESS model through MCP."""
    load_result = registry["finance.simulate.load_baseline"].handler({
        "preset": "bess_20mw_4h",
    })
    scenario_id = load_result["scenario_id"]

    run_result = registry["finance.simulate.run"].handler({
        "scenario_id": scenario_id,
    })
    assert "error" not in run_result
    assert "summary" in run_result

    # Get summary view
    summary = registry["finance.simulate.get_results"].handler({
        "scenario_id": scenario_id,
        "view": "summary",
    })
    assert "summary" in summary


def test_e2e_saas_still_works(registry):
    """SaaS models still work through the updated MCP."""
    load_result = registry["finance.simulate.load_baseline"].handler({
        "preset": "gestnova",
    })
    scenario_id = load_result["scenario_id"]

    run_result = registry["finance.simulate.run"].handler({
        "scenario_id": scenario_id,
    })
    assert "error" not in run_result
    assert "summary" in run_result
