import pytest

from asset_finance_modeler.mcp_server.registry import build_registry
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore


@pytest.fixture
def reg_with_baseline(tmp_path):
    store = SQLiteScenarioStore(str(tmp_path / "s.db"))
    store.initialize()
    reg = build_registry(store, kb_db_path=str(tmp_path / "kb.db"), kb_index_path=str(tmp_path / "kb.faiss"))
    baseline_id = reg["finance.simulate.load_baseline"].handler(
        {"model": "gestnova", "preset": "gestnova"}
    )["scenario_id"]
    return reg, baseline_id


def test_workflows_list_returns_templates(reg_with_baseline):
    reg, _ = reg_with_baseline
    out = reg["finance.workflows.list"].handler({})
    ids = {w["id"] for w in out["workflows"]}
    assert "pricing_impact_analysis" in ids
    assert "valuation_summary" in ids


def test_workflows_describe(reg_with_baseline):
    reg, _ = reg_with_baseline
    out = reg["finance.workflows.describe"].handler({"workflow_id": "pricing_impact_analysis"})
    assert out["id"] == "pricing_impact_analysis"
    assert "inputs" in out
    input_names = {i["name"] for i in out["inputs"]}
    assert "base_scenario_id" in input_names
    assert "prices" in input_names


def test_workflows_describe_missing(reg_with_baseline):
    reg, _ = reg_with_baseline
    out = reg["finance.workflows.describe"].handler({"workflow_id": "nope"})
    assert "error" in out


def test_workflows_run_valuation_summary(reg_with_baseline):
    reg, baseline_id = reg_with_baseline
    out = reg["finance.workflows.run"].handler({
        "workflow_id": "valuation_summary",
        "inputs": {"scenario_id": baseline_id},
    })
    assert "enterprise_value" in out
    assert out["enterprise_value"] > 0
