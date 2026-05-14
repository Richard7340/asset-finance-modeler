import pytest

from asset_finance_modeler.intelligence.workflows.engine import WorkflowEngine
from asset_finance_modeler.intelligence.workflows.loader import (
    list_builtin_workflows,
    load_workflow,
)


def test_list_builtin_workflows_returns_at_least_4():
    workflows = list_builtin_workflows()
    ids = {w["id"] for w in workflows}
    assert "pricing_impact_analysis" in ids
    assert "runway_diagnosis" in ids
    assert "unit_econ_review" in ids
    assert "valuation_summary" in ids


def test_load_workflow_parses_yaml():
    wf = load_workflow("pricing_impact_analysis")
    assert wf["id"] == "pricing_impact_analysis"
    assert "inputs" in wf
    assert "steps" in wf


def test_engine_variable_substitution():
    eng = WorkflowEngine(tool_dispatcher=lambda name, args: {"echo": args})
    workflow = {
        "id": "echo_test",
        "inputs": [{"name": "x", "type": "number"}],
        "steps": [
            {"id": "echo", "tool": "test.echo", "args": {"value": "${x}"}, "capture": "result"},
        ],
        "output": {"got": "${result.echo.value}"},
    }
    out = eng.run(workflow, {"x": 42})
    assert out["got"] == 42


def test_engine_runs_pricing_impact_via_mock_dispatcher():
    called: list[tuple[str, dict]] = []

    def mock(name, args):
        called.append((name, args))
        if name == "finance.simulate.clone_scenario":
            return {"scenario_id": f"clone-{args.get('name', 'x')}", "name": args.get("name", "x")}
        if name == "finance.simulate.run":
            return {"summary": {"revenue_y1": 100000}}
        if name == "finance.simulate.compare":
            return {"table": {"scenarios": ["a", "b", "c"], "metrics": {"revenue_y1": [100, 200, 300]}}}
        return {}

    eng = WorkflowEngine(tool_dispatcher=mock)
    wf = load_workflow("pricing_impact_analysis")
    out = eng.run(wf, {"base_scenario_id": "scn-base", "prices": [200, 300, 400]})
    # 3 clones + 3 runs + 1 compare = 7 tool calls
    assert len(called) >= 7
    tools_called = [c[0] for c in called]
    assert tools_called.count("finance.simulate.clone_scenario") == 3
    assert tools_called.count("finance.simulate.run") == 3
    assert "comparison" in out


def test_engine_required_input_missing_raises():
    eng = WorkflowEngine(tool_dispatcher=lambda n, a: {})
    workflow = {
        "id": "x", "inputs": [{"name": "must_have", "type": "string", "required": True}],
        "steps": [], "output": {},
    }
    with pytest.raises(ValueError, match="required input"):
        eng.run(workflow, {})
