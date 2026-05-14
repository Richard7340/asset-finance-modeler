from asset_finance_modeler.mcp_server.tools.discover import handle_list_models


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
