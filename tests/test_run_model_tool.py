"""finance.simulate.run_model: el modelo de negocio con las cifras del usuario (26-sep)."""
from asset_finance_modeler.mcp_server.tools.discover import handle_list_models, handle_run_model


def test_lista_incluye_modelos_de_negocio():
    nombres = {m["name"] for m in handle_list_models({})["models"]}
    assert {"business_generic", "business_restaurant"} <= nombres


def test_run_model_negocio_con_sus_cifras():
    r = handle_run_model({
        "model_id": "business_generic",
        "overrides": {
            "meta.horizon.periods": 60,
            "revenue": [{"name": "Servicios", "year1_amount": 120000, "growth_pct_yr": 0.2}],
            "cogs.pct_of_revenue": 0.1,
            "opex.fixed_lines": [{"name": "Personal", "year1_amount": 84000}, {"name": "Estructura", "year1_amount": 12000}],
            "capex.items": [],
        },
    })
    assert "error" not in r, r
    ingresos = r["income_statement"]["rows"]["revenue"]
    assert len(ingresos) == 5
    assert abs(ingresos[0] - 120000) < 1
    assert ingresos[1] > ingresos[0]


def test_run_model_ruta_mala_da_error_no_excepcion():
    r = handle_run_model({"model_id": "business_generic", "overrides": {"no.existe": 1}})
    assert r["error"] == "invalid_input"
    assert handle_run_model({"model_id": ""})["error"] == "model_id_required"
