import sqlite3

from datetime import UTC, datetime

from asset_finance_modeler.core.scenario import Scenario, new_scenario_id
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore


def test_store_roundtrips_lifecycle(tmp_path):
    store = SQLiteScenarioStore(str(tmp_path / "s.db"))
    store.initialize()
    s = Scenario(
        id=new_scenario_id(),
        name="Planta FV",
        base_model="solar_pv_50mw_spain",
        lifecycle="operational",
        commissioning_date=datetime(2026, 1, 1, tzinfo=UTC),
        base_locked=True,
        tracking_frequency="monthly",
    )
    store.save(s)
    got = store.get(s.id)
    assert got is not None
    assert got.lifecycle == "operational"
    assert got.commissioning_date == datetime(2026, 1, 1, tzinfo=UTC)
    assert got.base_locked is True
    assert got.tracking_frequency == "monthly"


def test_store_lifecycle_defaults_for_new_db(tmp_path):
    store = SQLiteScenarioStore(str(tmp_path / "s.db"))
    store.initialize()
    s = Scenario(id=new_scenario_id(), name="Op", base_model="bess_20mw_4h")
    store.save(s)
    got = store.get(s.id)
    assert got.lifecycle == "opportunity"
    assert got.commissioning_date is None
    assert got.base_locked is False
    assert got.tracking_frequency is None


def test_store_list_filters_by_lifecycle(tmp_path):
    store = SQLiteScenarioStore(str(tmp_path / "s.db"))
    store.initialize()
    op = Scenario(id=new_scenario_id(), name="Op", base_model="bess_20mw_4h",
                  lifecycle="operational")
    opp = Scenario(id=new_scenario_id(), name="Opp", base_model="bess_20mw_4h")
    store.save(op)
    store.save(opp)
    ops = store.list(lifecycle="operational")
    assert [s.id for s in ops] == [op.id]
    opps = store.list(lifecycle="opportunity")
    assert [s.id for s in opps] == [opp.id]
    assert len(store.list()) == 2


def test_store_migrates_legacy_db_without_lifecycle_columns(tmp_path):
    # Simula una DB antigua sin las columnas nuevas, con una fila existente.
    db = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(db)
    conn.execute(
        """CREATE TABLE scenarios (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
            base_model TEXT NOT NULL, parent_scenario_id TEXT,
            overrides_json TEXT NOT NULL DEFAULT '{}',
            inputs_snapshot_json TEXT NOT NULL DEFAULT '{}',
            results_snapshot_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL, tags_json TEXT NOT NULL DEFAULT '[]',
            notes TEXT NOT NULL DEFAULT '', is_canonical INTEGER NOT NULL DEFAULT 0,
            is_deleted INTEGER NOT NULL DEFAULT 0, user_id TEXT NOT NULL DEFAULT 'default',
            workspace_id TEXT
        )"""
    )
    conn.execute(
        "INSERT INTO scenarios (id, name, base_model, created_at) VALUES (?,?,?,?)",
        ("scn-old", "Antiguo", "bess_20mw_4h", datetime(2025, 1, 1, tzinfo=UTC).isoformat()),
    )
    conn.commit()
    conn.close()

    store = SQLiteScenarioStore(db)
    store.initialize()  # debe añadir las columnas sin romper
    got = store.get("scn-old")
    assert got is not None
    assert got.lifecycle == "opportunity"  # default tras migración
    assert got.commissioning_date is None
    assert got.base_locked is False
    assert got.tracking_frequency is None
