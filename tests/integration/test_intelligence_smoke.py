"""Full intelligent toolkit smoke test:
- Seed knowledge base
- Run a workflow that touches multiple tools
- Store + retrieve context
- All multi-tenant
"""
from asset_finance_modeler.intelligence.embeddings import LocalEmbeddingProvider
from asset_finance_modeler.intelligence.knowledge.base import KnowledgeBase
from asset_finance_modeler.intelligence.knowledge.seed import seed_default_knowledge
from asset_finance_modeler.mcp_server.registry import build_registry
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore


def test_intelligence_full_workflow(tmp_path):
    # Set up everything
    scn_store = SQLiteScenarioStore(str(tmp_path / "s.db"))
    scn_store.initialize()

    kb = KnowledgeBase(
        db_path=str(tmp_path / "kb.db"),
        index_path=str(tmp_path / "kb.faiss"),
        embedding_provider=LocalEmbeddingProvider(),
    )
    kb.initialize()
    seed_default_knowledge(kb)

    reg = build_registry(
        scn_store,
        kb_db_path=str(tmp_path / "kb.db"),
        kb_index_path=str(tmp_path / "kb.faiss"),
        ctx_db_path=str(tmp_path / "ctx.db"),
    )

    # 1. Discovery
    baseline_id = reg["finance.simulate.load_baseline"].handler(
        {"model": "gestnova", "preset": "gestnova"}
    )["scenario_id"]

    # 2. Use knowledge base to inform decision
    kb_results = reg["finance.knowledge.search"].handler({
        "query": "qué es un LTV CAC saludable", "top_k": 3,
    })
    assert any("LTV" in r["title"] or "CAC" in r["title"] for r in kb_results["results"])

    # 3. Run a workflow (valuation_summary)
    val_out = reg["finance.workflows.run"].handler({
        "workflow_id": "valuation_summary",
        "inputs": {"scenario_id": baseline_id},
    })
    assert "enterprise_value" in val_out
    assert val_out["enterprise_value"] > 0

    # 4. Run pricing impact workflow (multi-step with foreach)
    pricing_out = reg["finance.workflows.run"].handler({
        "workflow_id": "pricing_impact_analysis",
        "inputs": {"base_scenario_id": baseline_id, "prices": [200, 300, 400]},
    })
    assert "variants" in pricing_out
    assert len(pricing_out["variants"]) == 3

    # 5. Store decision in context memory
    reg["finance.context.store"].handler({
        "user_id": "gestnova",
        "key": "decision-pricing-2026-05",
        "value": "Decidimos mantener pricing 300€/agente tras analizar 200/300/400. EV óptimo en 300.",
        "tags": ["pricing", "decision"],
    })

    # 6. Recall context later
    recall = reg["finance.context.search"].handler({
        "user_id": "gestnova",
        "query": "qué decidimos sobre el precio",
        "top_k": 3,
    })
    assert len(recall["results"]) >= 1
    assert "300" in recall["results"][0]["value"]

    # 7. Multi-tenant isolation
    reg["finance.context.store"].handler({
        "user_id": "otra_empresa",
        "key": "secreto",
        "value": "Información privada de otra empresa",
    })
    leaked = reg["finance.context.search"].handler({
        "user_id": "gestnova",
        "query": "información privada",
        "top_k": 5,
    })
    assert all("otra empresa" not in r["value"] for r in leaked["results"])
