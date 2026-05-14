import pytest

from asset_finance_modeler.core.scenario import Scenario, new_scenario_id
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore


@pytest.fixture
def store(tmp_path):
    db_path = tmp_path / "scenarios.db"
    s = SQLiteScenarioStore(str(db_path))
    s.initialize()
    return s


def test_save_and_get(store):
    s = Scenario(id=new_scenario_id(), name="baseline", base_model="gestnova")
    store.save(s)
    fetched = store.get(s.id)
    assert fetched is not None
    assert fetched.id == s.id
    assert fetched.name == "baseline"


def test_get_missing_returns_none(store):
    assert store.get("nonexistent") is None


def test_list_filters_by_base_model(store):
    s1 = Scenario(id=new_scenario_id(), name="a", base_model="gestnova")
    s2 = Scenario(id=new_scenario_id(), name="b", base_model="other")
    store.save(s1)
    store.save(s2)
    only_gn = store.list(base_model="gestnova")
    assert len(only_gn) == 1
    assert only_gn[0].name == "a"


def test_list_excludes_deleted_by_default(store):
    s = Scenario(id=new_scenario_id(), name="x", base_model="gestnova")
    store.save(s)
    store.delete(s.id)
    assert store.list() == []
    assert len(store.list(include_deleted=True)) == 1


def test_delete_protected_raises(store):
    s = Scenario(id=new_scenario_id(), name="canon", base_model="gestnova", is_canonical=True)
    store.save(s)
    with pytest.raises(PermissionError):
        store.delete(s.id)


def test_set_canonical(store):
    s = Scenario(id=new_scenario_id(), name="b", base_model="gestnova")
    store.save(s)
    store.set_canonical(s.id, name="gestnova-baseline")
    fetched = store.get(s.id)
    assert fetched.is_canonical is True
    assert fetched.name == "gestnova-baseline"


def test_update_existing(store):
    s = Scenario(id=new_scenario_id(), name="initial", base_model="gestnova")
    store.save(s)
    s.notes = "updated note"
    store.save(s)  # save = upsert
    assert store.get(s.id).notes == "updated note"
