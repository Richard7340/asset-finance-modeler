"""Renovables (26-sep): recortes, costes propios, IVPEE, desmantelamiento,
comision de la deuda y lock-up del reparto al socio."""
from asset_finance_modeler.web_api.assets import _run_model

M = "solar_pv_50mw_spain"


def _k(ov):
    return _run_model(M, ov)["kpis"]


def test_por_defecto_nada_cambia():
    assert _k({})["npv"] == 2_354_276


def test_recorte_fijo_y_por_curva_bajan_ingresos():
    base = _run_model(M, {})["income_statement"]["rows"]["revenue"]
    r5 = _run_model(M, {"losses.curtailment_pct": 0.05})["income_statement"]["rows"]["revenue"]
    anio = next(i for i, x in enumerate(base) if x > 0)
    assert abs(r5[anio] / base[anio] - 0.95) < 0.01
    curva = _run_model(M, {"losses.curtailment_curve": [0.0, 0.10]})["income_statement"]["rows"]["revenue"]
    assert abs(curva[anio] - base[anio]) <= 1 and abs(curva[anio + 3] / base[anio + 3] - 0.90) < 0.01


def test_ivpee_lineas_propias_y_desmantelamiento_son_opex():
    base = _k({})
    for ov in ({"opex.generation_tax_pct": 0.07},
               {"opex.other_lines": [{"name": "Representacion de mercado", "eur_per_mwh": 0.8}]},
               {"opex.decommissioning": {"cost_eur": 2_000_000, "accrue_years": 5}}):
        assert _k(ov)["npv"] < base["npv"], ov
    ebitda_b = _run_model(M, {})["income_statement"]["rows"]["ebitda"]
    ebitda_d = _run_model(M, {"opex.decommissioning": {"cost_eur": 2_000_000, "accrue_years": 5}})["income_statement"]["rows"]["ebitda"]
    assert sum(ebitda_b) - sum(ebitda_d) == 2_000_000 or abs(sum(ebitda_b) - sum(ebitda_d) - 2_000_000) <= 30
    assert ebitda_b[:-5] == ebitda_d[:-5]


def test_comision_solo_toca_al_socio():
    b, f = _k({}), _k({"financing.upfront_fee_pct": 0.02})
    assert f["npv"] == b["npv"] and f["irr_equity"] < b["irr_equity"]


def test_lockup_retrasa_el_reparto():
    b = _k({})
    for ov in ({"financing.equity.lockup_dscr": 2.5}, {"financing.equity.distribution_lock_years": 6}):
        k = _k(ov)
        assert k["npv"] == b["npv"] and k["irr_equity"] < b["irr_equity"], ov


def _prod(ov):
    return _run_model(M, ov)["income_statement"]["rows"]["revenue"]


def test_curva_de_rendimiento_propia():
    base = _run_model(M, {"degradation": {"type": "none"}})["income_statement"]["rows"]["revenue"]
    r = _run_model(M, {"degradation": {"type": "custom", "curve": [1.0, 0.97, 0.96]}})["income_statement"]["rows"]["revenue"]
    anio = next(i for i, x in enumerate(base) if x > 0)
    assert abs(r[anio] - base[anio]) <= 1
    assert abs(r[anio + 1] / base[anio + 1] - 0.97) < 0.005 and abs(r[anio + 5] / base[anio + 5] - 0.96) < 0.005


def test_caida_por_equipos_solo_esos_anios():
    base = _prod({})
    r = _prod({"losses.equipment_events": [{"year": 3, "loss_pct": 0.10, "years": 2, "label": "Inversores"}]})
    anio = next(i for i, x in enumerate(base) if x > 0)
    # Cuenta anios de OPERACION (desde la puesta en marcha, que puede caer a
    # mitad de anio natural): se pierde un 10 % de unos dos anios de ingresos.
    assert abs(r[anio] - base[anio]) <= 1 and abs(r[-1] - base[-1]) <= 1
    perdido = sum(base) - sum(r)
    assert abs(perdido / (0.10 * (base[anio + 2] + base[anio + 3])) - 1) < 0.05


def test_repowering_con_mas_potencia():
    ev = {"year": 15, "amount": 5_000_000, "resets_degradation": True, "label": "Repowering"}
    solo = _prod({"capex_events": [ev]})
    mas = _prod({"capex_events": [{**ev, "capacity_uplift_pct": 0.2}]})
    assert abs(mas[16] / solo[16] - 1.2) < 0.01 and abs(mas[10] - solo[10]) <= 1


def test_tramo_con_plazo_cero_es_que_no_hay_deuda():
    """27-sep: "100 % equity" llego como mezzanine.tenor_years 0 y max_leverage 0."""
    k = _k({"financing.max_leverage": 0, "financing.senior.auto_size": False, "financing.mezzanine.tenor_years": 0,
            "financing.reserves.dsra_months": 0})
    assert k["irr_equity"] == k["irr_project"]
    assert _k({"financing.senior.tenor_years": 0})["npv"] == _k({})["npv"]
