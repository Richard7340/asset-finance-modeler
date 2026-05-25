import pytest
from asset_finance_modeler.store.projects import Project, SQLiteProjectStore, new_project_id


def test_create_project(tmp_path):
    store = SQLiteProjectStore(str(tmp_path / "test.db"))
    store.initialize()
    p = Project(id=new_project_id(), user_id="user-1", name="Solar Sevilla",
                asset_type="solar_pv", region="ES", tags=["renewable"])
    store.save(p)
    loaded = store.get(p.id)
    assert loaded is not None
    assert loaded.name == "Solar Sevilla"
    assert loaded.user_id == "user-1"


def test_list_by_tenant(tmp_path):
    store = SQLiteProjectStore(str(tmp_path / "test.db"))
    store.initialize()
    store.save(Project(id=new_project_id(), user_id="t1", name="P1"))
    store.save(Project(id=new_project_id(), user_id="t1", name="P2"))
    store.save(Project(id=new_project_id(), user_id="t2", name="P3"))
    assert len(store.list_by_tenant("t1")) == 2
    assert len(store.list_by_tenant("t2")) == 1


def test_archive_project(tmp_path):
    store = SQLiteProjectStore(str(tmp_path / "test.db"))
    store.initialize()
    p = Project(id=new_project_id(), user_id="t1", name="Old")
    store.save(p)
    store.archive(p.id)
    assert len(store.list_by_tenant("t1")) == 0
    assert len(store.list_by_tenant("t1", include_archived=True)) == 1


def test_add_scenario(tmp_path):
    store = SQLiteProjectStore(str(tmp_path / "test.db"))
    store.initialize()
    p = Project(id=new_project_id(), user_id="t1", name="Test")
    store.save(p)
    store.add_scenario(p.id, "scn-abc123")
    loaded = store.get(p.id)
    assert "scn-abc123" in loaded.scenario_ids


def test_add_scenario_idempotent(tmp_path):
    store = SQLiteProjectStore(str(tmp_path / "test.db"))
    store.initialize()
    p = Project(id=new_project_id(), user_id="t1", name="Test")
    store.save(p)
    store.add_scenario(p.id, "scn-abc")
    store.add_scenario(p.id, "scn-abc")
    loaded = store.get(p.id)
    assert loaded.scenario_ids.count("scn-abc") == 1


def test_project_metadata(tmp_path):
    store = SQLiteProjectStore(str(tmp_path / "test.db"))
    store.initialize()
    p = Project(id=new_project_id(), user_id="t1", name="Test",
                metadata={"budget": 10_000_000, "notes": "Phase 1"})
    store.save(p)
    loaded = store.get(p.id)
    assert loaded.metadata["budget"] == 10_000_000


def test_get_nonexistent(tmp_path):
    store = SQLiteProjectStore(str(tmp_path / "test.db"))
    store.initialize()
    assert store.get("nonexistent") is None


def test_workspace_isolation(tmp_path):
    store = SQLiteProjectStore(str(tmp_path / "test.db"))
    store.initialize()
    store.save(Project(id=new_project_id(), user_id="u1", name="P1", workspace_id="ws1"))
    store.save(Project(id=new_project_id(), user_id="u1", name="P2", workspace_id="ws2"))
    store.save(Project(id=new_project_id(), user_id="u1", name="P3"))
    assert len(store.list_by_tenant("u1", workspace_id="ws1")) == 1
    assert len(store.list_by_tenant("u1")) == 3
