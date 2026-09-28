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
