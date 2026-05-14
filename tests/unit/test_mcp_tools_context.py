import pytest

from asset_finance_modeler.mcp_server.registry import build_registry
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore


@pytest.fixture
def reg(tmp_path):
    store = SQLiteScenarioStore(str(tmp_path / "s.db"))
    store.initialize()
    return build_registry(
        store,
        kb_db_path=str(tmp_path / "kb.db"),
        kb_index_path=str(tmp_path / "kb.faiss"),
        ctx_db_path=str(tmp_path / "ctx.db"),
    )


def test_context_store_and_recent(reg):
    store_tool = reg["finance.context.store"].handler
    recent_tool = reg["finance.context.recent"].handler

    store_tool({
        "tenant_id": "gestnova",
        "key": "session-2026-05-15",
        "value": "Cliente Pedro pidió analisis pricing 250",
        "tags": ["pricing", "pedro"],
    })
    out = recent_tool({"tenant_id": "gestnova", "limit": 5})
    assert len(out["entries"]) == 1
    assert out["entries"][0]["value"].startswith("Cliente Pedro")


def test_context_search(reg):
    store_tool = reg["finance.context.store"].handler
    search_tool = reg["finance.context.search"].handler

    store_tool({"tenant_id": "t", "key": "k", "value": "Discussion about reducing customer acquisition cost"})
    out = search_tool({"tenant_id": "t", "query": "how to reduce CAC", "top_k": 1})
    assert len(out["results"]) == 1
