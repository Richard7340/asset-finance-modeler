"""Time-series of real (actual) operating data for an asset in operation.

Each ``Actual`` is a single observed value for one trackable model line in one
period. They live in the SAME SQLite file as scenarios (see ``web_api.assets``)
so a deployment has one DB. F2 only stores + reads them; the variance endpoint
(``web_api.actuals``) compares them against the frozen base ``results_snapshot``.
"""
from __future__ import annotations

import secrets
import sqlite3
from datetime import UTC, datetime
from typing import Protocol

from pydantic import BaseModel, Field


def new_actual_id() -> str:
    """Generate a unique actual id like 'act-a3f2c1b9' (mirrors new_scenario_id)."""
    return f"act-{secrets.token_hex(4)}"


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


class Actual(BaseModel):
    id: str = Field(default_factory=new_actual_id)
    scenario_id: str
    period_start: str  # ISO date string, e.g. "2026-01-01"
    line_path: str  # trackable line, e.g. "income_statement.rows.revenue"
    value: float
    unit: str = ""
    note: str = ""
    entered_by: str = "default"
    entered_at: str = Field(default_factory=_utcnow_iso)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS asset_actuals (
  id TEXT PRIMARY KEY,
  scenario_id TEXT NOT NULL,
  period_start TEXT NOT NULL,
  line_path TEXT NOT NULL,
  value REAL NOT NULL,
  unit TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT '',
  entered_by TEXT NOT NULL DEFAULT 'default',
  entered_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_actuals_scn ON asset_actuals(scenario_id, line_path, period_start);
"""


class ActualsStore(Protocol):
    def initialize(self) -> None: ...
    def add(self, actual: Actual) -> str: ...
    def add_batch(self, actuals: list[Actual]) -> list[str]: ...
    def list(
        self,
        scenario_id: str,
        line_path: str | None = None,
        since: str | None = None,
        until: str | None = None,
    ) -> list[Actual]: ...
    def delete(self, actual_id: str) -> None: ...


class SQLiteActualsStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    @staticmethod
    def _to_row(a: Actual) -> dict[str, object]:
        return {
            "id": a.id,
            "scenario_id": a.scenario_id,
            "period_start": a.period_start,
            "line_path": a.line_path,
            "value": a.value,
            "unit": a.unit,
            "note": a.note,
            "entered_by": a.entered_by,
            "entered_at": a.entered_at,
        }

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Actual:
        return Actual(
            id=row["id"],
            scenario_id=row["scenario_id"],
            period_start=row["period_start"],
            line_path=row["line_path"],
            value=row["value"],
            unit=row["unit"],
            note=row["note"],
            entered_by=row["entered_by"],
            entered_at=row["entered_at"],
        )

    def add(self, actual: Actual) -> str:
        row = self._to_row(actual)
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO asset_actuals (
                    id, scenario_id, period_start, line_path, value,
                    unit, note, entered_by, entered_at
                ) VALUES (
                    :id, :scenario_id, :period_start, :line_path, :value,
                    :unit, :note, :entered_by, :entered_at
                )
                """,
                row,
            )
        return actual.id

    def add_batch(self, actuals: list[Actual]) -> list[str]:
        ids: list[str] = []
        with self._conn() as conn:
            for a in actuals:
                conn.execute(
                    """
                    INSERT INTO asset_actuals (
                        id, scenario_id, period_start, line_path, value,
                        unit, note, entered_by, entered_at
                    ) VALUES (
                        :id, :scenario_id, :period_start, :line_path, :value,
                        :unit, :note, :entered_by, :entered_at
                    )
                    """,
                    self._to_row(a),
                )
                ids.append(a.id)
        return ids

    def list(
        self,
        scenario_id: str,
        line_path: str | None = None,
        since: str | None = None,
        until: str | None = None,
    ) -> list[Actual]:
        clauses = ["scenario_id = ?"]
        params: list[object] = [scenario_id]
        if line_path is not None:
            clauses.append("line_path = ?")
            params.append(line_path)
        if since is not None:
            clauses.append("period_start >= ?")
            params.append(since)
        if until is not None:
            clauses.append("period_start <= ?")
            params.append(until)
        where = " AND ".join(clauses)
        sql = (
            f"SELECT * FROM asset_actuals WHERE {where} "
            "ORDER BY period_start ASC, entered_at ASC"
        )
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._from_row(r) for r in rows]

    def delete(self, actual_id: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM asset_actuals WHERE id = ?", (actual_id,))
