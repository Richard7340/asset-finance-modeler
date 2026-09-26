"""Financiacion de una empresa (26-sep): varios prestamos, hipoteca y leasing a
la vez, deuda que ya existe, y la rentabilidad real del socio."""
from asset_finance_modeler.web_api.assets import _run_model

ICO = {"nombre": "ICO", "importe": 500000, "tipo_interes": 0.045, "plazo_anios": 7, "carencia_meses": 12}
LEASING = {"nombre": "Leasing equipos", "tipo": "leasing", "importe": 200000, "tipo_interes": 0.06,
           "plazo_anios": 5, "valor_residual": 20000, "comision_apertura_pct": 0.01}


def test_cuotas_carencia_leasing_y_comision():
    r = _run_model("business_generic", {"financing.prestamos": [ICO, LEASING]})
    ico, lea = r["summary"]["prestamos"]
    assert ico["cuota_anual_inicial"] == 22500  # carencia: solo intereses
    # 180.000 a la francesa al 6 % en 5 anios + intereses de la opcion de compra.
    assert lea["cuota_anual_inicial"] == round(180000 * 0.06 / (1 - 1.06 ** -5) + 20000 * 0.06)
    assert r["income_statement"]["rows"]["interest_expense"][0] == 22500 + 12000 + 2000
    # Entra el dinero de los dos el primer anio; el anio 5 se paga la opcion de compra.
    assert r["cash_flow"]["cff"][0] > 600000
    sin_residual = _run_model("business_generic", {"financing.prestamos": [ICO, {**LEASING, "valor_residual": 0}]})
    assert r["cash_flow"]["cff"][4] < sin_residual["cash_flow"]["cff"][4]


def test_el_socio_no_es_el_proyecto():
    base = _run_model("business_generic", {})["kpis"]
    k = _run_model("business_generic", {"financing.prestamos": [ICO, LEASING]})["kpis"]
    assert base["irr_equity"] == base["irr_project"]  # sin deuda, lo mismo
    assert k["irr_project"] == base["irr_project"] and k["npv"] == base["npv"]  # el proyecto no depende de la deuda
    assert k["irr_equity"] > k["irr_project"]  # deuda barata: el socio gana mas
    assert k["dscr_min"] < 1  # y se ve que un anio no llega a cubrir la cuota


def test_deuda_que_ya_existe_se_paga_sin_entrada_de_caja():
    r = _run_model("business_generic", {"capex.items": [], "financing.prestamos": [
        {"nombre": "Hipoteca del local", "tipo": "hipoteca", "importe": 300000, "tipo_interes": 0.035, "plazo_anios": 20, "ya_dispuesto": True}]})
    assert r["cash_flow"]["cff"][0] < 0 and r["summary"]["prestamos"][0]["ya_dispuesto"] is True
    assert r["income_statement"]["rows"]["interest_expense"][0] == 10500


def test_venta_al_final_en_la_caja_del_socio():
    k = _run_model("real_estate_rental", {})["kpis"]
    assert k["irr_equity"] > k["irr_project"] > 0


def test_la_valoracion_resta_la_deuda_que_ya_tiene():
    from asset_finance_modeler.mcp_server.tools import assets as a

    v = a.handle_value({"model_id": "business_generic", "overrides": {"financing.prestamos": [
        {"nombre": "Hipoteca", "importe": 300000, "tipo_interes": 0.035, "plazo_anios": 20, "ya_dispuesto": True}]}})
    assert v["deuda_neta"] == 300000 and v["valor_para_el_dueno"] == v["valor_empresa"] - 300000
    assert v["notas"][0].startswith("Deuda neta tomada")
