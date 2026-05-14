from typing import Any

from asset_finance_modeler.intelligence.context.memory import ContextMemory


def make_context_store(mem: ContextMemory) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        entry_id = mem.store(
            tenant_id=args["tenant_id"],
            key=args["key"],
            value=args["value"],
            tags=args.get("tags", []),
        )
        return {"id": entry_id}
    return _handle


def make_context_search(mem: ContextMemory) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        results = mem.search(
            tenant_id=args["tenant_id"],
            query=args["query"],
            top_k=args.get("top_k", 5),
        )
        return {
            "results": [
                {
                    "id": r.entry.id,
                    "key": r.entry.key,
                    "value": r.entry.value,
                    "tags": r.entry.tags,
                    "tenant_id": r.entry.tenant_id,
                    "created_at": r.entry.created_at.isoformat(),
                    "score": r.score,
                }
                for r in results
            ],
        }
    return _handle


def make_context_recent(mem: ContextMemory) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        entries = mem.recent(tenant_id=args["tenant_id"], limit=args.get("limit", 10))
        return {
            "entries": [
                {
                    "id": e.id,
                    "key": e.key,
                    "value": e.value,
                    "tags": e.tags,
                    "tenant_id": e.tenant_id,
                    "created_at": e.created_at.isoformat(),
                }
                for e in entries
            ],
        }
    return _handle
