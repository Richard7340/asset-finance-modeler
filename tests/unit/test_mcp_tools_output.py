import json

import pytest

from asset_finance_modeler.mcp_server.registry import build_registry
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore


@pytest.fixture
def reg_with_run(tmp_path):
    store = SQLiteScenarioStore(str(tmp_path / "s.db"))
    store.initialize()
    reg = build_registry(store)
    sid = reg["finance.simulate.load_baseline"].handler(
        {"model": "gestnova", "preset": "gestnova"}
    )["scenario_id"]
    reg["finance.simulate.run"].handler({"scenario_id": sid})
    return store, reg, sid, tmp_path


def test_export_csv(reg_with_run):
    store, reg, sid, tmp_path = reg_with_run
    export = reg["finance.simulate.export"].handler
    out_path = tmp_path / "pnl.csv"
    result = export({
        "scenario_id": sid,
        "format": "csv",
        "view": "pnl",
        "path": str(out_path),
    })
    assert result["ok"] is True
    assert out_path.exists()
    assert "revenue" in out_path.read_text()


def test_export_xlsx(reg_with_run):
    store, reg, sid, tmp_path = reg_with_run
    export = reg["finance.simulate.export"].handler
    out_path = tmp_path / "model.xlsx"
    result = export({
        "scenario_id": sid,
        "format": "xlsx",
        "path": str(out_path),
    })
    assert result["ok"] is True
    assert out_path.exists()


def test_export_markdown_report_inline(reg_with_run):
    store, reg, sid, tmp_path = reg_with_run
    export = reg["finance.simulate.export"].handler
    result = export({
        "scenario_id": sid,
        "format": "markdown_report",
    })
    # No path → return content inline
    assert "content" in result
    assert "Revenue" in result["content"] or "revenue" in result["content"]


def test_export_json_inline(reg_with_run):
    store, reg, sid, _ = reg_with_run
    export = reg["finance.simulate.export"].handler
    result = export({"scenario_id": sid, "format": "json"})
    parsed = json.loads(result["content"])
    assert "summary" in parsed


def test_fetch_external_returns_query_instruction(reg_with_run):
    store, reg, sid, _ = reg_with_run
    fetch = reg["finance.simulate.fetch_external"].handler
    out = fetch({
        "scenario_id": sid,
        "field_path": "external_data.benchmarks.saas_churn_p50",
        "query": "SaaS B2B average monthly churn 2025",
        "hint": "industry reports preferred",
    })
    # fetch_external does NOT execute HTTP — returns instruction
    assert out["query"] == "SaaS B2B average monthly churn 2025"
    assert out["field_path"] == "external_data.benchmarks.saas_churn_p50"


def test_set_external_persists_value(reg_with_run):
    store, reg, sid, _ = reg_with_run
    set_ext = reg["finance.simulate.set_external"].handler
    out = set_ext({
        "scenario_id": sid,
        "field_path": "external_data.benchmarks.saas_churn_p50",
        "value": 0.018,
        "source": "ChartMogul SaaS Benchmarks 2025",
        "confidence": "high",
    })
    assert out["ok"] is True
    # The scenario overrides now contains the new benchmark
    s = store.get(sid)
    assert s.overrides.get("external_data.benchmarks.saas_churn_p50.value") == 0.018


def test_track_import_real_data_stubbed(reg_with_run):
    _, reg, _, _ = reg_with_run
    h = reg["finance.track.import_real_data"].handler
    out = h({"source": "holded", "period": "2026-04"})
    assert "error" in out
    assert "v2" in out["error"].lower() or "not" in out["error"].lower()
