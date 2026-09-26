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
