from __future__ import annotations

import json
import secrets
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


def new_project_id() -> str:
    return f"prj-{secrets.token_hex(4)}"


@dataclass
class Project:
    id: str
    user_id: str
    name: str
    description: str = ""
    asset_type: str | None = None
    region: str | None = None
    tags: list[str] = field(default_factory=list)
    scenario_ids: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    archived: bool = False
    metadata: dict = field(default_factory=dict)
    workspace_id: str | None = None


_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    asset_type TEXT,
    region TEXT,
    tags_json TEXT NOT NULL DEFAULT '[]',
    scenario_ids_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    workspace_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_projects_user ON projects(user_id);
CREATE INDEX IF NOT EXISTS idx_projects_user_archived ON projects(user_id, archived);
CREATE INDEX IF NOT EXISTS idx_projects_user_workspace ON projects(user_id, workspace_id);
"""


class SQLiteProjectStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def initialize(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(_SCHEMA)
            # Migration: rename tenant_id -> user_id if upgrading existing DB
            try:
                conn.execute('ALTER TABLE projects RENAME COLUMN tenant_id TO user_id')
            except Exception:
                pass
            # Migration: add workspace_id column if it doesn't exist
            try:
                conn.execute('ALTER TABLE projects ADD COLUMN workspace_id TEXT')
            except Exception:
                pass

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def save(self, project: Project) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO projects
                   (id, user_id, name, description, asset_type, region,
                    tags_json, scenario_ids_json, created_at, archived, metadata_json, workspace_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    project.id,
                    project.user_id,
                    project.name,
                    project.description,
                    project.asset_type,
                    project.region,
                    json.dumps(project.tags),
                    json.dumps(project.scenario_ids),
                    project.created_at.isoformat(),
                    int(project.archived),
                    json.dumps(project.metadata),
                    project.workspace_id,
                ),
            )

    def get(self, project_id: str) -> Project | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM projects WHERE id = ?", (project_id,)
            ).fetchone()
        return self._row_to_project(row) if row else None

    def list_by_tenant(
        self, user_id: str, include_archived: bool = False, workspace_id: str | None = None
    ) -> list[Project]:
        with self._conn() as conn:
            if workspace_id:
                if include_archived:
                    rows = conn.execute(
                        "SELECT * FROM projects WHERE user_id = ? AND workspace_id = ? ORDER BY created_at DESC",
                        (user_id, workspace_id),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM projects WHERE user_id = ? AND workspace_id = ? AND archived = 0 ORDER BY created_at DESC",
                        (user_id, workspace_id),
                    ).fetchall()
            else:
                if include_archived:
                    rows = conn.execute(
                        "SELECT * FROM projects WHERE user_id = ? ORDER BY created_at DESC",
                        (user_id,),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM projects WHERE user_id = ? AND archived = 0 ORDER BY created_at DESC",
                        (user_id,),
                    ).fetchall()
        return [self._row_to_project(r) for r in rows]

    def archive(self, project_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE projects SET archived = 1 WHERE id = ?", (project_id,)
            )

    def add_scenario(self, project_id: str, scenario_id: str) -> None:
        project = self.get(project_id)
        if project and scenario_id not in project.scenario_ids:
            project.scenario_ids.append(scenario_id)
            self.save(project)

    @staticmethod
    def _row_to_project(row: sqlite3.Row) -> Project:
        keys = row.keys()
        return Project(
            id=row["id"],
            user_id=row["user_id"] if "user_id" in keys else "default",
            name=row["name"],
            description=row["description"],
            asset_type=row["asset_type"],
            region=row["region"],
            tags=json.loads(row["tags_json"]),
            scenario_ids=json.loads(row["scenario_ids_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            archived=bool(row["archived"]),
            metadata=json.loads(row["metadata_json"]),
            workspace_id=row["workspace_id"] if "workspace_id" in keys else None,
        )
