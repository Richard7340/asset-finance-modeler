import pytest

from asset_finance_modeler.core.scenario import Scenario, new_scenario_id
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore


@pytest.fixture
def store(tmp_path):
    s = SQLiteScenarioStore(str(tmp_path / "scenarios.db"))
    s.initialize()
    return s


def _build_tree(store):
    """Build: root → child_a → grandchild ; root → child_b"""
    root = Scenario(id=new_scenario_id(), name="root", base_model="gestnova")
    child_a = Scenario(
        id=new_scenario_id(), name="child_a", base_model="gestnova",
        parent_scenario_id=root.id,
    )
    child_b = Scenario(
        id=new_scenario_id(), name="child_b", base_model="gestnova",
        parent_scenario_id=root.id,
    )
    grandchild = Scenario(
        id=new_scenario_id(), name="grandchild", base_model="gestnova",
        parent_scenario_id=child_a.id,
    )
    for s in (root, child_a, child_b, grandchild):
        store.save(s)
    return root, child_a, child_b, grandchild


def test_get_ancestors_of_grandchild(store):
    root, child_a, _, grandchild = _build_tree(store)
    ancestors = store.get_ancestors(grandchild.id)
    assert [a.id for a in ancestors] == [child_a.id, root.id]


def test_get_descendants_of_root(store):
    root, child_a, child_b, grandchild = _build_tree(store)
    descendants = store.get_descendants(root.id)
    ids = {d.id for d in descendants}
    assert ids == {child_a.id, child_b.id, grandchild.id}


def test_get_ancestors_of_root_is_empty(store):
    root, _, _, _ = _build_tree(store)
    assert store.get_ancestors(root.id) == []


def test_get_descendants_excludes_deleted(store):
    root, child_a, _, _ = _build_tree(store)
    store.delete(child_a.id)
    descendants = store.get_descendants(root.id)
    # child_a is deleted → its descendants stay reachable via deleted intermediate? Decision: skip subtree of deleted.
    # We expect: only child_b reachable from root.
    assert all(d.name in {"child_b"} for d in descendants)
