import pytest

from asset_finance_modeler.mcp_server.registry import build_registry
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore


@pytest.fixture
def reg_three_scenarios(tmp_path):
    store = SQLiteScenarioStore(str(tmp_path / "s.db"))
    store.initialize()
    reg = build_registry(store)
    baseline_id = reg["finance.simulate.load_baseline"].handler(
        {"model": "gestnova", "preset": "gestnova"}
    )["scenario_id"]
    create = reg["finance.simulate.create_scenario"].handler
    cheap = create({
        "name": "cheap",
        "base_scenario_id": baseline_id,
        "overrides": {"revenue.sources[0].pricing.per_unit_per_period": 200},
    })["scenario_id"]
    expensive = create({
        "name": "expensive",
        "base_scenario_id": baseline_id,
        "overrides": {"revenue.sources[0].pricing.per_unit_per_period": 400},
    })["scenario_id"]
    # Run all three
    run = reg["finance.simulate.run"].handler
    for sid in (baseline_id, cheap, expensive):
        run({"scenario_id": sid})
    return store, reg, [baseline_id, cheap, expensive]


def test_compare(reg_three_scenarios):
    _, reg, ids = reg_three_scenarios
    compare = reg["finance.simulate.compare"].handler
    out = compare({"scenario_ids": ids})
    assert "table" in out
    table = out["table"]
    assert table["scenarios"] == ["gestnova-baseline", "cheap", "expensive"]
    # revenue_y1 should be ordered by pricing
    revs = table["metrics"]["revenue_y1"]
    assert revs[1] < revs[0] < revs[2]


def test_sensitivity_1d(reg_three_scenarios):
    _, reg, ids = reg_three_scenarios
    sens = reg["finance.simulate.sensitivity_1d"].handler
    out = sens({
        "scenario_id": ids[0],
        "variable": "revenue.sources[0].pricing.per_unit_per_period",
        "values": [200, 300, 400],
        "metric": "revenue_end_period",
    })
    assert "points" in out
    assert len(out["points"]) == 3
    vals = [p["metric_value"] for p in out["points"]]
    assert vals[0] < vals[1] < vals[2]


def test_sensitivity_grid(reg_three_scenarios):
    _, reg, ids = reg_three_scenarios
    grid_tool = reg["finance.simulate.sensitivity_grid"].handler
    out = grid_tool({
        "scenario_id": ids[0],
        "var_x": "revenue.sources[0].pricing.per_unit_per_period",
        "values_x": [200, 300],
        "var_y": "revenue.sources[0].retention.monthly_churn_rate",
        "values_y": [0.01, 0.05],
        "metric": "enterprise_value",
    })
    assert "grid" in out
    grid = out["grid"]
    assert len(grid) == 2  # rows = len(values_x)
    assert len(grid[0]) == 2  # cols = len(values_y)
    # Higher churn (col 1) → lower EV
    assert grid[0][0] > grid[0][1]


def test_compare_missing_results_returns_error(tmp_path):
    store = SQLiteScenarioStore(str(tmp_path / "s.db"))
    store.initialize()
    reg = build_registry(store)
    baseline_id = reg["finance.simulate.load_baseline"].handler(
        {"model": "gestnova", "preset": "gestnova"}
    )["scenario_id"]
    # NOT run — no results_snapshot
    compare = reg["finance.simulate.compare"].handler
    out = compare({"scenario_ids": [baseline_id]})
    assert "error" in out
