"""Cada espacio solo ve lo suyo (26-sep: list_scenarios devolvia los de todos)."""
from fastapi.testclient import TestClient

from asset_finance_modeler.core.scenario import Scenario
from asset_finance_modeler.mcp_server import http_server
from asset_finance_modeler.mcp_server.registry import ToolSpec
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore, en_espacio, espacio_actual


def test_el_almacen_guarda_y_filtra_por_el_espacio_de_la_llamada(tmp_path):
    store = SQLiteScenarioStore(str(tmp_path / "s.db"))
    store.initialize()
    with en_espacio("espacio-A"):
        store.save(Scenario(id="s1", name="Solar A", base_model="solar_pv_50mw_spain"))
    with en_espacio("espacio-A"):
        assert [s.id for s in store.list()] == ["s1"]
        assert store.get("s1") is not None
    with en_espacio("espacio-B"):
        assert store.list() == []
        # Adivinar el id de otro espacio no sirve.
        assert store.get("s1") is None
    # Sin espacio (herramientas internas), como antes.
    assert store.get("s1").workspace_id == "espacio-A"


def test_call_fija_el_espacio_con_el_tenant_id():
    http_server._registry["t.espacio"] = ToolSpec(name="t.espacio", description="", input_schema={}, handler=lambda _a: {"espacio": espacio_actual()})
    with TestClient(http_server.app) as c:
        assert c.post("/call", json={"name": "t.espacio", "arguments": {"tenant_id": "cmt123"}}).json() == {"espacio": "cmt123"}
        assert c.post("/call", json={"name": "t.espacio", "arguments": {}}).json() == {"espacio": None}
