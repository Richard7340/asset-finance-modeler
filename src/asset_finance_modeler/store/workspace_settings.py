"""Workspace settings store — privacy and tier configuration per workspace."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass
class WorkspaceSettings:
    workspace_id: str
    meta_learning_opt_out: bool = False  # Default: opted-in (privacy by default)
    tier: str = "free"  # free, personal, business, enterprise
    settings_json: str = "{}"

    @property
    def meta_learning_enabled(self) -> bool:
        if self.tier == "enterprise":
            return True  # Enterprise: opt-in, always available
        return not self.meta_learning_opt_out


class WorkspaceSettingsStore:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._ensure_table()

    def _ensure_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS workspace_settings (
                workspace_id TEXT PRIMARY KEY,
                meta_learning_opt_out INTEGER DEFAULT 0,
                tier TEXT DEFAULT 'free',
                settings_json TEXT DEFAULT '{}'
            )
        """)
        self.conn.commit()

    def get(self, workspace_id: str) -> WorkspaceSettings:
        row = self.conn.execute(
            "SELECT workspace_id, meta_learning_opt_out, tier, settings_json "
            "FROM workspace_settings WHERE workspace_id = ?",
            (workspace_id,),
        ).fetchone()
        if not row:
            return WorkspaceSettings(workspace_id=workspace_id)
        return WorkspaceSettings(
            workspace_id=row[0],
            meta_learning_opt_out=bool(row[1]),
            tier=row[2] or "free",
            settings_json=row[3] or "{}",
        )

    def save(self, settings: WorkspaceSettings):
        self.conn.execute(
            """
            INSERT INTO workspace_settings (workspace_id, meta_learning_opt_out, tier, settings_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(workspace_id) DO UPDATE SET
                meta_learning_opt_out = excluded.meta_learning_opt_out,
                tier = excluded.tier,
                settings_json = excluded.settings_json
            """,
            (
                settings.workspace_id,
                int(settings.meta_learning_opt_out),
                settings.tier,
                settings.settings_json,
            ),
        )
        self.conn.commit()

    def set_opt_out(self, workspace_id: str, opt_out: bool):
        settings = self.get(workspace_id)
        settings.meta_learning_opt_out = opt_out
        self.save(settings)

    def set_tier(self, workspace_id: str, tier: str):
        settings = self.get(workspace_id)
        settings.tier = tier
        self.save(settings)
