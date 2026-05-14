import pytest

from asset_finance_modeler.mcp_server.registry import build_registry
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore


@pytest.fixture
def reg_with_baseline(tmp_path):
    store = SQLiteScenarioStore(str(tmp_path / "s.db"))
    store.initialize()
    reg = build_registry(store)
    baseline_id = reg["finance.simulate.load_baseline"].handler(
        {"model": "gestnova", "preset": "gestnova"}
    )["scenario_id"]
    return store, reg, baseline_id


def test_run_persists_summary_in_results_snapshot(reg_with_baseline):
    store, reg, baseline_id = reg_with_baseline
    run = reg["finance.simulate.run"].handler
    result = run({"scenario_id": baseline_id})
    assert "summary" in result
    assert "revenue_y1" in result["summary"]
    # Persisted on the scenario row
    fetched = store.get(baseline_id)
    assert "summary" in fetched.results_snapshot


def test_get_results_summary_view(reg_with_baseline):
    store, reg, baseline_id = reg_with_baseline
    reg["finance.simulate.run"].handler({"scenario_id": baseline_id})
    get_results = reg["finance.simulate.get_results"].handler
    out = get_results({"scenario_id": baseline_id, "view": "summary"})
    assert "summary" in out
    assert "revenue_y1" in out["summary"]


def test_get_results_pnl_view(reg_with_baseline):
    store, reg, baseline_id = reg_with_baseline
    reg["finance.simulate.run"].handler({"scenario_id": baseline_id})
    get_results = reg["finance.simulate.get_results"].handler
    out = get_results({"scenario_id": baseline_id, "view": "pnl"})
    assert "pnl" in out
    assert "revenue" in out["pnl"]
    assert len(out["pnl"]["revenue"]) == 60


def test_get_results_all_view(reg_with_baseline):
    store, reg, baseline_id = reg_with_baseline
    reg["finance.simulate.run"].handler({"scenario_id": baseline_id})
    get_results = reg["finance.simulate.get_results"].handler
    out = get_results({"scenario_id": baseline_id, "view": "all"})
    # 'all' should expose every view
    for key in ["summary", "pnl", "cashflow", "balance", "unit_econ", "valuation"]:
        assert key in out


def test_get_genealogy(reg_with_baseline):
    store, reg, baseline_id = reg_with_baseline
    create = reg["finance.simulate.create_scenario"].handler
    a = create({"name": "a", "base_scenario_id": baseline_id, "overrides": {}})["scenario_id"]
    b = create({"name": "b", "base_scenario_id": a, "overrides": {}})["scenario_id"]

    genealogy = reg["finance.simulate.get_genealogy"].handler
    out = genealogy({"scenario_id": b})
    anc_names = [a["name"] for a in out["ancestors"]]
    assert anc_names == ["a", "gestnova-baseline"]


def test_run_unknown_scenario_returns_error(reg_with_baseline):
    _, reg, _ = reg_with_baseline
    run = reg["finance.simulate.run"].handler
    out = run({"scenario_id": "nonexistent"})
    assert "error" in out
