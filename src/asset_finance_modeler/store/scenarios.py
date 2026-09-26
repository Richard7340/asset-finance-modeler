from __future__ import annotations

import builtins
import json
import sqlite3
from datetime import datetime
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Protocol

from asset_finance_modeler.core.scenario import Scenario

# El espacio (tenant) de la llamada en curso. Lo fija la entrada /call con el
# tenant_id que manda la plataforma: asi ninguna herramienta puede olvidarse
# de filtrar (26-sep: list_scenarios devolvia los escenarios de TODOS los
# espacios). Las rutas REST siguen pasando su workspace_id explicito.
_espacio_actual: ContextVar[str | None] = ContextVar("espacio_actual", default=None)


def espacio_actual() -> str | None:
    return _espacio_actual.get()


@contextmanager
def en_espacio(workspace_id: str | None) -> Iterator[None]:
    token = _espacio_actual.set(str(workspace_id) if workspace_id else None)
    try:
        yield
    finally:
        _espacio_actual.reset(token)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scenarios (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    base_model TEXT NOT NULL,
    parent_scenario_id TEXT,
    overrides_json TEXT NOT NULL DEFAULT '{}',
    inputs_snapshot_json TEXT NOT NULL DEFAULT '{}',
    results_snapshot_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    tags_json TEXT NOT NULL DEFAULT '[]',
    notes TEXT NOT NULL DEFAULT '',
    is_canonical INTEGER NOT NULL DEFAULT 0,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    user_id TEXT NOT NULL DEFAULT 'default',
    workspace_id TEXT,
    lifecycle TEXT NOT NULL DEFAULT 'opportunity',
    commissioning_date TEXT,
    base_locked INTEGER NOT NULL DEFAULT 0,
    tracking_frequency TEXT,
    FOREIGN KEY (parent_scenario_id) REFERENCES scenarios(id)
);
CREATE INDEX IF NOT EXISTS idx_parent ON scenarios(parent_scenario_id);
CREATE INDEX IF NOT EXISTS idx_base_model ON scenarios(base_model);
CREATE INDEX IF NOT EXISTS idx_user ON scenarios(user_id);
CREATE INDEX IF NOT EXISTS idx_user_workspace ON scenarios(user_id, workspace_id);
"""


class ScenarioStore(Protocol):
    def initialize(self) -> None: ...
    def save(self, scenario: Scenario) -> None: ...
    def get(self, scenario_id: str, workspace_id: str | None = None) -> Scenario | None: ...
    def list(
        self,
        base_model: str | None = None,
        include_deleted: bool = False,
        user_id: str | None = None,
        workspace_id: str | None = None,
        lifecycle: str | None = None,
    ) -> list[Scenario]: ...
    def delete(self, scenario_id: str, workspace_id: str | None = None) -> None: ...
    def force_delete(self, scenario_id: str, workspace_id: str | None = None) -> None: ...
    def set_canonical(self, scenario_id: str, name: str | None = None) -> None: ...


class SQLiteScenarioStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def initialize(self) -> None:
        with self._conn() as conn:
            conn.executescript(_SCHEMA)
            # Migration: rename tenant_id -> user_id if upgrading existing DB
            try:
                conn.execute('ALTER TABLE scenarios RENAME COLUMN tenant_id TO user_id')
            except Exception:
                pass
            # Migration: add workspace_id column if it doesn't exist
            try:
                conn.execute('ALTER TABLE scenarios ADD COLUMN workspace_id TEXT')
            except Exception:
                pass
            # Migration: backfill legacy rows. Before tenant isolation, assets
            # saved via the REST layer carried workspace_id=NULL (the Scenario
            # default). The REST layer now scopes every list/get to a workspace
            # and uses 'default' for header-less (direct/dev/MCP) flows, so a
            # WHERE workspace_id='default' query would NOT match those NULL rows
            # and they'd silently disappear. Backfill NULL -> 'default' so legacy
            # data stays visible under the default tenant. Idempotent.
            try:
                conn.execute(
                    "UPDATE scenarios SET workspace_id = 'default' WHERE workspace_id IS NULL"
                )
            except Exception:
                pass
            # Migration: add lifecycle columns if upgrading an existing DB
            for ddl in (
                "ALTER TABLE scenarios ADD COLUMN lifecycle TEXT NOT NULL DEFAULT 'opportunity'",
                "ALTER TABLE scenarios ADD COLUMN commissioning_date TEXT",
                "ALTER TABLE scenarios ADD COLUMN base_locked INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE scenarios ADD COLUMN tracking_frequency TEXT",
            ):
                try:
                    conn.execute(ddl)
                except Exception:
                    pass

    @staticmethod
    def _to_row(s: Scenario) -> dict[str, object]:
        return {
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "base_model": s.base_model,
            "parent_scenario_id": s.parent_scenario_id,
            "overrides_json": json.dumps(s.overrides),
            "inputs_snapshot_json": json.dumps(s.inputs_snapshot, default=str),
            "results_snapshot_json": json.dumps(s.results_snapshot, default=str),
            "created_at": s.created_at.isoformat(),
            "tags_json": json.dumps(s.tags),
            "notes": s.notes,
            "is_canonical": int(s.is_canonical),
            "is_deleted": int(s.is_deleted),
            "user_id": s.user_id,
            "workspace_id": s.workspace_id,
            "lifecycle": s.lifecycle,
            "commissioning_date": s.commissioning_date.isoformat() if s.commissioning_date else None,
            "base_locked": int(s.base_locked),
            "tracking_frequency": s.tracking_frequency,
        }

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Scenario:
        keys = row.keys()
        return Scenario(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            base_model=row["base_model"],
            parent_scenario_id=row["parent_scenario_id"],
            overrides=json.loads(row["overrides_json"]),
            inputs_snapshot=json.loads(row["inputs_snapshot_json"]),
            results_snapshot=json.loads(row["results_snapshot_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            tags=json.loads(row["tags_json"]),
            notes=row["notes"],
            is_canonical=bool(row["is_canonical"]),
            is_deleted=bool(row["is_deleted"]),
            user_id=row["user_id"] if "user_id" in keys else "default",
            workspace_id=row["workspace_id"] if "workspace_id" in keys else None,
            lifecycle=row["lifecycle"] if "lifecycle" in keys else "opportunity",
            commissioning_date=(
                datetime.fromisoformat(row["commissioning_date"])
                if "commissioning_date" in keys and row["commissioning_date"]
                else None
            ),
            base_locked=bool(row["base_locked"]) if "base_locked" in keys else False,
            tracking_frequency=(
                row["tracking_frequency"] if "tracking_frequency" in keys else None
            ),
        )

    def save(self, scenario: Scenario) -> None:
        ws = espacio_actual()
        if ws and not scenario.workspace_id:
            scenario = scenario.model_copy(update={"workspace_id": ws})
        row = self._to_row(scenario)
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO scenarios (
                    id, name, description, base_model, parent_scenario_id,
                    overrides_json, inputs_snapshot_json, results_snapshot_json,
                    created_at, tags_json, notes, is_canonical, is_deleted, user_id, workspace_id,
                    lifecycle, commissioning_date, base_locked, tracking_frequency
                ) VALUES (
                    :id, :name, :description, :base_model, :parent_scenario_id,
                    :overrides_json, :inputs_snapshot_json, :results_snapshot_json,
                    :created_at, :tags_json, :notes, :is_canonical, :is_deleted, :user_id, :workspace_id,
                    :lifecycle, :commissioning_date, :base_locked, :tracking_frequency
                )
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description,
                    overrides_json = excluded.overrides_json,
                    inputs_snapshot_json = excluded.inputs_snapshot_json,
                    results_snapshot_json = excluded.results_snapshot_json,
                    tags_json = excluded.tags_json,
                    notes = excluded.notes,
                    is_canonical = excluded.is_canonical,
                    is_deleted = excluded.is_deleted,
                    user_id = excluded.user_id,
                    workspace_id = excluded.workspace_id,
                    lifecycle = excluded.lifecycle,
                    commissioning_date = excluded.commissioning_date,
                    base_locked = excluded.base_locked,
                    tracking_frequency = excluded.tracking_frequency
                """,
                row,
            )

    def get(self, scenario_id: str, workspace_id: str | None = None) -> Scenario | None:
        """Fetch a scenario by id. When ``workspace_id`` is given, the row is
        only returned if it belongs to that workspace — so a tenant can never
        read another tenant's asset by guessing its id. When ``workspace_id`` is
        ``None`` (admin/internal/cross-tenant tooling) the scoping is skipped."""
        if workspace_id is None:
            workspace_id = espacio_actual()
        with self._conn() as conn:
            if workspace_id is not None:
                row = conn.execute(
                    "SELECT * FROM scenarios WHERE id = ? AND workspace_id = ?",
                    (scenario_id, workspace_id),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM scenarios WHERE id = ?", (scenario_id,)
                ).fetchone()
        if row is None:
            return None
        return self._from_row(row)

    def list(
        self,
        base_model: str | None = None,
        include_deleted: bool = False,
        user_id: str | None = None,
        workspace_id: str | None = None,
        lifecycle: str | None = None,
    ) -> list[Scenario]:
        if workspace_id is None:
            workspace_id = espacio_actual()
        clauses = []
        params: list[object] = []
        if base_model is not None:
            clauses.append("base_model = ?")
            params.append(base_model)
        if not include_deleted:
            clauses.append("is_deleted = 0")
        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(user_id)
        if workspace_id is not None:
            clauses.append("workspace_id = ?")
            params.append(workspace_id)
        if lifecycle is not None:
            clauses.append("lifecycle = ?")
            params.append(lifecycle)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM scenarios {where} ORDER BY created_at DESC"
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._from_row(r) for r in rows]

    def delete(self, scenario_id: str, workspace_id: str | None = None) -> None:
        # workspace-scoped lookup: a tenant can only delete its own row.
        existing = self.get(scenario_id, workspace_id=workspace_id)
        if existing is None:
            return
        if existing.is_canonical:
            raise PermissionError(f"Cannot delete canonical scenario {scenario_id}")
        with self._conn() as conn:
            conn.execute("UPDATE scenarios SET is_deleted = 1 WHERE id = ?", (scenario_id,))

    def force_delete(self, scenario_id: str, workspace_id: str | None = None) -> None:
        """Soft-delete a scenario unconditionally, clearing the canonical flag
        first so a user can delete their own operational/canonical asset. The
        canonical-protection in ``delete`` is kept for the scenario-versioning
        use case; this is the explicit user-driven asset-deletion path.

        When ``workspace_id`` is given the delete is scoped to that workspace, so
        a tenant can never delete another tenant's asset (the lookup returns
        ``None`` and the call is a no-op)."""
        existing = self.get(scenario_id, workspace_id=workspace_id)
        if existing is None:
            return
        with self._conn() as conn:
            conn.execute(
                "UPDATE scenarios SET is_canonical = 0, is_deleted = 1 WHERE id = ?",
                (scenario_id,),
            )

    def set_canonical(self, scenario_id: str, name: str | None = None) -> None:
        with self._conn() as conn:
            if name is not None:
                conn.execute(
                    "UPDATE scenarios SET is_canonical = 1, name = ? WHERE id = ?",
                    (name, scenario_id),
                )
            else:
                conn.execute(
                    "UPDATE scenarios SET is_canonical = 1 WHERE id = ?", (scenario_id,)
                )

    def get_ancestors(self, scenario_id: str) -> builtins.list[Scenario]:
        """Return ancestors in order: immediate parent first, then grandparent, etc."""
        ancestors: builtins.list[Scenario] = []
        current = self.get(scenario_id)
        if current is None:
            return []
        while current.parent_scenario_id is not None:
            parent = self.get(current.parent_scenario_id)
            if parent is None:
                break
            ancestors.append(parent)
            current = parent
        return ancestors

    def get_descendants(self, scenario_id: str) -> builtins.list[Scenario]:
        """Return all non-deleted descendants (BFS)."""
        out: builtins.list[Scenario] = []
        queue = [scenario_id]
        seen: set[str] = set()
        while queue:
            current_id = queue.pop(0)
            if current_id in seen:
                continue
            seen.add(current_id)
            with self._conn() as conn:
                rows = conn.execute(
                    "SELECT * FROM scenarios WHERE parent_scenario_id = ? AND is_deleted = 0",
                    (current_id,),
                ).fetchall()
            for row in rows:
                child = self._from_row(row)
                out.append(child)
                queue.append(child.id)
        return out
