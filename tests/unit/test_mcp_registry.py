from asset_finance_modeler.mcp_server.registry import ToolSpec, build_registry


def test_tool_spec_dataclass():
    spec = ToolSpec(
        name="finance.simulate.test",
        description="Test tool",
        input_schema={"type": "object", "properties": {}},
        handler=lambda args: {"ok": True},
    )
    assert spec.name == "finance.simulate.test"
    assert spec.handler({}) == {"ok": True}


def test_registry_contains_simulate_tools():
    registry = build_registry(store=None)
    tool_names = set(registry.keys())
    # At minimum these should exist after the full plan is complete; T1 only needs list_models
    assert "finance.simulate.list_models" in tool_names


def test_registry_handler_callable():
    registry = build_registry(store=None)
    spec = registry["finance.simulate.list_models"]
    result = spec.handler({})
    assert isinstance(result, dict) or isinstance(result, list)
