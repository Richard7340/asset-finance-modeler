from typing import Any

from asset_finance_modeler.intelligence.knowledge.base import KnowledgeBase, KnowledgeEntry


def make_knowledge_search(kb: KnowledgeBase) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        results = kb.search(
            query=args["query"],
            top_k=args.get("top_k", 5),
            category=args.get("category"),
            user_id=args.get("user_id"),
            workspace_id=args.get("workspace_id"),
        )
        return {
            "results": [
                {
                    "id": r.entry.id,
                    "title": r.entry.title,
                    "content": r.entry.content,
                    "category": r.entry.category,
                    "tags": r.entry.tags,
                    "user_id": r.entry.user_id,
                    "workspace_id": r.entry.workspace_id,
                    "score": r.score,
                }
                for r in results
            ],
        }
    return _handle


def make_knowledge_add(kb: KnowledgeBase) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        entry_id = kb.add(KnowledgeEntry(
            title=args["title"],
            content=args["content"],
            category=args.get("category", "general"),
            tags=args.get("tags", []),
            user_id=args.get("user_id"),
            workspace_id=args.get("workspace_id"),
        ))
        return {"id": entry_id}
    return _handle


def make_knowledge_list_categories(kb: KnowledgeBase) -> Any:
    def _handle(_args: dict[str, Any]) -> dict[str, Any]:
        return {"categories": kb.list_categories()}
    return _handle
