"""Lo real con la frecuencia que se quiera (28-sep): diario, semanal, mensual…"""
from datetime import datetime

import pytest

from asset_finance_modeler.store.scenarios import en_espacio


@pytest.fixture()
def planta(tmp_path, monkeypatch):
    monkeypatch.setenv("ASSET_FINANCE_DB_PATH", str(tmp_path / "a.db"))
    from asset_finance_modeler.mcp_server.tools import assets as a
    with en_espacio("esp"):
        yield a.handle_save({"model_id": "solar_pv_50mw_spain", "name": "Planta"})["id"], tmp_path


def _store(tmp_path):
    from asset_finance_modeler.store.scenarios import SQLiteScenarioStore
    s = SQLiteScenarioStore(str(tmp_path / "a.db")); s.initialize(); return s


def test_la_produccion_se_puede_anotar_y_ver_por_dia_semana_y_mes(planta, monkeypatch):
    from asset_finance_modeler.mcp_server.tools.tracking import make_track_import, make_track_lines
    from asset_finance_modeler.web_api import actuals as A
    aid, tmp = planta
    st = _store(tmp)
    with en_espacio("esp"):
        lineas = {x["path"]: x for x in make_track_lines(st)({"scenario_id": aid})["lineas"]}
        assert "lineas.produccion.Producción" in lineas
        # Una semana de producción diaria.
        datos = [{"line_path": "lineas.produccion.Producción", "period_start": f"2030-09-{d:02d}", "value": 250} for d in range(23, 30)]
        assert make_track_import(st)({"scenario_id": aid, "actuals": datos})["ok"] is True
        monkeypatch.setattr(A, "_hoy", lambda: datetime(2030, 9, 30))
        asset = st.get(aid)
        reales = A._actuals_store().list(scenario_id=aid, line_path="lineas.produccion.Producción")
        dia = A.serie_real_vs_prevision(asset, reales, "lineas.produccion.Producción", "dia", "2030-09-23", "2030-09-29")
        assert [p["real"] for p in dia["puntos"]] == [250] * 7
        assert all(p["prevision"] > 0 for p in dia["puntos"])
        sem = A.serie_real_vs_prevision(asset, reales, "lineas.produccion.Producción", "semana", "2030-09-23", "2030-09-29")
        assert sem["puntos"][0]["real"] == 1750
        assert sem["puntos"][0]["prevision"] == pytest.approx(sum(p["prevision"] for p in dia["puntos"]), rel=1e-3)
        mes = A.serie_real_vs_prevision(asset, reales, "lineas.produccion.Producción", "mes", "2030-09-01", "2030-09-30")
        assert mes["puntos"][0]["real"] == 1750
        assert mes["resumen"]["periodos_con_dato"] == 1 and mes["resumen"]["cumplimiento_pct"] is not None


def test_estacionalidad_propia_y_la_tipica_solar(planta, monkeypatch):
    from asset_finance_modeler.web_api import actuals as A
    from asset_finance_modeler.mcp_server.tools import assets as a
    aid, tmp = planta
    st = _store(tmp)
    with en_espacio("esp"):
        monkeypatch.setattr(A, "_hoy", lambda: datetime(2030, 12, 31))
        s = st.get(aid)
        ene = A.serie_real_vs_prevision(s, [], "lineas.produccion.Producción", "mes", "2030-01-01", "2030-01-31")
        jul = A.serie_real_vs_prevision(s, [], "lineas.produccion.Producción", "mes", "2030-07-01", "2030-07-31")
        assert jul["puntos"][0]["prevision"] > 2 * ene["puntos"][0]["prevision"]
        assert ene["estacionalidad"].startswith("la típica")
        r = a.handle_configure({"asset_id": aid, "estacionalidad": [1] * 11 + [11]})
        assert "estacionalidad" in r["cambios"][0]
        s = st.get(aid)
        dic = A.serie_real_vs_prevision(s, [], "lineas.produccion.Producción", "mes", "2030-12-01", "2030-12-31")
        ene2 = A.serie_real_vs_prevision(s, [], "lineas.produccion.Producción", "mes", "2030-01-01", "2030-01-31")
        assert dic["estacionalidad"] == "la tuya" and dic["puntos"][0]["prevision"] == pytest.approx(11 * ene2["puntos"][0]["prevision"], rel=1e-3)


