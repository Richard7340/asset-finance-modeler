"""Operativa diaria de un activo: lineas por separado y validadas (26-sep)."""
import pytest

from asset_finance_modeler.store.scenarios import en_espacio


@pytest.fixture()
def piso(tmp_path, monkeypatch):
    monkeypatch.setenv("ASSET_FINANCE_DB_PATH", str(tmp_path / "a.db"))
    from asset_finance_modeler.mcp_server.tools import assets as a
    with en_espacio("esp"):
        yield a.handle_save({"model_id": "real_estate_rental", "name": "Piso"})["id"], tmp_path


def _store(tmp_path):
    from asset_finance_modeler.store.scenarios import SQLiteScenarioStore
    s = SQLiteScenarioStore(str(tmp_path / "a.db")); s.initialize(); return s


def test_lineas_por_separado_y_anotar_por_nombre(piso):
    from asset_finance_modeler.mcp_server.tools.tracking import make_track_import, make_track_lines
    aid, tmp = piso
    st = _store(tmp)
    with en_espacio("esp"):
        lineas = [x["path"] for x in make_track_lines(st)({"scenario_id": aid})["lineas"]]
        assert "lineas.gastos.Mantenimiento" in lineas and "lineas.ingresos.Rentas" in lineas
        ok = make_track_import(st)({"scenario_id": aid, "actuals": [{"line_path": "Mantenimiento", "period_start": "2026-03-01", "value": 300}]})
        assert ok["ok"] is True
        ibi = make_track_import(st)({"scenario_id": aid, "actuals": [{"line_path": "IBI", "period_start": "2026-03-01", "value": 450}]})
        assert ibi["ok"] is True  # -> lineas.gastos.Comunidad+IBI+seguros
        mal = make_track_import(st)({"scenario_id": aid, "actuals": [{"line_path": "Seguro del coche", "period_start": "2026-03-01", "value": 300}]})
        assert mal["error"] == "unknown-line" and "lineas.gastos.Mantenimiento" in mal["lineas"]
