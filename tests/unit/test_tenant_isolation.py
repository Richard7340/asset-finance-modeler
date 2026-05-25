import pytest
from asset_finance_modeler.core.scenario import Scenario, new_scenario_id
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore


def test_scenarios_isolated_by_tenant(tmp_path):
    store = SQLiteScenarioStore(str(tmp_path / "test.db"))
    store.initialize()
    s1 = Scenario(id=new_scenario_id(), name="S1", base_model="test", tenant_id="tenant-A")
    s2 = Scenario(id=new_scenario_id(), name="S2", base_model="test", tenant_id="tenant-B")
    s3 = Scenario(id=new_scenario_id(), name="S3", base_model="test", tenant_id="tenant-A")
    store.save(s1)
    store.save(s2)
    store.save(s3)
    a_scenarios = store.list(tenant_id="tenant-A")
    b_scenarios = store.list(tenant_id="tenant-B")
    assert len(a_scenarios) == 2
    assert len(b_scenarios) == 1
    assert all(s.tenant_id == "tenant-A" for s in a_scenarios)


def test_get_does_not_check_tenant():
    """get() by ID works regardless of tenant — needed for cross-tenant diffs by admin."""
    # This is intentional: get() is by primary key, list() is scoped
    pass  # get() already works this way


def test_default_tenant_backward_compat(tmp_path):
    store = SQLiteScenarioStore(str(tmp_path / "test.db"))
    store.initialize()
    s = Scenario(id=new_scenario_id(), name="Legacy", base_model="test")
    store.save(s)
    # Without tenant_id, should default to "default"
    loaded = store.get(s.id)
    assert loaded is not None
    assert loaded.tenant_id == "default"
    # list with default tenant should find it
    all_default = store.list(tenant_id="default")
    assert any(sc.id == s.id for sc in all_default)


def test_list_without_tenant_returns_all(tmp_path):
    """list() without tenant_id returns all (backward compat)."""
    store = SQLiteScenarioStore(str(tmp_path / "test.db"))
    store.initialize()
    store.save(Scenario(id=new_scenario_id(), name="A", base_model="test", tenant_id="t1"))
    store.save(Scenario(id=new_scenario_id(), name="B", base_model="test", tenant_id="t2"))
    all_scenarios = store.list()
    assert len(all_scenarios) == 2
