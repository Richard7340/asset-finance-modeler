from asset_finance_modeler.store.actuals import Actual, SQLiteActualsStore


def _store(tmp_path):
    s = SQLiteActualsStore(str(tmp_path / "scenarios.db"))
    s.initialize()
    return s


def test_add_and_list(tmp_path):
    s = _store(tmp_path)
    aid = s.add(
        Actual(
            scenario_id="scn-1",
            period_start="2026-01-01",
            line_path="income_statement.rows.revenue",
            value=1000.0,
            unit="EUR",
            note="enero",
            entered_by="riky",
        )
    )
    assert aid.startswith("act-")
    rows = s.list(scenario_id="scn-1")
    assert len(rows) == 1
    assert rows[0].id == aid
    assert rows[0].value == 1000.0
    assert rows[0].line_path == "income_statement.rows.revenue"
    assert rows[0].entered_at  # auto-stamped


def test_add_batch_and_filter_by_line(tmp_path):
    s = _store(tmp_path)
    s.add_batch(
        [
            Actual(scenario_id="scn-1", period_start="2026-01-01",
                   line_path="income_statement.rows.revenue", value=100.0),
            Actual(scenario_id="scn-1", period_start="2026-02-01",
                   line_path="income_statement.rows.revenue", value=200.0),
            Actual(scenario_id="scn-1", period_start="2026-01-01",
                   line_path="cash_flow.cfo", value=50.0),
        ]
    )
    rev = s.list(scenario_id="scn-1", line_path="income_statement.rows.revenue")
    assert len(rev) == 2
    assert {r.value for r in rev} == {100.0, 200.0}
    cfo = s.list(scenario_id="scn-1", line_path="cash_flow.cfo")
    assert len(cfo) == 1


def test_list_filters_by_scenario(tmp_path):
    s = _store(tmp_path)
    s.add(Actual(scenario_id="scn-1", period_start="2026-01-01",
                 line_path="x", value=1.0))
    s.add(Actual(scenario_id="scn-2", period_start="2026-01-01",
                 line_path="x", value=2.0))
    assert len(s.list(scenario_id="scn-1")) == 1
    assert len(s.list(scenario_id="scn-2")) == 1


def test_list_filters_by_date_range(tmp_path):
    s = _store(tmp_path)
    for m in ("2026-01-01", "2026-02-01", "2026-03-01"):
        s.add(Actual(scenario_id="scn-1", period_start=m, line_path="x", value=1.0))
    sub = s.list(scenario_id="scn-1", since="2026-02-01", until="2026-02-28")
    assert [r.period_start for r in sub] == ["2026-02-01"]
    frm = s.list(scenario_id="scn-1", since="2026-02-01")
    assert [r.period_start for r in frm] == ["2026-02-01", "2026-03-01"]


def test_delete(tmp_path):
    s = _store(tmp_path)
    aid = s.add(Actual(scenario_id="scn-1", period_start="2026-01-01",
                       line_path="x", value=1.0))
    s.delete(aid)
    assert s.list(scenario_id="scn-1") == []


def test_actuals_reuse_scenarios_db_file(tmp_path):
    """Actuals live in the SAME sqlite file as scenarios."""
    from asset_finance_modeler.store.scenarios import SQLiteScenarioStore

    db = str(tmp_path / "scenarios.db")
    scn = SQLiteScenarioStore(db)
    scn.initialize()
    act = SQLiteActualsStore(db)
    act.initialize()
    aid = act.add(Actual(scenario_id="scn-1", period_start="2026-01-01",
                         line_path="x", value=1.0))
    assert act.list(scenario_id="scn-1")[0].id == aid
