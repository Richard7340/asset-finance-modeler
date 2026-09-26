"""Activos del Portfolio por herramientas, en el espacio de la llamada (26-sep)."""
import pytest

from asset_finance_modeler.store.scenarios import en_espacio


@pytest.fixture()
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("ASSET_FINANCE_DB_PATH", str(tmp_path / "a.db"))
    return tmp_path


def test_guardar_listar_actualizar_promover_y_aislar(db):
    from asset_finance_modeler.mcp_server.tools import assets as a

    with en_espacio("espacio-A"):
        r = a.handle_save({"model_id": "real_estate_rental", "name": "Piso Calle Mayor", "overrides": {}})
        assert "id" in r, r
        aid = r["id"]
        assert [x["id"] for x in a.handle_list({})["assets"]] == [aid]
        g = a.handle_get({"asset_id": aid})
        assert g["name"] == "Piso Calle Mayor" and g["income_statement"]["rows"]["revenue"]
        u = a.handle_update({"asset_id": aid, "name": "Piso Mayor 3ºB"})
        assert u["name"] == "Piso Mayor 3ºB"
        p = a.handle_lifecycle({"asset_id": aid, "lifecycle": "operational", "tracking_frequency": "monthly"})
        assert p["lifecycle"] == "operational" and p["base_locked"] is True
        assert a.handle_update({"asset_id": aid, "overrides": {"x": 1}})["error"] == "base_locked"
    with en_espacio("espacio-B"):
        assert a.handle_list({})["assets"] == []
        assert a.handle_get({"asset_id": aid})["error"] == "not_found"
    # Sin espacio no se guarda nada.
    assert "workspace-required" in a.handle_save({"model_id": "business_generic", "name": "x"})["error"]


def test_modelos_y_su_esquema(db):
    from asset_finance_modeler.mcp_server.tools import assets as a

    ids = {m["id"] for m in a.handle_models({})["models"]}
    assert {"solar_pv_50mw_spain", "business_generic", "real_estate_rental", "svj_hybrid"} <= ids
    rutas = [x["path"] for x in a.handle_schema({"model_id": "business_generic"})["inputs"]]
    assert any(r.startswith("revenue") for r in rutas)
