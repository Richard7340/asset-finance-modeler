import pytest

from asset_finance_modeler.intelligence.embeddings import LocalEmbeddingProvider
from asset_finance_modeler.intelligence.knowledge.base import KnowledgeBase
from asset_finance_modeler.intelligence.knowledge.seed import seed_default_knowledge


@pytest.fixture
def kb(tmp_path):
    base = KnowledgeBase(
        db_path=str(tmp_path / "kb.db"),
        index_path=str(tmp_path / "kb.faiss"),
        embedding_provider=LocalEmbeddingProvider(),
    )
    base.initialize()
    return base


def test_seed_populates_knowledge_base(kb):
    count = seed_default_knowledge(kb)
    assert count >= 25  # we wrote 30 entries
    cats = {c["name"] for c in kb.list_categories()}
    assert "unit_economics" in cats
    assert "valuation" in cats
    assert "debt" in cats


def test_seeded_kb_search_returns_relevant_result(kb):
    seed_default_knowledge(kb)
    results = kb.search("how much should I pay to get a new SaaS customer?", top_k=3)
    titles = [r.entry.title for r in results]
    assert any("CAC" in t for t in titles)


def test_seeded_kb_search_in_spanish(kb):
    seed_default_knowledge(kb)
    results = kb.search("cuántos meses tarda en recuperarse el coste de un cliente nuevo", top_k=3)
    titles = [r.entry.title for r in results]
    assert any("Payback" in t or "CAC" in t for t in titles)
