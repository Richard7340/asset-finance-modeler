import pytest

from asset_finance_modeler.core.scenario import Scenario
from asset_finance_modeler.mcp_server.registry import build_registry
from asset_finance_modeler.mcp_server.tools.discover import (
    handle_describe_schema,
    handle_list_models,
    handle_list_presets,
    handle_load_baseline,  # noqa: F401
)
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore


def test_list_models_returns_gestnova():
    result = handle_list_models({})
    assert "models" in result
    names = [m["name"] for m in result["models"]]
    assert "gestnova" in names


def test_list_models_model_has_description():
    result = handle_list_models({})
    gn = next(m for m in result["models"] if m["name"] == "gestnova")
    assert "asset_type" in gn
    assert gn["asset_type"] == "saas"


def test_describe_schema_returns_json_schema():
    result = handle_describe_schema({"model": "gestnova"})
    assert "schema" in result
    schema = result["schema"]
    # JSON Schema shape
    assert schema.get("type") == "object"
    assert "properties" in schema
    # Expected top-level keys exist
    assert "revenue" in schema["properties"]
    assert "cost_of_revenue" in schema["properties"]


def test_describe_schema_unknown_model_raises():
    with pytest.raises(ValueError):
        handle_describe_schema({"model": "nonexistent"})


def test_list_presets_returns_gestnova():
    result = handle_list_presets({"model": "saas"})
    keys = [p["key"] for p in result["presets"]]
    assert "gestnova" in keys


def test_load_baseline_persists_scenario(tmp_path):
    store = SQLiteScenarioStore(str(tmp_path / "scn.db"))
    store.initialize()
    # The actual wired handler is closure-bound; here we exercise via build_registry
    registry = build_registry(store)
    result = registry["finance.simulate.load_baseline"].handler({"model": "gestnova", "preset": "gestnova"})
    assert "scenario_id" in result
    fetched = store.get(result["scenario_id"])
    assert isinstance(fetched, Scenario)
    assert fetched.is_canonical is True
