"""Lo que la app de Portfolio necesita de cada modelo (28-sep): deuda año a
año, caja, balance, valoración y los KPIs que ya se calculaban."""
import json
import math

import pytest

from asset_finance_modeler.web_api import models as M


@pytest.mark.parametrize("mid", ["solar_pv_50mw_spain", "business_industrial", "inmueble_alquiler"])
def test_deuda_y_caja_por_anio(mid):
    r = M.model_run(mid, M.RunBody(overrides={}))
    json.dumps(r, allow_nan=False)  # nada de infinitos ni NaN
    n = len(r["income_statement"]["years"])
    d = r["deuda"]
    for k in ("saldo", "intereses", "amortizacion", "disposiciones", "dscr"):
        assert len(d[k]) == n, k
    assert sum(d["disposiciones"]) > 0
    assert len(r["cash_flow"]["cash"]) == n
    assert r["kpis"].get("payback_years") is not None


def test_valoracion_y_balance_en_renovables():
    r = M.model_run("solar_pv_50mw_spain", M.RunBody(overrides={}))
    assert r["valoracion"]["enterprise_value"] == r["kpis"]["enterprise_value"]
    assert "debt" in r["balance"] and len(r["balance"]["debt"]) == len(r["income_statement"]["years"])
    assert all(v is None or math.isfinite(v) for v in r["deuda"]["dscr"])


def test_negocio_la_deuda_baja_con_lo_que_se_amortiza():
    d = M.model_run("business_industrial", M.RunBody(overrides={}))["deuda"]
    assert d["saldo"][1] == pytest.approx(d["saldo"][0] - d["amortizacion"][1], abs=2)
