"""Cuanto vale hoy un activo (26-sep): cuadres contra el propio motor."""
import pytest

from asset_finance_modeler.store.scenarios import en_espacio


@pytest.fixture()
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("ASSET_FINANCE_DB_PATH", str(tmp_path / "a.db"))


def test_empresa_cuadra_con_el_van_del_motor(db):
    from asset_finance_modeler.mcp_server.tools import assets as a
    from asset_finance_modeler.web_api.assets import _run_model

    k = _run_model("business_generic", {})["kpis"]
    v = a.handle_value({"model_id": "business_generic"})
    assert abs(v["van"] - k["npv"]) <= 1
    # Negocio en marcha: vale sus flujos sin la inversion inicial (900.000 en el anio 1).
    assert abs(v["valor_empresa"] - (v["van"] + 900_000 / 1.1)) <= 2
    assert v["inversion_inicial"] == 900_000 and "perpetuidad" in v["metodo"]
    # La celda central de la sensibilidad es el propio valor.
    fila = v["sensibilidad"]["tasas"].index(0.1)
    assert v["sensibilidad"]["valor_empresa"][fila][1] == v["valor_empresa"]


def test_multiplo_deuda_neta_y_rango(db):
    from asset_finance_modeler.mcp_server.tools import assets as a

    v = a.handle_value({"model_id": "business_generic", "multiplo_ebitda": 6, "deuda_neta": 200_000})
    assert v["multiplo"] == {"ebitda_referencia": 100_000, "multiplo": 6, "valor_empresa": 600_000, "valor_para_el_dueno": 400_000}
    assert v["rango_para_el_dueno"] == [400_000, v["valor_empresa"] - 200_000]


def test_piso_vida_finita_y_compra_fuera_de_los_flujos(db):
    from asset_finance_modeler.mcp_server.tools import assets as a

    v = a.handle_value({"model_id": "inmueble_alquiler"})
    assert v["crecimiento_final"] is None and v["dcf"]["valor_terminal"] == 0
    assert v["inversion_inicial"] == 267_500 and v["van"] == v["valor_empresa"] - 267_500
    assert v["tasa_descuento"] == 0.06


def test_tasa_por_debajo_del_crecimiento_no_revienta(db):
    from asset_finance_modeler.mcp_server.tools import assets as a

    v = a.handle_value({"model_id": "business_generic", "tasa": 0.02, "crecimiento": 0.03})
    assert v["dcf"]["valor_terminal"] == 0 and any("no converge" in n for n in v["notas"])


def test_un_activo_guardado_solo_en_su_espacio(db):
    from asset_finance_modeler.mcp_server.tools import assets as a

    with en_espacio("esp-A"):
        aid = a.handle_save({"model_id": "business_restaurant", "name": "Bar"})["id"]
        v = a.handle_value({"asset_id": aid, "deuda_neta": 50_000})
        assert v["activo"] == "Bar" and v["valor_para_el_dueno"] == v["valor_empresa"] - 50_000
    with en_espacio("esp-B"):
        assert a.handle_value({"asset_id": aid})["error"] == "not_found"
