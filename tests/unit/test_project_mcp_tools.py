import pytest

from asset_finance_modeler.core.scenario import Scenario, new_scenario_id
from asset_finance_modeler.mcp_server.tools.projects import (
    make_project_archive,
    make_project_create,
    make_project_get,
    make_project_list,
)
from asset_finance_modeler.mcp_server.tools.scenario_recall import (
    make_recall_project_context,
    make_scenario_diff,
)
from asset_finance_modeler.store.projects import SQLiteProjectStore
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore


@pytest.fixture()
def stores(tmp_path):
    proj = SQLiteProjectStore(str(tmp_path / "test.db"))
    proj.initialize()
    scn = SQLiteScenarioStore(str(tmp_path / "test.db"))
    scn.initialize()
    return proj, scn


def test_project_create(stores):
    proj_store, _ = stores
    handler = make_project_create(proj_store)
    result = handler({"name": "Solar Sevilla", "asset_type": "solar_pv", "region": "ES"})
    assert "project_id" in result
    assert result["name"] == "Solar Sevilla"


def test_project_list(stores):
    proj_store, _ = stores
    make_project_create(proj_store)({"name": "P1", "tenant_id": "t1"})
    make_project_create(proj_store)({"name": "P2", "tenant_id": "t1"})
    result = make_project_list(proj_store)({"tenant_id": "t1"})
    assert len(result["projects"]) == 2


def test_project_get(stores):
    proj_store, _ = stores
    created = make_project_create(proj_store)({"name": "Test"})
    result = make_project_get(proj_store)({"project_id": created["project_id"]})
    assert result["name"] == "Test"


def test_project_get_not_found(stores):
    proj_store, _ = stores
    result = make_project_get(proj_store)({"project_id": "prj-nonexistent"})
    assert "error" in result


def test_project_archive(stores):
    proj_store, _ = stores
    created = make_project_create(proj_store)({"name": "Old"})
    make_project_archive(proj_store)({"project_id": created["project_id"]})
    result = make_project_list(proj_store)({"tenant_id": "default"})
    assert len(result["projects"]) == 0


def test_project_archive_visible_with_flag(stores):
    proj_store, _ = stores
    created = make_project_create(proj_store)({"name": "Old"})
    make_project_archive(proj_store)({"project_id": created["project_id"]})
    result = make_project_list(proj_store)({"tenant_id": "default", "include_archived": True})
    assert len(result["projects"]) == 1
    assert result["projects"][0]["archived"] is True


def test_scenario_diff_via_mcp(stores):
    _, scn_store = stores
    s1 = Scenario(
        id=new_scenario_id(),
        name="Base",
        base_model="test",
        results_snapshot={
            "summary": {"revenue_y1": 3_000_000, "irr_project": 0.08},
            "inputs_resolved": {"x": 1},
        },
    )
    s2 = Scenario(
        id=new_scenario_id(),
        name="Optimistic",
        base_model="test",
        results_snapshot={
            "summary": {"revenue_y1": 3_500_000, "irr_project": 0.10},
            "inputs_resolved": {"x": 2},
        },
    )
    scn_store.save(s1)
    scn_store.save(s2)
    handler = make_scenario_diff(scn_store)
    result = handler({"scenario_a_id": s1.id, "scenario_b_id": s2.id})
    assert "summary" in result
    assert "kpi_deltas" in result
    assert len(result["kpi_deltas"]) >= 1


def test_scenario_diff_not_found(stores):
    _, scn_store = stores
    handler = make_scenario_diff(scn_store)
    result = handler({"scenario_a_id": "scn-missing", "scenario_b_id": "scn-other"})
    assert "error" in result


def test_recall_project_context(stores):
    proj_store, scn_store = stores
    # Create project
    p = make_project_create(proj_store)(
        {"name": "Solar Sevilla", "asset_type": "solar_pv", "region": "ES"}
    )
    # Create scenario with results
    s = Scenario(
        id=new_scenario_id(),
        name="Base",
        base_model="solar_pv",
        results_snapshot={
            "summary": {"revenue_y1": 3_000_000},
            "project_kpis": {"irr_project": 0.085},
        },
    )
    scn_store.save(s)
    proj_store.add_scenario(p["project_id"], s.id)
    # Recall context
    handler = make_recall_project_context(proj_store, scn_store)
    result = handler({"project_id": p["project_id"]})
    assert "narrative" in result
    assert "Solar Sevilla" in result["narrative"]
    assert len(result["scenarios"]) == 1


def test_recall_project_context_not_found(stores):
    proj_store, scn_store = stores
    handler = make_recall_project_context(proj_store, scn_store)
    result = handler({"project_id": "prj-nonexistent"})
    assert "error" in result


def test_recall_project_context_narrative_irr(stores):
    proj_store, scn_store = stores
    p = make_project_create(proj_store)({"name": "Wind Norte", "asset_type": "wind", "region": "ES-N"})
    s = Scenario(
        id=new_scenario_id(),
        name="Base",
        base_model="wind",
        results_snapshot={"project_kpis": {"irr_project": 0.12}},
    )
    scn_store.save(s)
    proj_store.add_scenario(p["project_id"], s.id)
    handler = make_recall_project_context(proj_store, scn_store)
    result = handler({"project_id": p["project_id"]})
    assert "12.0%" in result["narrative"]
    assert "wind" in result["narrative"]
    assert "ES-N" in result["narrative"]
