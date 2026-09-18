"""La base de conocimiento nace con el conocimiento de serie.

seed_default_knowledge existia pero solo la llamaban los tests: en produccion
finance.knowledge.list_categories devolvia [] y cualquier busqueda ("TIR",
"payback") volvia vacia. Visto por el conector de Gestnova el 18-sep-2026.
"""
from asset_finance_modeler.mcp_server.registry import build_registry
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore


def _reg(tmp_path):
    store = SQLiteScenarioStore(str(tmp_path / "scn.db"))
    store.initialize()
    return build_registry(store, kb_db_path=str(tmp_path / "kb.db"), kb_index_path=str(tmp_path / "kb.faiss"))


def _total(reg):
    cats = reg["finance.knowledge.list_categories"].handler({})["categories"]
    return sum(c["count"] for c in cats)


def test_una_base_nueva_trae_el_conocimiento_de_serie(tmp_path):
    reg = _reg(tmp_path)
    assert _total(reg) >= 25
    res = reg["finance.knowledge.search"].handler({"query": "cuánto tarda en recuperarse el coste de un cliente", "top_k": 3})
    assert res["results"]


def test_arrancar_dos_veces_no_duplica(tmp_path):
    primero = _total(_reg(tmp_path))
    segundo = _total(_reg(tmp_path))
    assert segundo == primero
