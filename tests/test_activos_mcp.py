"""Activos del Portfolio por herramientas, en el espacio de la llamada (26-sep)."""
import pytest

from asset_finance_modeler.store.scenarios import en_espacio


@pytest.fixture()
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("ASSET_FINANCE_DB_PATH", str(tmp_path / "a.db"))
    return tmp_path


def test_guardar_listar_actualizar_promover_y_aislar(db):
    from asset_finance_modeler.mcp_server.tools import assets as a

    with en_espacio("espacio-A"):
        r = a.handle_save({"model_id": "real_estate_rental", "name": "Piso Calle Mayor", "overrides": {}})
        assert "id" in r, r
        aid = r["id"]
        assert [x["id"] for x in a.handle_list({})["assets"]] == [aid]
        g = a.handle_get({"asset_id": aid})
        assert g["name"] == "Piso Calle Mayor" and g["income_statement"]["rows"]["revenue"]
        u = a.handle_update({"asset_id": aid, "name": "Piso Mayor 3ºB"})
        assert u["name"] == "Piso Mayor 3ºB"
        p = a.handle_lifecycle({"asset_id": aid, "lifecycle": "operational", "tracking_frequency": "monthly"})
        assert p["lifecycle"] == "operational" and p["base_locked"] is True
        assert a.handle_update({"asset_id": aid, "overrides": {"x": 1}})["error"] == "base_locked"
    with en_espacio("espacio-B"):
        assert a.handle_list({})["assets"] == []
        assert a.handle_get({"asset_id": aid})["error"] == "not_found"
    # Sin espacio no se guarda nada.
    assert "workspace-required" in a.handle_save({"model_id": "business_generic", "name": "x"})["error"]


def test_modelos_y_su_esquema(db):
    from asset_finance_modeler.mcp_server.tools import assets as a

    ids = {m["id"] for m in a.handle_models({})["models"]}
    assert {"solar_pv_50mw_spain", "business_generic", "real_estate_rental", "svj_hybrid"} <= ids
    rutas = [x["path"] for x in a.handle_schema({"model_id": "business_generic"})["inputs"]]
    assert any(r.startswith("revenue") for r in rutas)


def test_carpeta_y_reglas_del_activo(db):
    """Como lo gestiona su agente: carpeta del VDR y reglas proveedor -> linea,
    que se cambian tambien con el activo en operacion (no tocan la base)."""
    from asset_finance_modeler.mcp_server.tools import assets as a

    with en_espacio("esp"):
        r = a.handle_save({"model_id": "inmueble_alquiler", "name": "Clinica", "carpeta": "/Activos/Clinica/",
                           "reglas": [{"proveedor": "Iberdrola", "linea": "Suministros"}, {"linea": "sin proveedor"}, "basura"]})
        assert r["carpeta"] == "Activos/Clinica" and r["reglas"] == [{"proveedor": "Iberdrola", "linea": "Suministros"}]
        a.handle_lifecycle({"asset_id": r["id"], "lifecycle": "operational"})
        u = a.handle_update({"asset_id": r["id"], "reglas": [{"nif": "B12345678", "linea": "IBI"}]})
        assert u["reglas"] == [{"nif": "B12345678", "linea": "IBI"}]
        lst = a.handle_list({})["assets"][0]
        assert lst["carpeta"] == "Activos/Clinica" and lst["reglas"][0]["nif"] == "B12345678"
        g = a.handle_get({"asset_id": r["id"]})
        assert g["lifecycle"] == "operational" and g["kpis"]["npv"] == r["kpis"]["npv"]


def test_fuentes_de_las_hipotesis(db):
    """De donde sale cada valor (web y fecha): se suman y se quitan con vacio."""
    from asset_finance_modeler.mcp_server.tools import assets as a

    with en_espacio("esp"):
        r = a.handle_save({"model_id": "inmueble_alquiler", "name": "Piso", "overrides": {"alquiler.renta_mensual": 950},
                           "fuentes": {"alquiler.renta_mensual": {"fuente": "https://www.idealista.com/informes", "fecha": "2026-09"}}})
        a.handle_update({"asset_id": r["id"], "fuentes": {"compra.precio": "lo dice el usuario"}})
        f = a.handle_get({"asset_id": r["id"]})["fuentes"]
        assert f["alquiler.renta_mensual"]["fecha"] == "2026-09" and f["compra.precio"] == {"fuente": "lo dice el usuario"}
        f = a.handle_update({"asset_id": r["id"], "fuentes": {"compra.precio": None}})["fuentes"]
        assert list(f) == ["alquiler.renta_mensual"]


