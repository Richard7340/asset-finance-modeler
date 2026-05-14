import pytest

from asset_finance_modeler.mcp_server.registry import build_registry
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore


@pytest.fixture
def reg(tmp_path):
    store = SQLiteScenarioStore(str(tmp_path / "scn.db"))
    store.initialize()
    return build_registry(store, kb_db_path=str(tmp_path / "kb.db"), kb_index_path=str(tmp_path / "kb.faiss"))


def test_knowledge_search_tool_returns_results(reg):
    add = reg["finance.knowledge.add"].handler
    add({
        "title": "Test concept",
        "content": "Customer Acquisition Cost is fundamental for SaaS",
        "category": "test",
    })
    search = reg["finance.knowledge.search"].handler
    out = search({"query": "how do I measure customer acquisition?", "top_k": 3})
    assert "results" in out
    assert len(out["results"]) >= 1
    assert "score" in out["results"][0]


def test_knowledge_list_categories(reg):
    add = reg["finance.knowledge.add"].handler
    add({"title": "A", "content": "a", "category": "cat1"})
    add({"title": "B", "content": "b", "category": "cat2"})
    list_cats = reg["finance.knowledge.list_categories"].handler
    out = list_cats({})
    names = [c["name"] for c in out["categories"]]
    assert "cat1" in names
    assert "cat2" in names


def test_knowledge_add_returns_id(reg):
    add = reg["finance.knowledge.add"].handler
    out = add({"title": "New entry", "content": "Content here", "category": "test"})
    assert "id" in out
    assert out["id"].startswith("kn-")
