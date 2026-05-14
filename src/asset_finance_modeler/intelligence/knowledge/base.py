from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import faiss  # type: ignore[import-untyped]
import numpy as np

from asset_finance_modeler.intelligence.embeddings import EmbeddingProvider

_SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge_entries (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    category TEXT NOT NULL,
    tags_json TEXT NOT NULL DEFAULT '[]',
    tenant_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    vector_offset INTEGER
);
CREATE INDEX IF NOT EXISTS idx_kb_category ON knowledge_entries(category);
CREATE INDEX IF NOT EXISTS idx_kb_tenant ON knowledge_entries(tenant_id);
"""


@dataclass
class KnowledgeEntry:
    title: str
    content: str
    category: str = "general"
    tags: list[str] = field(default_factory=list)
    tenant_id: str | None = None
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            self.id = f"kn-{uuid.uuid4().hex[:8]}"


@dataclass
class SearchResult:
    entry: KnowledgeEntry
    score: float


class KnowledgeBase:
    def __init__(
        self,
        db_path: str,
        index_path: str,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self.db_path = db_path
        self.index_path = index_path
        self.provider = embedding_provider
        self._index: faiss.IndexFlatIP | None = None
        self._id_map: list[str] = []  # offset → entry id

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(_SCHEMA)
        self._load_index()

    def _load_index(self) -> None:
        index_file = Path(self.index_path)
        if index_file.exists():
            self._index = faiss.read_index(str(index_file))
            with self._conn() as conn:
                rows = conn.execute(
                    "SELECT id FROM knowledge_entries WHERE vector_offset IS NOT NULL ORDER BY vector_offset"
                ).fetchall()
            self._id_map = [r["id"] for r in rows]
        else:
            self._index = faiss.IndexFlatIP(self.provider.dimension)
            self._id_map = []

    def _save_index(self) -> None:
        if self._index is not None:
            Path(self.index_path).parent.mkdir(parents=True, exist_ok=True)
            faiss.write_index(self._index, self.index_path)

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> KnowledgeEntry:
        return KnowledgeEntry(
            id=row["id"],
            title=row["title"],
            content=row["content"],
            category=row["category"],
            tags=json.loads(row["tags_json"]),
            tenant_id=row["tenant_id"],
        )

    def add(self, entry: KnowledgeEntry) -> str:
        # Embed
        text = f"{entry.title}\n{entry.content}"
        vec = self.provider.embed(text).astype(np.float32).reshape(1, -1)
        assert self._index is not None
        offset = self._index.ntotal
        self._index.add(vec)
        self._id_map.append(entry.id)
        self._save_index()

        with self._conn() as conn:
            conn.execute(
                """INSERT INTO knowledge_entries
                   (id, title, content, category, tags_json, tenant_id, vector_offset)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (entry.id, entry.title, entry.content, entry.category,
                 json.dumps(entry.tags), entry.tenant_id, offset),
            )
        return entry.id

    def get(self, entry_id: str) -> KnowledgeEntry | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM knowledge_entries WHERE id = ?", (entry_id,)
            ).fetchone()
        return self._row_to_entry(row) if row else None

    def search(
        self,
        query: str,
        top_k: int = 5,
        category: str | None = None,
        tenant_id: str | None = None,
    ) -> list[SearchResult]:
        assert self._index is not None
        if self._index.ntotal == 0:
            return []
        qvec = self.provider.embed(query).astype(np.float32).reshape(1, -1)
        # Search a wider neighborhood to allow post-filtering
        k_search = min(top_k * 5, self._index.ntotal)
        scores, idxs = self._index.search(qvec, k_search)

        results: list[SearchResult] = []
        for score, idx in zip(scores[0].tolist(), idxs[0].tolist()):
            if idx < 0 or idx >= len(self._id_map):
                continue
            entry = self.get(self._id_map[idx])
            if entry is None:
                continue
            if category is not None and entry.category != category:
                continue
            if tenant_id is not None and entry.tenant_id not in (None, tenant_id):
                continue
            results.append(SearchResult(entry=entry, score=float(score)))
            if len(results) >= top_k:
                break
        return results

    def list_categories(self) -> list[dict[str, object]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT category, COUNT(*) as cnt FROM knowledge_entries GROUP BY category ORDER BY category"
            ).fetchall()
        return [{"name": r["category"], "count": int(r["cnt"])} for r in rows]
