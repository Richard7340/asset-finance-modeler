"""finance.track.* reales: importar, conciliar y varianza sobre SQLite temporal."""
from asset_finance_modeler.core.scenario import Scenario
from asset_finance_modeler.mcp_server.tools.tracking import (
    make_track_import,
    make_track_reconcile,
    make_track_variance,
)
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore

SNAP = {"income_statement": {"rows": {"revenue": [100.0, 200.0, 300.0]}}}


def _tienda(tmp_path):
    store = SQLiteScenarioStore(str(tmp_path / "s.db"))
    store.initialize()
    s = Scenario(id="scn-t1", name="t", base_model="gestnova", results_snapshot=SNAP)
    store.save(s)
    return store


def test_import_ok(tmp_path):
    store = _tienda(tmp_path)
    r = make_track_import(store)({
        "scenario_id": "scn-t1",
        "actuals": [{"line_path": "income_statement.rows.revenue", "period_start": "2026-03-01", "value": 90.0}],
    })
    assert r["ok"] is True
    assert len(r["imported"]) == 1


def test_import_sin_escenario():
    import tempfile, os
    d = tempfile.mkdtemp()
    store = SQLiteScenarioStore(os.path.join(d, "s.db"))
    store.initialize()
    r = make_track_import(store)({"scenario_id": "nope", "actuals": []})
    assert "not found" in r["error"]


def test_import_invalido():
    import tempfile, os
    d = tempfile.mkdtemp()
    store = SQLiteScenarioStore(os.path.join(d, "s.db"))
    store.initialize()
    store.save(Scenario(id="s", name="t", base_model="gestnova"))
    assert "actuals-required" in make_track_import(store)({"scenario_id": "s", "actuals": []})["error"]
    assert "line_path" in make_track_import(store)({
        "scenario_id": "s", "actuals": [{"value": 1}],
    })["error"]


def test_reconcile_y_variance(tmp_path):
    store = _tienda(tmp_path)
    make_track_import(store)({
        "scenario_id": "scn-t1",
        "actuals": [{"line_path": "income_statement.rows.revenue", "period_start": "2026-03-01", "value": 90.0}],
    })
    rec = make_track_reconcile(store)({"scenario_id": "scn-t1"})
    assert rec["n_actuals"] == 1
    rev = next(l for l in rec["lines"] if l["line_path"] == "income_statement.rows.revenue")
    assert rev["actual_total"] == 90.0
    var = make_track_variance(store)({"scenario_id": "scn-t1"})
    rl = next(l for l in var["lines"] if l["line_path"] == "income_statement.rows.revenue")
    assert rl["base"] == [100.0, 200.0, 300.0]
    assert rl["deviation"][0] == -10.0
    assert rl["actual"][1] is None


def test_reconcile_sin_resultados(tmp_path):
    store = SQLiteScenarioStore(str(tmp_path / "s.db"))
    store.initialize()
    store.save(Scenario(id="s", name="t", base_model="gestnova"))
    assert "run it first" in make_track_reconcile(store)({"scenario_id": "s"})["error"]
    assert "run it first" in make_track_variance(store)({"scenario_id": "s"})["error"]


def test_pnl_mensual_se_anualiza(tmp_path):
    from asset_finance_modeler.web_api.actuals import _base_series, _trackable_lines
    snap = {"pnl": {"revenue": [10.0] * 24, "ebitda": [1.0] * 24}}
    paths = [ln["path"] for ln in _trackable_lines(snap)]
    assert "pnl.revenue" in paths
    assert _base_series(snap, "pnl.revenue") == [120.0, 120.0]
    assert _base_series(snap, "no.existe") is None
