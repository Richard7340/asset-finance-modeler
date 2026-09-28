"""La cartera para el cuadro general (28-sep): tipo, valor, deuda, caja,
series y consolidado por año natural, sin recalcular lo mismo dos veces."""
import pytest
from fastapi.testclient import TestClient

from asset_finance_modeler.store.scenarios import en_espacio


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    monkeypatch.setenv("ASSET_FINANCE_DB_PATH", str(tmp_path / "a.db"))
    monkeypatch.setenv("SIM_TOKEN", "tk")
    monkeypatch.setenv("SIM_ONLY", "1")
    from asset_finance_modeler.mcp_server.tools import assets as a
    with en_espacio("default"):
        a.handle_save({"model_id": "business_industrial", "name": "Fábrica"})
        a.handle_save({"model_id": "inmueble_alquiler", "name": "Piso"})
    from asset_finance_modeler.mcp_server.http_server import app
    return TestClient(app)


def test_cartera_con_todo_lo_del_cuadro(cliente, monkeypatch):
    from asset_finance_modeler.web_api import assets as A
    llamadas = []
    original = A._run_model
    monkeypatch.setattr(A, "_run_model", lambda m, o: (llamadas.append(m), original(m, o))[1])
    A._CACHE_DE_MODELOS.clear()
    j = cliente.get("/api/portfolio?t=tk").json()
    assert {x["name"] for x in j["assets"]} == {"Fábrica", "Piso"}
    fab = next(x for x in j["assets"] if x["name"] == "Fábrica")
    assert fab["tipo"] == "negocio" and fab["enterprise_value"] and fab["series"]["revenue"]
    piso = next(x for x in j["assets"] if x["name"] == "Piso")
    assert piso["tipo"] == "inmueble" and piso["deuda_viva"] is not None
    c = j["consolidado"]
    assert c["years"] and len(c["revenue"]) == len(c["years"])
    assert j["totals"]["enterprise_value"]
    # Segunda visita: sin recalcular.
    n = len(llamadas)
    cliente.get("/api/portfolio?t=tk")
    assert len(llamadas) == n


def test_valoracion_por_rest(cliente):
    j = cliente.get("/api/portfolio?t=tk").json()
    fab = next(x for x in j["assets"] if x["name"] == "Fábrica")
    v = cliente.get(f"/api/assets/{fab['id']}/valoracion?t=tk").json()
    assert v.get("valor_empresa") or v.get("valoracion", {}).get("valor_empresa"), v
    assert cliente.get("/api/assets/no-existe/valoracion?t=tk").status_code in (400, 404)
