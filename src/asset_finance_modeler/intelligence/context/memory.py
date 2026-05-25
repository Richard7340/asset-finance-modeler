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
    user_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    tags_json TEXT NOT NULL DEFAULT '[]',
    embedding_blob BLOB,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    workspace_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_ctx_user ON context_entries(user_id);
CREATE INDEX IF NOT EXISTS idx_ctx_user_created ON context_entries(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ctx_user_workspace ON context_entries(user_id, workspace_id);
"""


@dataclass
class ContextEntry:
    user_id: str
    key: str
    value: str
    tags: list[str] = field(default_factory=list)
    id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    workspace_id: str | None = None

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
            # Migration: rename tenant_id -> user_id if upgrading existing DB
            try:
                conn.execute('ALTER TABLE context_entries RENAME COLUMN tenant_id TO user_id')
            except Exception:
                pass
            # Migration: add workspace_id column if it doesn't exist
            try:
                conn.execute('ALTER TABLE context_entries ADD COLUMN workspace_id TEXT')
            except Exception:
                pass

    def store(self, user_id: str, key: str, value: str, tags: list[str] | None = None, workspace_id: str | None = None) -> str:
        entry = ContextEntry(user_id=user_id, key=key, value=value, tags=tags or [], workspace_id=workspace_id)
        vec = self.provider.embed(value).astype(np.float32)
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO context_entries
                   (id, user_id, key, value, tags_json, embedding_blob, created_at, workspace_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (entry.id, entry.user_id, entry.key, entry.value,
                 json.dumps(entry.tags), vec.tobytes(), entry.created_at.isoformat(),
                 entry.workspace_id),
            )
        return entry.id

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> ContextEntry:
        keys = row.keys()
        return ContextEntry(
            id=row["id"],
            user_id=row["user_id"] if "user_id" in keys else "default",
            key=row["key"],
            value=row["value"],
            tags=json.loads(row["tags_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            workspace_id=row["workspace_id"] if "workspace_id" in keys else None,
        )

    def recent(self, user_id: str, limit: int = 10, workspace_id: str | None = None) -> list[ContextEntry]:
        with self._conn() as conn:
            if workspace_id:
                rows = conn.execute(
                    "SELECT * FROM context_entries WHERE user_id = ? AND workspace_id = ? ORDER BY created_at DESC LIMIT ?",
                    (user_id, workspace_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM context_entries WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                    (user_id, limit),
                ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def search(self, user_id: str, query: str, top_k: int = 5, workspace_id: str | None = None) -> list[ContextSearchResult]:
        qvec = self.provider.embed(query).astype(np.float32)
        with self._conn() as conn:
            if workspace_id:
                rows = conn.execute(
                    "SELECT * FROM context_entries WHERE user_id = ? AND workspace_id = ?", (user_id, workspace_id)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM context_entries WHERE user_id = ?", (user_id,)
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
