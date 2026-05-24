from asset_finance_modeler.core.scenario import Scenario, new_scenario_id, run_scenario, run_scenario_saas
from asset_finance_modeler.mcp_server.tools.discover import handle_list_models


def test_run_scenario_saas_backward_compat():
    scenario = Scenario(id=new_scenario_id(), name="saas-test", base_model="gestnova", overrides={})
    results = run_scenario_saas(scenario)
    assert "revenue" in results.pnl


def test_run_scenario_dispatches_saas():
    scenario = Scenario(id=new_scenario_id(), name="saas-test", base_model="gestnova", overrides={})
    results = run_scenario(scenario)
    assert "revenue" in results.pnl


def test_run_scenario_dispatches_solar():
    scenario = Scenario(id=new_scenario_id(), name="solar-test", base_model="solar_pv_50mw_spain", overrides={})
    results = run_scenario(scenario)
    assert "revenue" in results.pnl
    assert results.project_kpis is not None


def test_run_scenario_dispatches_bess():
    scenario = Scenario(id=new_scenario_id(), name="bess-test", base_model="bess_20mw_4h", overrides={})
    results = run_scenario(scenario)
    assert "revenue" in results.pnl


def test_list_models_includes_infrastructure():
    result = handle_list_models({})
    names = [m["name"] for m in result["models"]]
    assert "solar_pv_50mw_spain" in names
    assert "bess_20mw_4h" in names
    assert "gestnova" in names
