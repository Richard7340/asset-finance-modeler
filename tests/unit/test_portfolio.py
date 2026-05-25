import pytest
from asset_finance_modeler.core.portfolio import analyze_portfolio, PortfolioAnalysis


def _solar_scenario():
    return {"id": "scn-1", "name": "Solar Sevilla", "base_model": "solar_pv",
            "summary": {"total_capex": 22_000_000, "revenue_y1": 3_200_000,
                        "enterprise_value": 15_000_000, "irr_project": 0.085},
            "project_kpis": {"irr_equity": 0.12, "dscr_min": 1.32, "lcoe": 42.5, "payback_years": 8.5}}


def _bess_scenario():
    return {"id": "scn-2", "name": "BESS Madrid", "base_model": "bess",
            "summary": {"total_capex": 18_000_000, "revenue_y1": 2_800_000,
                        "enterprise_value": 12_000_000, "irr_project": 0.095},
            "project_kpis": {"irr_equity": 0.14, "dscr_min": 1.18, "lcoe": None, "payback_years": 7.2}}


def test_portfolio_basic():
    result = analyze_portfolio([_solar_scenario(), _bess_scenario()])
    assert isinstance(result, PortfolioAnalysis)
    assert result.aggregated["project_count"] == 2


def test_portfolio_total_capex():
    result = analyze_portfolio([_solar_scenario(), _bess_scenario()])
    assert result.aggregated["total_capex"] == 40_000_000


def test_portfolio_weighted_irr():
    result = analyze_portfolio([_solar_scenario(), _bess_scenario()])
    # Weighted by CAPEX: (0.085*22M + 0.095*18M) / 40M
    expected = (0.085 * 22_000_000 + 0.095 * 18_000_000) / 40_000_000
    assert result.aggregated["weighted_avg_irr_project"] == pytest.approx(expected, rel=0.01)


def test_portfolio_worst_dscr():
    result = analyze_portfolio([_solar_scenario(), _bess_scenario()])
    assert result.aggregated["worst_dscr_min"] == 1.18  # BESS is worse


def test_portfolio_comparison_table():
    result = analyze_portfolio([_solar_scenario(), _bess_scenario()])
    assert len(result.comparison_table) == 2
    assert result.comparison_table[0]["name"] == "Solar Sevilla"
    assert result.comparison_table[1]["name"] == "BESS Madrid"


def test_portfolio_narrative():
    result = analyze_portfolio([_solar_scenario(), _bess_scenario()])
    assert "2 project" in result.narrative
    assert "40,000,000" in result.narrative


def test_portfolio_single():
    result = analyze_portfolio([_solar_scenario()])
    assert result.aggregated["project_count"] == 1


def test_portfolio_empty():
    result = analyze_portfolio([])
    assert result.aggregated["project_count"] == 0
    assert result.aggregated["total_capex"] == 0


def test_portfolio_mcp_tool(tmp_path):
    from asset_finance_modeler.store.scenarios import SQLiteScenarioStore
    from asset_finance_modeler.core.scenario import Scenario, new_scenario_id
    from asset_finance_modeler.mcp_server.tools.portfolio import make_portfolio_analyze
    store = SQLiteScenarioStore(str(tmp_path / "test.db"))
    store.initialize()
    s1 = Scenario(id=new_scenario_id(), name="Solar", base_model="solar_pv",
                  results_snapshot={"summary": {"total_capex": 10_000_000, "irr_project": 0.08}})
    s2 = Scenario(id=new_scenario_id(), name="BESS", base_model="bess",
                  results_snapshot={"summary": {"total_capex": 8_000_000, "irr_project": 0.10}})
    store.save(s1)
    store.save(s2)
    handler = make_portfolio_analyze(store)
    result = handler({"scenario_ids": [s1.id, s2.id]})
    assert "aggregated" in result
    assert result["aggregated"]["project_count"] == 2
