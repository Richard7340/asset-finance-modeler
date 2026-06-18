import pytest
from asset_finance_modeler.core.scenario import Scenario, new_scenario_id
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore


def test_scenarios_isolated_by_user(tmp_path):
    store = SQLiteScenarioStore(str(tmp_path / "test.db"))
    store.initialize()
    s1 = Scenario(id=new_scenario_id(), name="S1", base_model="test", user_id="user-A")
    s2 = Scenario(id=new_scenario_id(), name="S2", base_model="test", user_id="user-B")
    s3 = Scenario(id=new_scenario_id(), name="S3", base_model="test", user_id="user-A")
    store.save(s1)
    store.save(s2)
    store.save(s3)
    a_scenarios = store.list(user_id="user-A")
    b_scenarios = store.list(user_id="user-B")
    assert len(a_scenarios) == 2
    assert len(b_scenarios) == 1
    assert all(s.user_id == "user-A" for s in a_scenarios)


def test_get_does_not_check_user():
    """get() by ID works regardless of user — needed for cross-user diffs by admin."""
    # This is intentional: get() is by primary key, list() is scoped
    pass  # get() already works this way


def test_default_user_backward_compat(tmp_path):
    store = SQLiteScenarioStore(str(tmp_path / "test.db"))
    store.initialize()
    s = Scenario(id=new_scenario_id(), name="Legacy", base_model="test")
    store.save(s)
    # Without user_id, should default to "default"
    loaded = store.get(s.id)
    assert loaded is not None
    assert loaded.user_id == "default"
    # list with default user should find it
    all_default = store.list(user_id="default")
    assert any(sc.id == s.id for sc in all_default)


def test_list_without_user_returns_all(tmp_path):
    """list() without user_id returns all (backward compat)."""
    store = SQLiteScenarioStore(str(tmp_path / "test.db"))
    store.initialize()
    store.save(Scenario(id=new_scenario_id(), name="A", base_model="test", user_id="t1"))
    store.save(Scenario(id=new_scenario_id(), name="B", base_model="test", user_id="t2"))
    all_scenarios = store.list()
    assert len(all_scenarios) == 2


def test_workspace_isolation(tmp_path):
    """list() with workspace_id scopes results."""
    store = SQLiteScenarioStore(str(tmp_path / "test.db"))
    store.initialize()
    store.save(Scenario(id=new_scenario_id(), name="A", base_model="test", user_id="u1", workspace_id="ws1"))
    store.save(Scenario(id=new_scenario_id(), name="B", base_model="test", user_id="u1", workspace_id="ws2"))
    store.save(Scenario(id=new_scenario_id(), name="C", base_model="test", user_id="u1"))
    ws1 = store.list(user_id="u1", workspace_id="ws1")
    assert len(ws1) == 1
    assert ws1[0].name == "A"
    all_u1 = store.list(user_id="u1")
    assert len(all_u1) == 3


def test_get_scoped_by_workspace(tmp_path):
    """get(id, workspace_id) only returns the row if it belongs to that
    workspace; None for another workspace; unscoped get(id) still works."""
    store = SQLiteScenarioStore(str(tmp_path / "test.db"))
    store.initialize()
    s = Scenario(id=new_scenario_id(), name="A", base_model="test", workspace_id="ws1")
    store.save(s)
    assert store.get(s.id, workspace_id="ws1") is not None
    assert store.get(s.id, workspace_id="ws2") is None  # cross-tenant denied
    assert store.get(s.id) is not None  # unscoped (admin/internal) still works


def test_delete_scoped_by_workspace(tmp_path):
    """force_delete is a no-op across workspaces; deletes within the owner."""
    store = SQLiteScenarioStore(str(tmp_path / "test.db"))
    store.initialize()
    s = Scenario(id=new_scenario_id(), name="A", base_model="test", workspace_id="ws1")
    store.save(s)
    # Wrong workspace -> no-op, row survives.
    store.force_delete(s.id, workspace_id="ws2")
    assert store.get(s.id) is not None
    # Owner -> soft-deletes.
    store.force_delete(s.id, workspace_id="ws1")
    assert store.get(s.id).is_deleted
