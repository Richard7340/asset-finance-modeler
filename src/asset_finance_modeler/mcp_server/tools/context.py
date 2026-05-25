from typing import Any

from asset_finance_modeler.intelligence.context.memory import ContextMemory


def make_context_store(mem: ContextMemory) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        entry_id = mem.store(
            user_id=args["user_id"],
            key=args["key"],
            value=args["value"],
            tags=args.get("tags", []),
            workspace_id=args.get("workspace_id"),
        )
        return {"id": entry_id}
    return _handle


def make_context_search(mem: ContextMemory) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        results = mem.search(
            user_id=args["user_id"],
            query=args["query"],
            top_k=args.get("top_k", 5),
            workspace_id=args.get("workspace_id"),
        )
        return {
            "results": [
                {
                    "id": r.entry.id,
                    "key": r.entry.key,
                    "value": r.entry.value,
                    "tags": r.entry.tags,
                    "user_id": r.entry.user_id,
                    "workspace_id": r.entry.workspace_id,
                    "created_at": r.entry.created_at.isoformat(),
                    "score": r.score,
                }
                for r in results
            ],
        }
    return _handle


def make_context_recent(mem: ContextMemory) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        entries = mem.recent(user_id=args["user_id"], limit=args.get("limit", 10), workspace_id=args.get("workspace_id"))
        return {
            "entries": [
                {
                    "id": e.id,
                    "key": e.key,
                    "value": e.value,
                    "tags": e.tags,
                    "user_id": e.user_id,
                    "workspace_id": e.workspace_id,
                    "created_at": e.created_at.isoformat(),
                }
                for e in entries
            ],
        }
    return _handle
