from asset_finance_modeler.intelligence.knowledge.retriever import KBRetriever


def test_retriever_search_concept():
    retriever = KBRetriever()
    retriever.initialize()
    results = retriever.search("DSCR debt service", top_k=3)
    assert len(results) >= 1


def test_retriever_search_benchmark():
    retriever = KBRetriever()
    retriever.initialize()
    results = retriever.search("solar CAPEX cost", top_k=3)
    assert len(results) >= 1


def test_retriever_filter_by_layer():
    retriever = KBRetriever()
    retriever.initialize()
    results = retriever.search("solar", top_k=5, layer="concept")
    assert all(r.layer == "concept" for r in results)
