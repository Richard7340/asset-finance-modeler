# src/asset_finance_modeler/mcp_server/tools/knowledge_retrieve.py
from __future__ import annotations

from typing import Any


def make_knowledge_retrieve(retriever: Any) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        results = retriever.search(
            query=args["topic"],
            top_k=args.get("top_k", 5),
            asset_type=args.get("asset_type"),
            layer=args.get("layer"),
        )
        return {
            "results": [
                {
                    "id": r.id,
                    "title": r.title,
                    "content": r.content,
                    "category": r.category,
                    "layer": r.layer,
                    "score": r.score,
                }
                for r in results
            ],
        }

    return _handle