def test_configurar_renovable_y_empresa(planta, tmp_path):
    from asset_finance_modeler.mcp_server.tools import assets as a
    aid, _ = planta
    with en_espacio("esp"):
        r = a.handle_configure({"asset_id": aid, "degradacion": 0.006, "repowering": [{"anio": 20, "inversion": 3000000, "mas_potencia_pct": 0.1}],
                                "averias": [{"anio": 8, "perdida_pct": 0.05, "nombre": "Inversores"}], "precio": {"contrato": "merchant", "puntos": [60, 58, 55]}})
        assert not r.get("error"), r
        assert any("degradación" in c for c in r["cambios"]) and any("repowering" in c for c in r["cambios"]) and r["kpis"]
        g = a.handle_get({"asset_id": aid})
        assert g["overrides"]["capex_events"][0]["year"] == 19
        f = a.handle_save({"model_id": "business_restaurant", "name": "Bar"})["id"]
        r2 = a.handle_configure({"asset_id": f, "ingresos": [{"nombre": "Comidas", "curva": [500000, 650000, 700000]}, {"nombre": "Terraza", "importe": 80000, "crecimientos": [0.3, 0.1]}]})
        assert not r2.get("error"), r2
        lineas = a.handle_get({"asset_id": f})["overrides"]["revenue"]
        assert any(x["name"] == "Terraza" for x in lineas) and next(x for x in lineas if x["name"] == "Comidas")["curva"][1] == 650000
        malo = a.handle_configure({"asset_id": f, "degradacion": 0.01})
        assert any("renovables" in x for x in malo["avisos"])


def test_anotar_reales_la_pasa_a_la_cartera_sin_mover_su_anio(tmp_path, monkeypatch):
    """29-sep: la planta tenía producción real y la Cartera salía vacía."""
    monkeypatch.setenv("ASSET_FINANCE_DB_PATH", str(tmp_path / "a.db"))
    from asset_finance_modeler.mcp_server.tools import assets as a
    from asset_finance_modeler.mcp_server.tools.tracking import make_track_import
    from asset_finance_modeler.web_api.actuals import _model_start_year
    st = _store(tmp_path)
    with en_espacio("esp"):
        aid = a.handle_save({"model_id": "solar_pv_50mw_spain", "name": "P", "overrides": {"meta.start_date": "2025-01-01"}})["id"]
        assert st.get(aid).lifecycle == "opportunity"
        r = make_track_import(st)({"scenario_id": aid, "actuals": [{"line_path": "lineas.produccion.Producción", "period_start": "2026-01-01", "value": 500}]})
        assert r["pasado_a_operacion"] is True
        s = st.get(aid)
        assert s.lifecycle == "operational" and _model_start_year(s) == 2025


def test_si_ya_funciona_se_guarda_en_la_cartera(tmp_path, monkeypatch):
    monkeypatch.setenv("ASSET_FINANCE_DB_PATH", str(tmp_path / "a.db"))
    from asset_finance_modeler.mcp_server.tools import assets as a
    with en_espacio("esp"):
        r = a.handle_save({"model_id": "solar_pv_50mw_spain", "name": "Q", "en_operacion_desde": "2025-01-01"})
        assert r["lifecycle"] == "operational"


def test_la_repotenciacion_no_agranda_el_prestamo():
    """29-sep: 2,5 M sobre 3,5 M de inversión salían 2,86 M por la repotenciación del año 20."""
    from asset_finance_modeler.web_api.assets import _run_model
    ov = {"financing.senior.auto_size": False, "financing.max_leverage": 0.5}
    sin = _run_model("solar_pv_50mw_spain", ov)
    con = _run_model("solar_pv_50mw_spain", {**ov, "capex_events": [{"year": 20, "amount": 5_000_000, "label": "R"}]})
    assert sum(con["deuda"]["disposiciones"]) == pytest.approx(sum(sin["deuda"]["disposiciones"]))
    assert con["kpis"]["irr_equity"] < sin["kpis"]["irr_equity"]
