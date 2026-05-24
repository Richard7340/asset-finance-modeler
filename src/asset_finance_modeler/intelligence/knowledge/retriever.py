from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import faiss  # type: ignore[import-untyped]
import numpy as np

from asset_finance_modeler.intelligence.embeddings import LocalEmbeddingProvider

from .loader import KBLoader


@dataclass
class KBSearchResult:
    id: str
    title: str
    content: str
    category: str
    layer: str
    score: float
    metadata: dict[str, Any]


class KBRetriever:
    def __init__(
        self, db_path: str | None = None, index_path: str | None = None
    ) -> None:
        self._provider = LocalEmbeddingProvider()
        self._index: faiss.IndexFlatIP | None = None
        self._entries: list[dict[str, Any]] = []

    def initialize(self) -> None:
        loader = KBLoader()
        self._entries = []

        for concept in loader.load_concepts():
            self._entries.append({
                "id": concept.id,
                "title": concept.title,
                "content": concept.content,
                "category": concept.category,
                "layer": "concept",
                "asset_types": concept.asset_types,
            })

        for bm in loader.load_benchmarks():
            text = (
                f"{bm.field} {bm.asset_type} {bm.region or ''}: "
                f"{bm.value} {bm.unit}. {bm.methodology}"
            )
            self._entries.append({
                "id": f"bm-{bm.field}-{bm.asset_type}-{bm.region or 'global'}",
                "title": f"{bm.field} ({bm.asset_type})",
                "content": text,
                "category": "benchmark",
                "layer": "benchmark",
                "asset_types": [bm.asset_type],
            })

        if not self._entries:
            self._index = faiss.IndexFlatIP(self._provider.dimension)
            return

        texts = [f"{e['title']}\n{e['content']}" for e in self._entries]
        vecs = np.array(
            [self._provider.embed(t) for t in texts], dtype=np.float32
        )
        self._index = faiss.IndexFlatIP(vecs.shape[1])
        self._index.add(vecs)

    def search(
        self,
        query: str,
        top_k: int = 5,
        asset_type: str | None = None,
        layer: str | None = None,
    ) -> list[KBSearchResult]:
        if self._index is None or self._index.ntotal == 0:
            return []

        qvec = self._provider.embed(query).astype(np.float32).reshape(1, -1)
        k = min(top_k * 3, self._index.ntotal)
        scores, idxs = self._index.search(qvec, k)

        results: list[KBSearchResult] = []
        for score, idx in zip(scores[0].tolist(), idxs[0].tolist()):
            if idx < 0 or idx >= len(self._entries):
                continue
            entry = self._entries[idx]

            if asset_type and entry.get("asset_types"):
                if asset_type not in entry["asset_types"] and entry["asset_types"]:
                    continue

            if layer and entry["layer"] != layer:
                continue

            results.append(
                KBSearchResult(
                    id=entry["id"],
                    title=entry["title"],
                    content=entry["content"],
                    category=entry["category"],
                    layer=entry["layer"],
                    score=float(score),
                    metadata={
                        k: v
                        for k, v in entry.items()
                        if k not in ("id", "title", "content", "category", "layer")
                    },
                )
            )
            if len(results) >= top_k:
                break

        return results
