import pytest

from asset_finance_modeler.intelligence.embeddings import LocalEmbeddingProvider
from asset_finance_modeler.intelligence.knowledge.base import KnowledgeBase, KnowledgeEntry


@pytest.fixture
def kb(tmp_path):
    base = KnowledgeBase(
        db_path=str(tmp_path / "kb.db"),
        index_path=str(tmp_path / "kb.faiss"),
        embedding_provider=LocalEmbeddingProvider(),
    )
    base.initialize()
    return base


def test_add_and_get(kb):
    entry_id = kb.add(KnowledgeEntry(
        title="LTV definition",
        content="Lifetime Value (LTV) is the total revenue a customer generates during their relationship with the business.",
        category="unit_economics",
        tags=["ltv", "metric"],
    ))
    fetched = kb.get(entry_id)
    assert fetched is not None
    assert fetched.title == "LTV definition"
    assert "ltv" in fetched.tags


def test_search_semantic(kb):
    kb.add(KnowledgeEntry(
        title="CAC",
        content="Customer Acquisition Cost: total marketing + sales spend / new customers acquired.",
        category="unit_economics",
    ))
    kb.add(KnowledgeEntry(
        title="DCF",
        content="Discounted Cash Flow valuation method discounts future free cash flows to present value.",
        category="valuation",
    ))
    kb.add(KnowledgeEntry(
        title="Stock photography",
        content="Stock photography refers to professional photographs of common places, landmarks, nature, etc.",
        category="unrelated",
    ))

    results = kb.search("how much does it cost to acquire a new customer?", top_k=2)
    assert len(results) == 2
    # CAC should rank first
    assert results[0].entry.title == "CAC"


def test_search_with_category_filter(kb):
    kb.add(KnowledgeEntry(title="LTV", content="LTV is...", category="unit_economics"))
    kb.add(KnowledgeEntry(title="DCF", content="DCF method...", category="valuation"))

    results = kb.search("valuation method", top_k=5, category="valuation")
    titles = {r.entry.title for r in results}
    assert "DCF" in titles
    assert "LTV" not in titles


def test_list_categories(kb):
    kb.add(KnowledgeEntry(title="A", content="a", category="cat1"))
    kb.add(KnowledgeEntry(title="B", content="b", category="cat2"))
    kb.add(KnowledgeEntry(title="C", content="c", category="cat1"))
    cats = kb.list_categories()
    assert {"cat1", "cat2"} == set(c["name"] for c in cats)
    counts = {c["name"]: c["count"] for c in cats}
    assert counts["cat1"] == 2


def test_multi_tenant_isolation(kb):
    kb.add(KnowledgeEntry(title="Tenant A info", content="proprietary A", tenant_id="company-a"))
    kb.add(KnowledgeEntry(title="Tenant B info", content="proprietary B", tenant_id="company-b"))
    kb.add(KnowledgeEntry(title="Global info", content="shared", tenant_id=None))

    results_a = kb.search("proprietary", top_k=10, tenant_id="company-a")
    titles_a = {r.entry.title for r in results_a}
    assert "Tenant A info" in titles_a
    assert "Tenant B info" not in titles_a
    # Global entries visible to all tenants
    assert "Global info" in titles_a
