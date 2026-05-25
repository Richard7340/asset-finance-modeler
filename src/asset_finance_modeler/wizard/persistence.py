# src/asset_finance_modeler/wizard/persistence.py
from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from asset_finance_modeler.core.resolved_input import ResolvedInput
from asset_finance_modeler.intelligence.knowledge.schemas import QuestionTemplate

from .session import WizardSession

_SCHEMA = """
CREATE TABLE IF NOT EXISTS wizard_sessions (
    session_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    mode TEXT NOT NULL,
    questions_json TEXT NOT NULL,
    resolved_json TEXT NOT NULL DEFAULT '{}',
    current_idx INTEGER NOT NULL DEFAULT 0,
    history_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wizard_tenant ON wizard_sessions(tenant_id);
"""


class WizardSessionStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(db_path) as conn:
            conn.executescript(_SCHEMA)

    def save(self, session: WizardSession, tenant_id: str = "default") -> None:
        questions_data = [q.model_dump() for q in session.questions]
        resolved_data = {k: v.to_dict() for k, v in session.resolved.items()}
        now = datetime.now(UTC).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO wizard_sessions
                   (session_id, tenant_id, asset_type, mode, questions_json,
                    resolved_json, current_idx, history_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session.session_id,
                    tenant_id,
                    session.asset_type,
                    session.mode,
                    json.dumps(questions_data),
                    json.dumps(resolved_data),
                    session._current_idx,
                    json.dumps(session._history),
                    now,
                    now,
                ),
            )

    def load(self, session_id: str) -> WizardSession | None:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM wizard_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        questions = [
            QuestionTemplate.model_validate(q) for q in json.loads(row["questions_json"])
        ]
        resolved_raw = json.loads(row["resolved_json"])
        resolved = {k: ResolvedInput(**v) for k, v in resolved_raw.items()}
        session = WizardSession(
            session_id=row["session_id"],
            asset_type=row["asset_type"],
            mode=row["mode"],
            questions=questions,
            resolved=resolved,
            _current_idx=row["current_idx"],
            _history=json.loads(row["history_json"]),
        )
        return session

    def delete(self, session_id: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM wizard_sessions WHERE session_id = ?", (session_id,)
            )

    def list_by_tenant(self, tenant_id: str) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT session_id, asset_type, mode, updated_at FROM wizard_sessions "
                "WHERE tenant_id = ? ORDER BY updated_at DESC",
                (tenant_id,),
            ).fetchall()
        return [dict(r) for r in rows]