def test_ipc_de_una_vez(db):
    """El IPC a todas las subidas (o solo ingresos/gastos); lo fijado a mano manda
    y un IPC nuevo sustituye al anterior."""
    from asset_finance_modeler.mcp_server.tools import assets as a

    ov, rutas = a.aplicar_ipc("solar_pv_50mw_spain", {"revenue[1].escalation_pct_yr": 0.0}, 0.03)
    assert set(rutas) == {"revenue[0].escalation_pct_yr", "opex.opex_escalation_pct_yr"}
    assert ov["revenue[1].escalation_pct_yr"] == 0.0 and "valuation.terminal_growth_rate" not in ov
    assert a.aplicar_ipc("inmueble_alquiler", {}, {"valor": 0.025, "a": "gastos"})[1] == ["gastos.subida_anual"]
    assert set(a.aplicar_ipc("saas_gestnova", {}, 0.02)[1]) == {"meta.inflation_annual", "revenue.sources[0].pricing.price_escalation_annual"}
    assert "ipc-fuera-de-rango" in a.handle_save({"model_id": "business_generic", "name": "x", "ipc": 3, "workspace_id": "w"})["error"]
    with en_espacio("esp"):
        r = a.handle_save({"model_id": "inmueble_alquiler", "name": "Piso", "ipc": 0.03})
        assert set(r["ipc_aplicado_a"]) == {"alquiler.subida_anual", "gastos.subida_anual"}
        u = a.handle_update({"asset_id": r["id"], "ipc": {"valor": 0.02, "a": "gastos"}})
        ov = a.handle_get({"asset_id": r["id"]})["overrides"]
        assert u["ipc_aplicado_a"] == ["gastos.subida_anual"] and ov == {"gastos.subida_anual": 0.02}
        a.handle_lifecycle({"asset_id": r["id"], "lifecycle": "operational"})
        assert a.handle_update({"asset_id": r["id"], "ipc": 0.04})["error"] == "base_locked"


def test_anios_de_proyeccion_en_cualquier_modelo(db):
    """8 anios son 96 meses en los modelos mensuales y 8 en el del piso; antes
    'periods: 8' en uno mensual dejaba la proyeccion vacia."""
    from asset_finance_modeler.mcp_server.tools import assets as a

    assert a.aplicar_anios("business_restaurant", {}, 8) == {"meta.horizon.periods": 96}
    assert a.aplicar_anios("inmueble_alquiler", {}, 8) == {"horizonte_anios": 8}
    assert a.aplicar_anios("svj_hybrid", {}, 20) == {"fv.meta.horizon.periods": 240, "bess.meta.horizon.periods": 240}
    assert a.aplicar_anios("business_generic", {"meta.horizon.frequency": "Q"}, 5)["meta.horizon.periods"] == 20
    with en_espacio("esp"):
        r = a.handle_save({"model_id": "business_restaurant", "name": "Bar", "anios": 8})
        g = a.handle_get({"asset_id": r["id"]})
        assert len(g["income_statement"]["rows"]["revenue"]) == 8
        assert a.handle_value({"asset_id": r["id"]})["anios"] == 8
    assert "sin-flujos" in a.handle_value({"model_id": "business_restaurant", "overrides": {"meta.horizon.periods": 8}})["error"]


def test_ipc_como_curva_anio_a_anio(db):
    from asset_finance_modeler.mcp_server.tools import assets as a
    from asset_finance_modeler.web_api.assets import _run_model

    ov, rutas = a.aplicar_ipc("business_generic", {}, {"curva": [0.04, 0.03, 0.02], "a": "gastos"})
    assert rutas == ["inflacion"] and ov["inflacion"] == {"curva": [0.04, 0.03, 0.02], "aplicar_a": "gastos"}
    assert "curva-no-soportada" in str(pytest.raises(ValueError, a.aplicar_ipc, "solar_pv_50mw_spain", {}, [0.03]).value)
    # Piso: la renta sube 4 %, 3 % y luego 2 % cada anio.
    r = _run_model("inmueble_alquiler", {"inflacion": {"curva": [0.04, 0.03, 0.02], "aplicar_a": "ingresos"}, "alquiler.meses_vacios_anio": 0, "alquiler.impagos_pct": 0})
    rentas = r["lineas"]["ingresos"]["Rentas"]
    assert abs(rentas[1] / rentas[0] - 1.04) < 0.001 and abs(rentas[3] / rentas[2] - 1.02) < 0.001 and abs(rentas[5] / rentas[4] - 1.02) < 0.001
    # Empresa: gastos fijos con la curva; las lineas para anotar lo real, igual.
    e = _run_model("business_generic", {"inflacion": {"curva": [0.05], "aplicar_a": "gastos"}})
    g = next(iter(e["lineas"]["gastos"].values()))
    assert abs(g[1] / g[0] - 1.05) < 0.001


def test_no_duplica_y_entiende_el_nombre(db):
    """27-sep: el agente guardo otra vez la clinica para ponerle una regla, y
    pidio la valoracion por su nombre."""
    from asset_finance_modeler.mcp_server.tools import assets as a

    with en_espacio("esp"):
        aid = a.handle_save({"model_id": "business_generic", "name": "Clínica Dental Centro"})["id"]
        r = a.handle_save({"model_id": "business_generic", "name": "clínica  dental centro", "reglas": [{"proveedor": "Iberdrola"}]})
        assert r["error"] == "ya-existe" and r["asset_id"] == aid and len(a.handle_list({})["assets"]) == 1
        assert a.handle_save({"model_id": "business_generic", "name": "Clínica Dental Centro", "duplicar": True})["id"] != aid
        a.handle_delete({"asset_id": [x for x in a.handle_list({})["assets"] if x["id"] != aid][0]["id"]})
        assert a.handle_value({"asset_id": "Clínica Dental Centro"})["activo"] == "Clínica Dental Centro"
        assert a.handle_update({"asset_id": "Clínica Dental Centro", "reglas": [{"proveedor": "Iberdrola", "linea": "Suministros"}]})["id"] == aid
