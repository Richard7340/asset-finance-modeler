"""Lo que se ve en el Portfolio, también por herramientas (28-sep)."""
import pytest

from asset_finance_modeler.store.scenarios import en_espacio


@pytest.fixture()
def fabrica(tmp_path, monkeypatch):
    monkeypatch.setenv("ASSET_FINANCE_DB_PATH", str(tmp_path / "a.db"))
    from asset_finance_modeler.mcp_server.tools import assets as a
    with en_espacio("esp"):
        yield a, a.handle_save({"model_id": "business_industrial", "name": "Fábrica"})["id"]


def test_serie_por_nombre_de_linea_y_cartera_y_deuda(fabrica):
    a, aid = fabrica
    with en_espacio("esp"):
        r = a.handle_series({"asset_id": "Fábrica", "linea": "ingresos", "cada": "mes"})
        assert r["linea"].lower().startswith("ingres") and r["ver_en_la_app"]["ruta"] == f"asset/{aid}/real"
        assert a.handle_series({"asset_id": aid, "linea": "cosa rara"})["error"] == "linea-desconocida"
        o = a.handle_overview({})
        assert o["activos"][0]["nombre"] == "Fábrica" and o["totales"]["count"] == 1
        d = a.handle_debt({"asset_id": aid})
        assert d["pedida"] > 0 and d["por_anio"][0]["saldo"] > 0 and d["ver_en_la_app"]["ruta"].endswith("/deuda")
