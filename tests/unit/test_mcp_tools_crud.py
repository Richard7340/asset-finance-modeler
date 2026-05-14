import pytest

from asset_finance_modeler.mcp_server.registry import build_registry
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore


@pytest.fixture
def store_and_baseline(tmp_path):
    store = SQLiteScenarioStore(str(tmp_path / "s.db"))
    store.initialize()
    reg = build_registry(store)
    load = reg["finance.simulate.load_baseline"].handler
    baseline_id = load({"model": "gestnova", "preset": "gestnova"})["scenario_id"]
    return store, reg, baseline_id


def test_create_scenario(store_and_baseline):
    store, reg, baseline_id = store_and_baseline
    create = reg["finance.simulate.create_scenario"].handler
    result = create({
        "name": "pricing-250",
        "base_scenario_id": baseline_id,
        "overrides": {"revenue.sources[0].pricing.per_unit_per_period": 250},
        "notes": "Lower price",
    })
    assert "scenario_id" in result
    fetched = store.get(result["scenario_id"])
    assert fetched.name == "pricing-250"
    assert fetched.parent_scenario_id == baseline_id


def test_clone_scenario(store_and_baseline):
    store, reg, baseline_id = store_and_baseline
    create = reg["finance.simulate.create_scenario"].handler
    clone = reg["finance.simulate.clone_scenario"].handler

    first = create({
        "name": "first",
        "base_scenario_id": baseline_id,
        "overrides": {"revenue.sources[0].pricing.per_unit_per_period": 250},
    })
    second = clone({
        "scenario_id": first["scenario_id"],
        "name": "second-with-extra",
        "overrides": {"operating_expenses.infra_fixed_eur": 600},
    })
    assert "scenario_id" in second
    fetched = store.get(second["scenario_id"])
    # Clone inherits parent's overrides + adds its own
    assert fetched.overrides["revenue.sources[0].pricing.per_unit_per_period"] == 250
    assert fetched.overrides["operating_expenses.infra_fixed_eur"] == 600
    assert fetched.parent_scenario_id == first["scenario_id"]


def test_list_scenarios(store_and_baseline):
    store, reg, baseline_id = store_and_baseline
    create = reg["finance.simulate.create_scenario"].handler
    create({"name": "a", "base_scenario_id": baseline_id, "overrides": {}})
    create({"name": "b", "base_scenario_id": baseline_id, "overrides": {}})
    list_tool = reg["finance.simulate.list_scenarios"].handler
    result = list_tool({})
    assert "scenarios" in result
    names = [s["name"] for s in result["scenarios"]]
    assert "a" in names and "b" in names
    assert "gestnova-baseline" in names


def test_delete_scenario(store_and_baseline):
    store, reg, baseline_id = store_and_baseline
    create = reg["finance.simulate.create_scenario"].handler
    delete = reg["finance.simulate.delete_scenario"].handler
    s = create({"name": "x", "base_scenario_id": baseline_id, "overrides": {}})
    delete({"scenario_id": s["scenario_id"]})
    assert store.get(s["scenario_id"]).is_deleted is True


def test_delete_canonical_returns_error(store_and_baseline):
    store, reg, baseline_id = store_and_baseline
    delete = reg["finance.simulate.delete_scenario"].handler
    # Baseline is canonical
    result = delete({"scenario_id": baseline_id})
    assert "error" in result


def test_set_canonical(store_and_baseline):
    store, reg, baseline_id = store_and_baseline
    create = reg["finance.simulate.create_scenario"].handler
    set_canonical = reg["finance.simulate.set_canonical"].handler
    s = create({"name": "candidate", "base_scenario_id": baseline_id, "overrides": {}})
    set_canonical({"scenario_id": s["scenario_id"], "name": "new-baseline"})
    fetched = store.get(s["scenario_id"])
    assert fetched.is_canonical is True
    assert fetched.name == "new-baseline"
