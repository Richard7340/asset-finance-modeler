"""Modelo inmobiliario profesional (26-sep): cifras comprobadas a mano."""
from asset_finance_modeler.assets.inmobiliario.modelo import InmuebleConfig, ejecutar, impuesto_ahorro, tir


def test_compra_hipoteca_rentabilidad_y_venta():
    r = ejecutar(InmuebleConfig())
    k, d = r["kpis"], r["detalle"]
    assert d["compra"]["ITP"] == 15000 and d["compra"]["inversion_total"] == 267500
    assert k["cuota_hipoteca_mensual"] == 829.87
    assert k["rentabilidad_bruta"] == 0.0528 and k["rentabilidad_neta"] == 0.0381
    assert k["dscr_min"] == 1.02
    assert d["venta"]["precio"] == 304749 and abs(d["venta"]["impuesto"] - 17342) <= 1
    # Accionista con hipoteca por encima del proyecto (apalancamiento positivo aqui).
    assert k["irr_equity"] > k["irr_project"] > 0
    assert list(r["lineas"]["gastos"]) == ["IBI", "Comunidad", "Seguro del hogar", "Mantenimiento"]


def test_obra_nueva_iva_y_ajd_y_sin_hipoteca():
    cfg = InmuebleConfig.model_validate({"compra": {"precio": 200000, "obra_nueva": True}, "hipoteca": {"ltv": 0}})
    r = ejecutar(cfg)
    assert r["detalle"]["compra"]["IVA"] == 20000 and r["detalle"]["compra"]["AJD"] == 3000
    assert r["kpis"]["irr_equity"] == r["kpis"]["irr_project"] or abs(r["kpis"]["irr_equity"] - r["kpis"]["irr_project"]) < 0.002
    assert r["kpis"]["dscr_min"] is None


def test_sociedad_y_reduccion_por_vivienda():
    alto = {"alquiler": {"renta_mensual": 2500}, "hipoteca": {"ltv": 0}}
    part = ejecutar(InmuebleConfig.model_validate({**alto, "impuestos": {"regimen": "particular", "reduccion_vivienda_pct": 0.5, "tipo_marginal_irpf": 0.3}}))
    soc = ejecutar(InmuebleConfig.model_validate({**alto, "impuestos": {"regimen": "sociedad"}}))
    base = part["income_statement"]["rows"]["ebt"][0]
    assert abs(part["income_statement"]["rows"]["tax"][0] - base * 0.5 * 0.3) <= 1
    assert abs(soc["income_statement"]["rows"]["tax"][0] - base * 0.25) <= 1


def test_tramos_del_ahorro_y_tir():
    assert impuesto_ahorro(80269) == 6000 * 0.19 + 44000 * 0.21 + 30269 * 0.23
    assert impuesto_ahorro(-5) == 0
    assert abs(tir([-100, 110]) - 0.10) < 1e-4
    assert tir([100, 50]) is None


def test_como_activo_y_seguimiento_por_lineas(tmp_path, monkeypatch):
    monkeypatch.setenv("ASSET_FINANCE_DB_PATH", str(tmp_path / "a.db"))
    from asset_finance_modeler.mcp_server.tools import assets as a
    from asset_finance_modeler.store.scenarios import en_espacio
    with en_espacio("esp"):
        s = a.handle_save({"model_id": "inmueble_alquiler", "name": "Piso Mayor 3B", "overrides": {"compra.precio": 180000, "alquiler.renta_mensual": 900}})
        assert s["kpis"]["total_capex"] == round(180000 * 1.06 + 2500)
        esquema = [x["path"] for x in a.handle_schema({"model_id": "inmueble_alquiler"})["inputs"]]
        assert "hipoteca.ltv" in esquema and "impuestos.regimen" in esquema
