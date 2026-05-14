import pytest

from asset_finance_modeler.intelligence.context.memory import ContextMemory
from asset_finance_modeler.intelligence.embeddings import LocalEmbeddingProvider


@pytest.fixture
def mem(tmp_path):
    m = ContextMemory(
        db_path=str(tmp_path / "ctx.db"),
        embedding_provider=LocalEmbeddingProvider(),
    )
    m.initialize()
    return m


def test_store_and_recent(mem):
    mem.store(tenant_id="t1", key="discussion-1", value="Talked about pricing 250", tags=["pricing"])
    mem.store(tenant_id="t1", key="discussion-2", value="Decided to run sensitivity on churn", tags=["churn"])
    recent = mem.recent(tenant_id="t1", limit=10)
    assert len(recent) == 2
    # most recent first
    assert recent[0].value == "Decided to run sensitivity on churn"


def test_search_semantic(mem):
    mem.store(tenant_id="t1", key="d1", value="The client asked about cash flow runway projections")
    mem.store(tenant_id="t1", key="d2", value="We covered the difference between LTV and CAC")
    mem.store(tenant_id="t1", key="d3", value="Today's weather is sunny")
    results = mem.search(tenant_id="t1", query="how long until we run out of cash?", top_k=2)
    values = [r.entry.value for r in results]
    assert any("runway" in v.lower() for v in values)


def test_multi_tenant_isolation(mem):
    mem.store(tenant_id="a", key="k1", value="company A private")
    mem.store(tenant_id="b", key="k2", value="company B private")
    results = mem.search(tenant_id="a", query="private", top_k=10)
    assert all(r.entry.tenant_id == "a" for r in results)
