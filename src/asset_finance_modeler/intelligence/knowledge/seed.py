from importlib.resources import files

import yaml

from .base import KnowledgeBase, KnowledgeEntry


def seed_default_knowledge(kb: KnowledgeBase) -> int:
    """Populate a KnowledgeBase from the bundled seed.yaml. Returns count added."""
    seed_path = files("asset_finance_modeler.intelligence.knowledge.data") / "seed.yaml"
    with seed_path.open() as f:
        entries = yaml.safe_load(f)

    added = 0
    for raw in entries:
        kb.add(KnowledgeEntry(
            title=raw["title"],
            content=raw["content"],
            category=raw.get("category", "general"),
            tags=raw.get("tags", []),
            tenant_id=None,  # global knowledge
        ))
        added += 1
    return added
