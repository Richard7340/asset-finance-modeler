from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from asset_finance_modeler.intelligence.embeddings import EmbeddingProvider

_SCHEMA = """
CREATE TABLE IF NOT EXISTS context_entries (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    tags_json TEXT NOT NULL DEFAULT '[]',
    embedding_blob BLOB,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ctx_tenant ON context_entries(tenant_id);
CREATE INDEX IF NOT EXISTS idx_ctx_tenant_created ON context_entries(tenant_id, created_at DESC);
"""


@dataclass
class ContextEntry:
    tenant_id: str
    key: str
    value: str
    tags: list[str] = field(default_factory=list)
    id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.id:
            self.id = f"ctx-{uuid.uuid4().hex[:8]}"


@dataclass
class ContextSearchResult:
    entry: ContextEntry
    score: float


class ContextMemory:
    def __init__(self, db_path: str, embedding_provider: EmbeddingProvider) -> None:
        self.db_path = db_path
        self.provider = embedding_provider

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    def store(self, tenant_id: str, key: str, value: str, tags: list[str] | None = None) -> str:
        entry = ContextEntry(tenant_id=tenant_id, key=key, value=value, tags=tags or [])
        vec = self.provider.embed(value).astype(np.float32)
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO context_entries
                   (id, tenant_id, key, value, tags_json, embedding_blob, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (entry.id, entry.tenant_id, entry.key, entry.value,
                 json.dumps(entry.tags), vec.tobytes(), entry.created_at.isoformat()),
            )
        return entry.id

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> ContextEntry:
        return ContextEntry(
            id=row["id"],
            tenant_id=row["tenant_id"],
            key=row["key"],
            value=row["value"],
            tags=json.loads(row["tags_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def recent(self, tenant_id: str, limit: int = 10) -> list[ContextEntry]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM context_entries WHERE tenant_id = ? ORDER BY created_at DESC LIMIT ?",
                (tenant_id, limit),
            ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def search(self, tenant_id: str, query: str, top_k: int = 5) -> list[ContextSearchResult]:
        qvec = self.provider.embed(query).astype(np.float32)
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM context_entries WHERE tenant_id = ?", (tenant_id,)
            ).fetchall()
        if not rows:
            return []
        # Compute cosine similarity manually (small N, no need for FAISS here)
        scored: list[ContextSearchResult] = []
        for row in rows:
            stored = np.frombuffer(row["embedding_blob"], dtype=np.float32)
            score = float(np.dot(qvec, stored))  # vectors are already normalized
            scored.append(ContextSearchResult(entry=self._row_to_entry(row), score=score))
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]
