# Plan 2 — Scenarios + Store + Exports + CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** On top of Plan 1's engine, add (1) the Scenario model with JSONPath overrides, (2) SQLite persistence with genealogy tree, (3) scenario comparison, (4) all output formats (JSON/CSV/XLSX/Markdown), and (5) a thin CLI to exercise the system end-to-end. After Plan 2, you can load a baseline, branch into N alternative scenarios, persist them, compare them, and export results — all without MCP.

**Architecture:**
- `core/scenario.py` — `Scenario` pydantic class + `apply_overrides()` (JSONPath via jsonpath_ng) + `run_scenario()` that resolves a Scenario over its base preset and runs `SaasModel`.
- `store/scenarios.py` — abstract `ScenarioStore` protocol + `SQLiteScenarioStore` implementation with full CRUD + genealogy traversal + compare.
- `store/exports.py` — `to_summary`, `to_csv`, `to_json`, `to_xlsx`, `to_markdown_table`, `to_markdown_report`. Pure data → file/string. UI rendering is the consumer's job.
- `cli/main.py` — thin Click-free argparse CLI: `python -m asset_finance_modeler load gestnova`, `... create-scenario`, `... run`, `... compare`, `... export`.

**Tech Stack:** Same as Plan 1 + `jsonpath-ng` (already in deps) + `openpyxl` (already in deps) + Python stdlib `sqlite3` + `argparse`.

**Spec reference:** `docs/superpowers/specs/2026-05-14-asset-finance-modeler-design.md`

**Prerequisites:** Plan 1 merged (commit `382d414` or later). 83 tests passing, library functional.

---

### Task 1: Scenario dataclass + JSONPath override application

**Files:**
- Create: `src/asset_finance_modeler/core/scenario.py`
- Create: `tests/unit/test_scenario.py`

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_scenario.py`:
```python
from datetime import datetime

import pytest

from asset_finance_modeler.core.scenario import Scenario, apply_overrides, new_scenario_id


def test_new_scenario_id_format():
    sid = new_scenario_id()
    assert sid.startswith("scn-")
    assert len(sid) > 10


def test_new_scenario_id_unique():
    ids = {new_scenario_id() for _ in range(50)}
    assert len(ids) == 50


def test_apply_overrides_scalar():
    base = {"revenue": {"price": 300}}
    result = apply_overrides(base, {"revenue.price": 250})
    assert result["revenue"]["price"] == 250
    # base must not be mutated
    assert base["revenue"]["price"] == 300


def test_apply_overrides_array_index():
    base = {"revenue": {"sources": [{"name": "subs", "price": 300}]}}
    result = apply_overrides(base, {"revenue.sources[0].price": 250})
    assert result["revenue"]["sources"][0]["price"] == 250


def test_apply_overrides_multiple_paths():
    base = {"a": {"b": 1}, "c": {"d": 2}}
    result = apply_overrides(base, {"a.b": 10, "c.d": 20})
    assert result["a"]["b"] == 10
    assert result["c"]["d"] == 20


def test_apply_overrides_invalid_path_raises():
    base = {"a": 1}
    with pytest.raises(KeyError):
        apply_overrides(base, {"nonexistent.path": 5})


def test_scenario_minimal_construction():
    s = Scenario(
        id="scn-abc",
        name="test",
        base_model="gestnova",
        overrides={},
    )
    assert s.parent_scenario_id is None
    assert s.tags == []
    assert s.is_canonical is False
    assert s.notes == ""


def test_scenario_with_snapshots():
    s = Scenario(
        id="scn-abc",
        name="pricing-250",
        base_model="gestnova",
        parent_scenario_id="scn-baseline",
        overrides={"revenue.sources[0].pricing.per_unit_per_period": 250},
        inputs_snapshot={"resolved": True},
        results_snapshot={"revenue_y1": 196000},
        created_at=datetime(2026, 5, 14, 22, 0, 0),
        tags=["pricing", "downside"],
        notes="Lower price test",
    )
    assert s.overrides["revenue.sources[0].pricing.per_unit_per_period"] == 250
    assert "pricing" in s.tags
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
cd "/Users/rikyizquierdo/Documents/New project/asset-finance-modeler"
source .venv/bin/activate
pytest tests/unit/test_scenario.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement Scenario + apply_overrides**

`src/asset_finance_modeler/core/scenario.py`:
```python
import copy
import secrets
from datetime import datetime, timezone
from typing import Any

from jsonpath_ng.ext import parse as jsonpath_parse
from pydantic import BaseModel, Field


def new_scenario_id() -> str:
    """Generate a unique scenario id like 'scn-a3f2c1b9'."""
    return f"scn-{secrets.token_hex(4)}"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Scenario(BaseModel):
    id: str
    name: str
    description: str = ""
    base_model: str = Field(description="Preset key, e.g. 'gestnova'")
    parent_scenario_id: str | None = None
    overrides: dict[str, Any] = Field(default_factory=dict)
    inputs_snapshot: dict[str, Any] = Field(default_factory=dict)
    results_snapshot: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)
    tags: list[str] = Field(default_factory=list)
    notes: str = ""
    is_canonical: bool = False
    is_deleted: bool = False


def _set_by_path(d: dict[str, Any], path: str, value: Any) -> None:
    """Set d[path] = value where path uses dotted+[index] syntax.
    Raises KeyError if any intermediate key does not exist."""
    expr = jsonpath_parse(path)
    matches = expr.find(d)
    if not matches:
        raise KeyError(f"Override path not found: {path!r}")
    expr.update(d, value)


def apply_overrides(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Return a deep-copied base with overrides applied. base is not mutated."""
    result = copy.deepcopy(base)
    for path, value in overrides.items():
        _set_by_path(result, path, value)
    return result
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
pytest tests/unit/test_scenario.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add src/asset_finance_modeler/core/scenario.py tests/unit/test_scenario.py
git commit -m "feat(core): Scenario dataclass + JSONPath override application"
```

---

### Task 2: run_scenario helper (apply overrides + execute SaasModel)

**Files:**
- Modify: `src/asset_finance_modeler/core/scenario.py`
- Create: `tests/unit/test_run_scenario.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_run_scenario.py`:
```python
from asset_finance_modeler.core.scenario import Scenario, new_scenario_id, run_scenario_saas


def test_run_scenario_baseline_no_overrides():
    s = Scenario(id=new_scenario_id(), name="baseline", base_model="gestnova", overrides={})
    results = run_scenario_saas(s)
    assert results.summary["revenue_y1"] > 0
    # Snapshot fields populated
    assert "revenue" in results.pnl


def test_run_scenario_with_override_changes_revenue():
    base = Scenario(id=new_scenario_id(), name="baseline", base_model="gestnova", overrides={})
    base_results = run_scenario_saas(base)

    cheaper = Scenario(
        id=new_scenario_id(),
        name="pricing-200",
        base_model="gestnova",
        overrides={"revenue.sources[0].pricing.per_unit_per_period": 200},
    )
    cheap_results = run_scenario_saas(cheaper)

    # Lower price → lower revenue
    assert cheap_results.summary["revenue_end_period"] < base_results.summary["revenue_end_period"]


def test_run_scenario_changes_horizon():
    s = Scenario(
        id=new_scenario_id(),
        name="short-horizon",
        base_model="gestnova",
        overrides={"meta.horizon.periods": 12},
    )
    results = run_scenario_saas(s)
    assert len(results.pnl["revenue"]) == 12
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
pytest tests/unit/test_run_scenario.py -v
```

Expected: ImportError on `run_scenario_saas`.

- [ ] **Step 3: Append to scenario.py**

```python
from asset_finance_modeler.assets.saas.loader import load_preset
from asset_finance_modeler.assets.saas.model import ModelResults, SaasModel
from asset_finance_modeler.assets.saas.schema import SaasModelConfig


def run_scenario_saas(scenario: Scenario) -> ModelResults:
    """Resolve a Scenario for the SaaS asset type: load preset, apply overrides, run."""
    base_cfg = load_preset(scenario.base_model)
    base_dict = base_cfg.model_dump(mode="json")
    resolved_dict = apply_overrides(base_dict, scenario.overrides)
    resolved_cfg = SaasModelConfig.model_validate(resolved_dict)
    return SaasModel(resolved_cfg).run()
```

- [ ] **Step 4: Run tests, verify pass**

```bash
pytest tests/unit/test_run_scenario.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/asset_finance_modeler/core/scenario.py tests/unit/test_run_scenario.py
git commit -m "feat(core): run_scenario_saas — apply overrides over preset and execute model"
```

---

### Task 3: ScenarioStore abstract + SQLite implementation (CRUD)

**Files:**
- Create: `src/asset_finance_modeler/store/__init__.py`
- Create: `src/asset_finance_modeler/store/scenarios.py`
- Create: `tests/unit/test_scenario_store.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_scenario_store.py`:
```python
import pytest

from asset_finance_modeler.core.scenario import Scenario, new_scenario_id
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore


@pytest.fixture
def store(tmp_path):
    db_path = tmp_path / "scenarios.db"
    s = SQLiteScenarioStore(str(db_path))
    s.initialize()
    return s


def test_save_and_get(store):
    s = Scenario(id=new_scenario_id(), name="baseline", base_model="gestnova")
    store.save(s)
    fetched = store.get(s.id)
    assert fetched is not None
    assert fetched.id == s.id
    assert fetched.name == "baseline"


def test_get_missing_returns_none(store):
    assert store.get("nonexistent") is None


def test_list_filters_by_base_model(store):
    s1 = Scenario(id=new_scenario_id(), name="a", base_model="gestnova")
    s2 = Scenario(id=new_scenario_id(), name="b", base_model="other")
    store.save(s1)
    store.save(s2)
    only_gn = store.list(base_model="gestnova")
    assert len(only_gn) == 1
    assert only_gn[0].name == "a"


def test_list_excludes_deleted_by_default(store):
    s = Scenario(id=new_scenario_id(), name="x", base_model="gestnova")
    store.save(s)
    store.delete(s.id)
    assert store.list() == []
    assert len(store.list(include_deleted=True)) == 1


def test_delete_protected_raises(store):
    s = Scenario(id=new_scenario_id(), name="canon", base_model="gestnova", is_canonical=True)
    store.save(s)
    with pytest.raises(PermissionError):
        store.delete(s.id)


def test_set_canonical(store):
    s = Scenario(id=new_scenario_id(), name="b", base_model="gestnova")
    store.save(s)
    store.set_canonical(s.id, name="gestnova-baseline")
    fetched = store.get(s.id)
    assert fetched.is_canonical is True
    assert fetched.name == "gestnova-baseline"


def test_update_existing(store):
    s = Scenario(id=new_scenario_id(), name="initial", base_model="gestnova")
    store.save(s)
    s.notes = "updated note"
    store.save(s)  # save = upsert
    assert store.get(s.id).notes == "updated note"
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
pytest tests/unit/test_scenario_store.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement store**

`src/asset_finance_modeler/store/__init__.py`: empty file.

`src/asset_finance_modeler/store/scenarios.py`:
```python
import json
import sqlite3
from typing import Protocol

from asset_finance_modeler.core.scenario import Scenario

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
    FOREIGN KEY (parent_scenario_id) REFERENCES scenarios(id)
);
CREATE INDEX IF NOT EXISTS idx_parent ON scenarios(parent_scenario_id);
CREATE INDEX IF NOT EXISTS idx_base_model ON scenarios(base_model);
"""


class ScenarioStore(Protocol):
    def initialize(self) -> None: ...
    def save(self, scenario: Scenario) -> None: ...
    def get(self, scenario_id: str) -> Scenario | None: ...
    def list(self, base_model: str | None = None, include_deleted: bool = False) -> list[Scenario]: ...
    def delete(self, scenario_id: str) -> None: ...
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
        }

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Scenario:
        from datetime import datetime
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
        )

    def save(self, scenario: Scenario) -> None:
        row = self._to_row(scenario)
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO scenarios (
                    id, name, description, base_model, parent_scenario_id,
                    overrides_json, inputs_snapshot_json, results_snapshot_json,
                    created_at, tags_json, notes, is_canonical, is_deleted
                ) VALUES (
                    :id, :name, :description, :base_model, :parent_scenario_id,
                    :overrides_json, :inputs_snapshot_json, :results_snapshot_json,
                    :created_at, :tags_json, :notes, :is_canonical, :is_deleted
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
                    is_deleted = excluded.is_deleted
                """,
                row,
            )

    def get(self, scenario_id: str) -> Scenario | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM scenarios WHERE id = ?", (scenario_id,)).fetchone()
        if row is None:
            return None
        return self._from_row(row)

    def list(
        self, base_model: str | None = None, include_deleted: bool = False
    ) -> list[Scenario]:
        clauses = []
        params: list[object] = []
        if base_model is not None:
            clauses.append("base_model = ?")
            params.append(base_model)
        if not include_deleted:
            clauses.append("is_deleted = 0")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM scenarios {where} ORDER BY created_at DESC"
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._from_row(r) for r in rows]

    def delete(self, scenario_id: str) -> None:
        existing = self.get(scenario_id)
        if existing is None:
            return
        if existing.is_canonical:
            raise PermissionError(f"Cannot delete canonical scenario {scenario_id}")
        with self._conn() as conn:
            conn.execute("UPDATE scenarios SET is_deleted = 1 WHERE id = ?", (scenario_id,))

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
```

- [ ] **Step 4: Run tests, verify pass**

```bash
pytest tests/unit/test_scenario_store.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/asset_finance_modeler/store/__init__.py src/asset_finance_modeler/store/scenarios.py tests/unit/test_scenario_store.py
git commit -m "feat(store): SQLiteScenarioStore with full CRUD + canonical protection"
```

---

### Task 4: Genealogy tree traversal

**Files:**
- Modify: `src/asset_finance_modeler/store/scenarios.py`
- Create: `tests/unit/test_scenario_genealogy.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_scenario_genealogy.py`:
```python
import pytest

from asset_finance_modeler.core.scenario import Scenario, new_scenario_id
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore


@pytest.fixture
def store(tmp_path):
    s = SQLiteScenarioStore(str(tmp_path / "scenarios.db"))
    s.initialize()
    return s


def _build_tree(store):
    """Build: root → child_a → grandchild ; root → child_b"""
    root = Scenario(id=new_scenario_id(), name="root", base_model="gestnova")
    child_a = Scenario(
        id=new_scenario_id(), name="child_a", base_model="gestnova",
        parent_scenario_id=root.id,
    )
    child_b = Scenario(
        id=new_scenario_id(), name="child_b", base_model="gestnova",
        parent_scenario_id=root.id,
    )
    grandchild = Scenario(
        id=new_scenario_id(), name="grandchild", base_model="gestnova",
        parent_scenario_id=child_a.id,
    )
    for s in (root, child_a, child_b, grandchild):
        store.save(s)
    return root, child_a, child_b, grandchild


def test_get_ancestors_of_grandchild(store):
    root, child_a, _, grandchild = _build_tree(store)
    ancestors = store.get_ancestors(grandchild.id)
    assert [a.id for a in ancestors] == [child_a.id, root.id]


def test_get_descendants_of_root(store):
    root, child_a, child_b, grandchild = _build_tree(store)
    descendants = store.get_descendants(root.id)
    ids = {d.id for d in descendants}
    assert ids == {child_a.id, child_b.id, grandchild.id}


def test_get_ancestors_of_root_is_empty(store):
    root, _, _, _ = _build_tree(store)
    assert store.get_ancestors(root.id) == []


def test_get_descendants_excludes_deleted(store):
    root, child_a, _, _ = _build_tree(store)
    store.delete(child_a.id)
    descendants = store.get_descendants(root.id)
    # child_a is deleted → its descendants stay reachable via deleted intermediate? Decision: skip subtree of deleted.
    # We expect: only child_b reachable from root.
    assert all(d.name in {"child_b"} for d in descendants)
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
pytest tests/unit/test_scenario_genealogy.py -v
```

Expected: AttributeError on `get_ancestors`/`get_descendants`.

- [ ] **Step 3: Append to `SQLiteScenarioStore` class**

Add inside `SQLiteScenarioStore`:
```python
    def get_ancestors(self, scenario_id: str) -> list[Scenario]:
        """Return ancestors in order: immediate parent first, then grandparent, etc."""
        ancestors: list[Scenario] = []
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

    def get_descendants(self, scenario_id: str) -> list[Scenario]:
        """Return all non-deleted descendants (BFS)."""
        out: list[Scenario] = []
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
```

- [ ] **Step 4: Run tests, verify pass**

```bash
pytest tests/unit/test_scenario_genealogy.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/asset_finance_modeler/store/scenarios.py tests/unit/test_scenario_genealogy.py
git commit -m "feat(store): genealogy traversal (get_ancestors, get_descendants)"
```

---

### Task 5: compare_scenarios

**Files:**
- Create: `src/asset_finance_modeler/store/compare.py`
- Create: `tests/unit/test_compare.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_compare.py`:
```python
import pytest

from asset_finance_modeler.core.scenario import Scenario, new_scenario_id, run_scenario_saas
from asset_finance_modeler.store.compare import compare_scenarios


def _persisted_results(scenario: Scenario) -> Scenario:
    """Run and stash summary into results_snapshot."""
    results = run_scenario_saas(scenario)
    scenario.results_snapshot = {"summary": dict(results.summary)}
    return scenario


def test_compare_two_scenarios_returns_delta_table():
    base = _persisted_results(Scenario(
        id=new_scenario_id(), name="baseline", base_model="gestnova", overrides={},
    ))
    cheaper = _persisted_results(Scenario(
        id=new_scenario_id(), name="pricing-200", base_model="gestnova",
        overrides={"revenue.sources[0].pricing.per_unit_per_period": 200},
    ))
    table = compare_scenarios([base, cheaper])

    assert table["scenarios"] == ["baseline", "pricing-200"]
    assert "revenue_y1" in table["metrics"]
    # Cheaper price → lower revenue
    base_rev = table["metrics"]["revenue_y1"][0]
    cheap_rev = table["metrics"]["revenue_y1"][1]
    assert cheap_rev < base_rev


def test_compare_with_metric_filter():
    a = _persisted_results(Scenario(
        id=new_scenario_id(), name="a", base_model="gestnova", overrides={},
    ))
    table = compare_scenarios([a], metrics=["revenue_y1", "cash_end"])
    assert set(table["metrics"].keys()) == {"revenue_y1", "cash_end"}


def test_compare_missing_results_raises():
    s = Scenario(id=new_scenario_id(), name="x", base_model="gestnova", overrides={})
    with pytest.raises(ValueError, match="results_snapshot"):
        compare_scenarios([s])
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
pytest tests/unit/test_compare.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement compare**

`src/asset_finance_modeler/store/compare.py`:
```python
from asset_finance_modeler.core.scenario import Scenario

_DEFAULT_METRICS = [
    "revenue_y1",
    "revenue_end_period",
    "ebitda_margin_end",
    "active_customers_end",
    "cash_end",
    "runway_months",
    "ltv_cac_end",
    "enterprise_value",
]


def compare_scenarios(
    scenarios: list[Scenario],
    metrics: list[str] | None = None,
) -> dict[str, object]:
    """Return a comparison table.

    Output shape:
        {
            "scenarios": [name1, name2, ...],
            "metrics": {
                "revenue_y1": [val1, val2, ...],
                ...
            }
        }
    Each scenario must have a populated results_snapshot["summary"].
    """
    if not scenarios:
        return {"scenarios": [], "metrics": {}}

    selected = metrics if metrics is not None else _DEFAULT_METRICS
    names: list[str] = []
    metric_rows: dict[str, list[float | int | None]] = {m: [] for m in selected}

    for s in scenarios:
        summary = s.results_snapshot.get("summary")
        if not summary:
            raise ValueError(
                f"Scenario {s.id} ({s.name}) has no results_snapshot.summary — run it first"
            )
        names.append(s.name)
        for m in selected:
            metric_rows[m].append(summary.get(m))

    return {"scenarios": names, "metrics": metric_rows}
```

- [ ] **Step 4: Run tests, verify pass**

```bash
pytest tests/unit/test_compare.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/asset_finance_modeler/store/compare.py tests/unit/test_compare.py
git commit -m "feat(store): compare_scenarios delta table over default + custom metrics"
```

---

### Task 6: Summary + markdown exports

**Files:**
- Create: `src/asset_finance_modeler/store/exports.py`
- Create: `tests/unit/test_exports_markdown.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_exports_markdown.py`:
```python
import pytest

from asset_finance_modeler.assets.saas.loader import load_preset
from asset_finance_modeler.assets.saas.model import SaasModel
from asset_finance_modeler.store.exports import (
    to_markdown_report,
    to_markdown_table,
    to_summary,
)


@pytest.fixture(scope="module")
def results():
    cfg = load_preset("gestnova")
    return SaasModel(cfg).run()


def test_to_summary(results):
    summary = to_summary(results)
    assert "revenue_y1" in summary
    assert "enterprise_value" in summary
    assert isinstance(summary["revenue_y1"], (int, float))


def test_to_markdown_table_pnl(results):
    md = to_markdown_table(results, view="pnl", max_periods=6)
    assert "| period |" in md.lower() or "| Period |" in md
    assert "revenue" in md.lower()
    # Should contain at most 6 data rows
    data_lines = [line for line in md.split("\n") if line.startswith("| ") and "---" not in line]
    # 1 header + up to 6 data rows
    assert 1 <= len(data_lines) <= 7


def test_to_markdown_table_invalid_view(results):
    with pytest.raises(ValueError):
        to_markdown_table(results, view="nonexistent")


def test_to_markdown_report(results):
    report = to_markdown_report(results)
    assert "# " in report
    assert "Revenue" in report or "revenue" in report
    # Has at least 3 sections
    assert report.count("\n## ") >= 2
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
pytest tests/unit/test_exports_markdown.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement exports module**

`src/asset_finance_modeler/store/exports.py`:
```python
from typing import Any

from asset_finance_modeler.assets.saas.model import ModelResults

_VIEW_KEYS: dict[str, tuple[str, list[str]]] = {
    "pnl": ("pnl", ["revenue", "cogs", "gross_profit", "opex", "ebitda", "ebit", "tax", "net_income"]),
    "cashflow": ("cashflow", ["cfo", "cfi", "cff", "cash"]),
    "balance": ("balance", ["total_assets", "total_liabilities", "equity", "cash", "debt"]),
    "unit_econ": ("unit_econ", ["arpu", "gross_margin", "cac", "ltv", "ltv_cac", "payback_months"]),
}


def to_summary(results: ModelResults) -> dict[str, float | int]:
    """Return the summary dict already computed by SaasModel."""
    return dict(results.summary)


def _section_for_view(view: str) -> tuple[str, list[str]]:
    if view not in _VIEW_KEYS:
        raise ValueError(f"Unknown view {view!r}. Valid: {list(_VIEW_KEYS)}")
    return _VIEW_KEYS[view]


def _format_number(v: float | int) -> str:
    if isinstance(v, float):
        if abs(v) >= 1000:
            return f"{v:,.0f}"
        if abs(v) < 1:
            return f"{v:.4f}"
        return f"{v:.2f}"
    return str(v)


def to_markdown_table(results: ModelResults, view: str, max_periods: int | None = None) -> str:
    """Render a section of the model as a markdown table."""
    attr, columns = _section_for_view(view)
    data: dict[str, list[Any]] = getattr(results, attr)
    n = len(next(iter(data.values())))
    if max_periods is not None:
        n = min(n, max_periods)

    header = ["period"] + columns
    sep = ["---"] * len(header)
    rows = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(sep) + " |",
    ]
    for t in range(n):
        cells = [str(t)] + [_format_number(data[c][t]) for c in columns]
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows)


def to_markdown_report(results: ModelResults) -> str:
    """Narrative markdown report — for email or chat summaries."""
    s = results.summary
    sections: list[str] = []

    sections.append(f"# Modelo financiero — resumen ejecutivo")
    sections.append("")
    sections.append(f"Generado a partir de {len(results.pnl['revenue'])} periodos.")
    sections.append("")

    sections.append("## Ingresos y rentabilidad")
    sections.append(f"- Revenue Año 1: **{_format_number(s.get('revenue_y1', 0))} €**")
    sections.append(f"- Revenue último periodo: {_format_number(s.get('revenue_end_period', 0))} €")
    sections.append(f"- EBITDA margen último periodo: {s.get('ebitda_margin_end', 0):.1%}")
    sections.append("")

    sections.append("## Clientes y unit economics")
    sections.append(f"- Clientes activos al final: {_format_number(s.get('active_customers_end', 0))}")
    sections.append(f"- Unidades activas al final: {_format_number(s.get('active_units_end', 0))}")
    ltv_cac = s.get("ltv_cac_end", -1)
    if ltv_cac > 0:
        sections.append(f"- LTV/CAC: {ltv_cac:.2f}")
    sections.append("")

    sections.append("## Caja y valoración")
    sections.append(f"- Caja al final: {_format_number(s.get('cash_end', 0))} €")
    runway = s.get("runway_months", -1)
    if runway < 0:
        sections.append("- Runway: indefinido (no se cruza cero)")
    else:
        sections.append(f"- Runway: {runway} meses hasta cash=0")
    sections.append(f"- Enterprise value (DCF): {_format_number(s.get('enterprise_value', 0))} €")
    sections.append("")

    return "\n".join(sections)
```

- [ ] **Step 4: Run tests, verify pass**

```bash
pytest tests/unit/test_exports_markdown.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/asset_finance_modeler/store/exports.py tests/unit/test_exports_markdown.py
git commit -m "feat(store): exports — summary, markdown_table per view, markdown_report"
```

---

### Task 7: CSV + JSON exports

**Files:**
- Modify: `src/asset_finance_modeler/store/exports.py`
- Create: `tests/unit/test_exports_csv_json.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_exports_csv_json.py`:
```python
import csv
import json

import pytest

from asset_finance_modeler.assets.saas.loader import load_preset
from asset_finance_modeler.assets.saas.model import SaasModel
from asset_finance_modeler.store.exports import to_csv, to_json


@pytest.fixture(scope="module")
def results():
    return SaasModel(load_preset("gestnova")).run()


def test_to_csv_pnl(results, tmp_path):
    out = tmp_path / "pnl.csv"
    to_csv(results, view="pnl", path=str(out))
    assert out.exists()
    with out.open() as f:
        rows = list(csv.reader(f))
    # header + 60 data rows
    assert len(rows) == 61
    assert "revenue" in rows[0]
    assert "period" == rows[0][0]


def test_to_csv_invalid_view(results, tmp_path):
    with pytest.raises(ValueError):
        to_csv(results, view="invalid", path=str(tmp_path / "x.csv"))


def test_to_json_full(results):
    payload = to_json(results)
    parsed = json.loads(payload)
    assert "summary" in parsed
    assert "pnl" in parsed
    assert "cashflow" in parsed
    assert isinstance(parsed["pnl"]["revenue"], list)
    assert len(parsed["pnl"]["revenue"]) == 60


def test_to_json_writes_to_path(results, tmp_path):
    out = tmp_path / "results.json"
    to_json(results, path=str(out))
    assert out.exists()
    parsed = json.loads(out.read_text())
    assert "summary" in parsed
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
pytest tests/unit/test_exports_csv_json.py -v
```

Expected: ImportError on `to_csv`/`to_json`.

- [ ] **Step 3: Append to exports.py**

```python
import csv as _csv
import json as _json
from pathlib import Path


def to_csv(results: ModelResults, view: str, path: str) -> None:
    """Write a section to CSV file. Columns: period + view-specific keys."""
    attr, columns = _section_for_view(view)
    data: dict[str, list[Any]] = getattr(results, attr)
    n = len(next(iter(data.values())))
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        writer = _csv.writer(f)
        writer.writerow(["period"] + columns)
        for t in range(n):
            writer.writerow([t] + [data[c][t] for c in columns])


def to_json(results: ModelResults, path: str | None = None) -> str:
    """Return full results as JSON string. Optionally also write to file."""
    payload = {
        "summary": dict(results.summary),
        "pnl": results.pnl,
        "cashflow": results.cashflow,
        "balance": results.balance,
        "unit_econ": results.unit_econ,
        "valuation": results.valuation,
        "sensitivity": results.sensitivity,
        "debt_metrics": results.debt_metrics,
        "revenue_breakdown": results.revenue_breakdown,
    }
    text = _json.dumps(payload, default=str, indent=2)
    if path is not None:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text)
    return text
```

- [ ] **Step 4: Run tests, verify pass**

```bash
pytest tests/unit/test_exports_csv_json.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/asset_finance_modeler/store/exports.py tests/unit/test_exports_csv_json.py
git commit -m "feat(store): exports — to_csv (per view) and to_json (full)"
```

---

### Task 8: XLSX multi-sheet export

**Files:**
- Modify: `src/asset_finance_modeler/store/exports.py`
- Create: `tests/unit/test_exports_xlsx.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_exports_xlsx.py`:
```python
import pytest
from openpyxl import load_workbook

from asset_finance_modeler.assets.saas.loader import load_preset
from asset_finance_modeler.assets.saas.model import SaasModel
from asset_finance_modeler.store.exports import to_xlsx


@pytest.fixture(scope="module")
def results():
    return SaasModel(load_preset("gestnova")).run()


def test_to_xlsx_creates_file(results, tmp_path):
    out = tmp_path / "model.xlsx"
    to_xlsx(results, path=str(out))
    assert out.exists()


def test_to_xlsx_has_expected_sheets(results, tmp_path):
    out = tmp_path / "model.xlsx"
    to_xlsx(results, path=str(out))
    wb = load_workbook(out)
    sheet_names = set(wb.sheetnames)
    assert {"Summary", "PnL", "CashFlow", "Balance", "UnitEcon"}.issubset(sheet_names)


def test_to_xlsx_pnl_has_data(results, tmp_path):
    out = tmp_path / "model.xlsx"
    to_xlsx(results, path=str(out))
    wb = load_workbook(out)
    pnl = wb["PnL"]
    # Header row + 60 data rows
    assert pnl.max_row == 61
    # Column A header = "period", first data col after header
    assert pnl.cell(row=1, column=1).value == "period"
    assert pnl.cell(row=2, column=1).value == 0


def test_to_xlsx_summary_has_key_metrics(results, tmp_path):
    out = tmp_path / "model.xlsx"
    to_xlsx(results, path=str(out))
    wb = load_workbook(out)
    summary = wb["Summary"]
    # Summary is 2-column key:value
    keys = [summary.cell(row=r, column=1).value for r in range(2, summary.max_row + 1)]
    assert "revenue_y1" in keys
    assert "enterprise_value" in keys
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
pytest tests/unit/test_exports_xlsx.py -v
```

Expected: ImportError on `to_xlsx`.

- [ ] **Step 3: Append to exports.py**

```python
from openpyxl import Workbook

_XLSX_SHEETS: list[tuple[str, str, list[str]]] = [
    ("PnL", "pnl", ["revenue", "cogs", "gross_profit", "opex", "ebitda", "depreciation", "ebit", "interest_expense", "ebt", "tax", "net_income"]),
    ("CashFlow", "cashflow", ["cfo", "cfi", "cff", "cash", "delta_ar", "delta_ap"]),
    ("Balance", "balance", ["cash", "ar", "fixed_assets_net", "total_assets", "debt", "ap", "total_liabilities", "equity"]),
    ("UnitEcon", "unit_econ", ["arpu", "gross_margin", "cac", "ltv", "ltv_cac", "payback_months"]),
    ("DebtMetrics", "debt_metrics", ["dscr", "icr", "leverage"]),
    ("Revenue", "revenue_breakdown", ["active_units", "active_customers", "subscription_revenue", "setup_revenue", "total_revenue", "new_units", "new_customers"]),
]


def to_xlsx(results: ModelResults, path: str) -> None:
    """Write multi-sheet workbook: Summary + each statement view + assumptions."""
    wb = Workbook()

    # Summary sheet (key/value)
    summary_ws = wb.active
    summary_ws.title = "Summary"
    summary_ws.append(["metric", "value"])
    for key, value in results.summary.items():
        summary_ws.append([key, value])

    # Time-series sheets
    for sheet_name, attr, columns in _XLSX_SHEETS:
        ws = wb.create_sheet(sheet_name)
        data: dict[str, list[Any]] = getattr(results, attr)
        header = ["period"] + columns
        ws.append(header)
        n = len(next(iter(data.values())))
        for t in range(n):
            row = [t] + [data[c][t] if c in data else None for c in columns]
            ws.append(row)

    # Valuation
    val_ws = wb.create_sheet("Valuation")
    val_ws.append(["metric", "value"])
    for k, v in results.valuation.items():
        val_ws.append([k, v])

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
```

- [ ] **Step 4: Run tests, verify pass**

```bash
pytest tests/unit/test_exports_xlsx.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/asset_finance_modeler/store/exports.py tests/unit/test_exports_xlsx.py
git commit -m "feat(store): exports — to_xlsx multi-sheet workbook (Summary + PnL + CF + Balance + Unit + Debt + Revenue + Valuation)"
```

---

### Task 9: Sensitivity 1D over any model variable

**Files:**
- Create: `src/asset_finance_modeler/store/sensitivity.py`
- Create: `tests/unit/test_sensitivity.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_sensitivity.py`:
```python
import pytest

from asset_finance_modeler.core.scenario import Scenario, new_scenario_id
from asset_finance_modeler.store.sensitivity import sensitivity_1d


def test_sensitivity_pricing_revenue():
    base = Scenario(id=new_scenario_id(), name="b", base_model="gestnova", overrides={})
    out = sensitivity_1d(
        base,
        variable="revenue.sources[0].pricing.per_unit_per_period",
        values=[200, 250, 300, 350],
        metric="revenue_y1",
    )
    assert len(out["points"]) == 4
    # Monotonic: higher price → higher revenue
    revenues = [p["metric_value"] for p in out["points"]]
    assert revenues == sorted(revenues)


def test_sensitivity_churn_runway():
    base = Scenario(id=new_scenario_id(), name="b", base_model="gestnova", overrides={})
    out = sensitivity_1d(
        base,
        variable="revenue.sources[0].retention.monthly_churn_rate",
        values=[0.01, 0.05, 0.10],
        metric="enterprise_value",
    )
    # Higher churn → lower EV
    evs = [p["metric_value"] for p in out["points"]]
    assert evs[0] > evs[2]


def test_sensitivity_invalid_metric_raises():
    base = Scenario(id=new_scenario_id(), name="b", base_model="gestnova", overrides={})
    with pytest.raises(KeyError):
        sensitivity_1d(
            base,
            variable="revenue.sources[0].pricing.per_unit_per_period",
            values=[200, 250],
            metric="nonexistent_metric",
        )
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
pytest tests/unit/test_sensitivity.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement sensitivity**

`src/asset_finance_modeler/store/sensitivity.py`:
```python
from asset_finance_modeler.core.scenario import Scenario, new_scenario_id, run_scenario_saas


def sensitivity_1d(
    base_scenario: Scenario,
    variable: str,
    values: list[float],
    metric: str,
) -> dict[str, object]:
    """Run base_scenario with `variable` overridden across `values`, return
    list of {value, metric_value} points."""
    points: list[dict[str, float]] = []
    for value in values:
        # Compose: base overrides + the variable being swept
        merged = dict(base_scenario.overrides)
        merged[variable] = value
        run_s = Scenario(
            id=new_scenario_id(),
            name=f"sens-{variable}-{value}",
            base_model=base_scenario.base_model,
            overrides=merged,
        )
        results = run_scenario_saas(run_s)
        if metric not in results.summary:
            raise KeyError(f"metric {metric!r} not found in summary; available: {list(results.summary)}")
        points.append({"value": value, "metric_value": results.summary[metric]})

    return {"variable": variable, "metric": metric, "points": points}
```

- [ ] **Step 4: Run tests, verify pass**

```bash
pytest tests/unit/test_sensitivity.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/asset_finance_modeler/store/sensitivity.py tests/unit/test_sensitivity.py
git commit -m "feat(store): sensitivity_1d over arbitrary scenario variable + metric"
```

---

### Task 10: CLI thin wrapper

**Files:**
- Create: `src/asset_finance_modeler/cli/__init__.py`
- Create: `src/asset_finance_modeler/cli/main.py`
- Modify: `pyproject.toml` (add `[project.scripts]`)
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/test_cli.py`

- [ ] **Step 1: Write failing tests**

`tests/integration/__init__.py`: empty file.

`tests/integration/test_cli.py`:
```python
import json
import subprocess
import sys


def _run_cli(*args, cwd):
    cmd = [sys.executable, "-m", "asset_finance_modeler.cli.main", *args]
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(cwd))


def test_cli_list_models(tmp_path):
    result = _run_cli("list-models", cwd=tmp_path)
    assert result.returncode == 0
    assert "gestnova" in result.stdout


def test_cli_run_baseline_prints_summary(tmp_path):
    result = _run_cli("run", "--preset", "gestnova", "--output", "summary", cwd=tmp_path)
    assert result.returncode == 0
    # stdout should be valid JSON summary
    data = json.loads(result.stdout)
    assert "revenue_y1" in data


def test_cli_run_with_override(tmp_path):
    result = _run_cli(
        "run", "--preset", "gestnova",
        "--override", "revenue.sources[0].pricing.per_unit_per_period=200",
        "--output", "summary",
        cwd=tmp_path,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    base_result = _run_cli("run", "--preset", "gestnova", "--output", "summary", cwd=tmp_path)
    base_data = json.loads(base_result.stdout)
    # Override should reduce revenue
    assert data["revenue_end_period"] < base_data["revenue_end_period"]


def test_cli_run_export_csv(tmp_path):
    out_file = tmp_path / "pnl.csv"
    result = _run_cli(
        "run", "--preset", "gestnova",
        "--export", f"csv:pnl:{out_file}",
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert out_file.exists()
    assert "revenue" in out_file.read_text()
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
pytest tests/integration/test_cli.py -v
```

Expected: ImportError / module not found.

- [ ] **Step 3: Implement CLI**

`src/asset_finance_modeler/cli/__init__.py`: empty file.

`src/asset_finance_modeler/cli/main.py`:
```python
"""Thin CLI for asset-finance-modeler.

Examples:
    python -m asset_finance_modeler.cli.main list-models
    python -m asset_finance_modeler.cli.main run --preset gestnova --output summary
    python -m asset_finance_modeler.cli.main run --preset gestnova \\
        --override revenue.sources[0].pricing.per_unit_per_period=200 \\
        --export xlsx::./out.xlsx --export csv:pnl:./pnl.csv
"""
import argparse
import json
import sys

from asset_finance_modeler.core.scenario import Scenario, new_scenario_id, run_scenario_saas
from asset_finance_modeler.store.exports import (
    to_csv,
    to_json,
    to_markdown_report,
    to_markdown_table,
    to_summary,
    to_xlsx,
)

_AVAILABLE_PRESETS = ["gestnova"]


def _parse_override(spec: str) -> tuple[str, object]:
    if "=" not in spec:
        raise ValueError(f"Bad override (need key=value): {spec!r}")
    key, raw_value = spec.split("=", 1)
    # Try numeric, fall back to string
    try:
        value: object = int(raw_value)
    except ValueError:
        try:
            value = float(raw_value)
        except ValueError:
            value = raw_value
    return key.strip(), value


def _do_list_models() -> int:
    for name in _AVAILABLE_PRESETS:
        print(name)
    return 0


def _do_run(args: argparse.Namespace) -> int:
    overrides = {}
    for spec in args.override or []:
        k, v = _parse_override(spec)
        overrides[k] = v

    scenario = Scenario(
        id=new_scenario_id(),
        name=args.name or "cli-run",
        base_model=args.preset,
        overrides=overrides,
    )
    results = run_scenario_saas(scenario)

    # Print primary output
    if args.output == "summary":
        print(json.dumps(to_summary(results), default=str, indent=2))
    elif args.output == "json":
        print(to_json(results))
    elif args.output in ("pnl", "cashflow", "balance", "unit_econ"):
        print(to_markdown_table(results, view=args.output))
    elif args.output == "report":
        print(to_markdown_report(results))
    else:
        raise ValueError(f"Unknown --output: {args.output}")

    # Optional exports
    for export_spec in args.export or []:
        # Format: "csv:view:path" or "xlsx::path" or "json::path"
        parts = export_spec.split(":", 2)
        if len(parts) != 3:
            raise ValueError(f"Bad --export (expected fmt:view:path): {export_spec!r}")
        fmt, view, path = parts
        if fmt == "csv":
            to_csv(results, view=view, path=path)
        elif fmt == "xlsx":
            to_xlsx(results, path=path)
        elif fmt == "json":
            to_json(results, path=path)
        else:
            raise ValueError(f"Unknown export fmt: {fmt!r}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="asset-finance-modeler")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list-models")

    run_p = sub.add_parser("run")
    run_p.add_argument("--preset", required=True)
    run_p.add_argument("--name", default=None)
    run_p.add_argument("--override", action="append", default=[])
    run_p.add_argument("--output", default="summary",
                       choices=["summary", "json", "report", "pnl", "cashflow", "balance", "unit_econ"])
    run_p.add_argument("--export", action="append", default=[])

    args = parser.parse_args(argv)

    if args.cmd == "list-models":
        return _do_list_models()
    if args.cmd == "run":
        return _do_run(args)
    parser.error(f"Unknown command: {args.cmd}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

Add to `pyproject.toml` (right after the `dev = [...]` block, top-level):
```toml
[project.scripts]
asset-finance-modeler = "asset_finance_modeler.cli.main:main"
```

After editing pyproject.toml, re-install in editable mode:
```bash
pip install -e ".[dev]"
```

- [ ] **Step 4: Run tests, verify pass**

```bash
pytest tests/integration/test_cli.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/asset_finance_modeler/cli/ pyproject.toml tests/integration/
git commit -m "feat(cli): argparse-based CLI for list-models / run with overrides + exports"
```

---

### Task 11: End-to-end integration scenario

**Files:**
- Create: `tests/integration/test_end_to_end.py`

- [ ] **Step 1: Write the integration test (it should pass on first run if everything before is correct)**

`tests/integration/test_end_to_end.py`:
```python
import json

import pytest

from asset_finance_modeler.core.scenario import Scenario, new_scenario_id, run_scenario_saas
from asset_finance_modeler.store.compare import compare_scenarios
from asset_finance_modeler.store.exports import (
    to_csv,
    to_json,
    to_markdown_report,
    to_xlsx,
)
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore
from asset_finance_modeler.store.sensitivity import sensitivity_1d


def _persist_with_results(store, scenario):
    results = run_scenario_saas(scenario)
    scenario.results_snapshot = {"summary": dict(results.summary)}
    store.save(scenario)
    return scenario, results


def test_full_workflow(tmp_path):
    # 1. Set up store
    store = SQLiteScenarioStore(str(tmp_path / "scenarios.db"))
    store.initialize()

    # 2. Create baseline
    baseline = Scenario(
        id=new_scenario_id(), name="gestnova-baseline", base_model="gestnova",
        is_canonical=True, tags=["baseline"], notes="Initial baseline",
    )
    baseline, base_results = _persist_with_results(store, baseline)

    # 3. Branch: lower pricing
    lower_price = Scenario(
        id=new_scenario_id(), name="pricing-250", base_model="gestnova",
        parent_scenario_id=baseline.id,
        overrides={"revenue.sources[0].pricing.per_unit_per_period": 250},
        tags=["pricing", "downside"],
    )
    lower_price, _ = _persist_with_results(store, lower_price)

    # 4. Branch from lower_price: also reduce infra cost
    aggressive = Scenario(
        id=new_scenario_id(), name="pricing-250+infra-reduced", base_model="gestnova",
        parent_scenario_id=lower_price.id,
        overrides={
            "revenue.sources[0].pricing.per_unit_per_period": 250,
            "operating_expenses.infra_fixed_eur": 600,
        },
    )
    aggressive, _ = _persist_with_results(store, aggressive)

    # 5. Genealogy
    ancestors = store.get_ancestors(aggressive.id)
    assert [a.name for a in ancestors] == ["pricing-250", "gestnova-baseline"]
    descendants = store.get_descendants(baseline.id)
    descendant_names = {d.name for d in descendants}
    assert descendant_names == {"pricing-250", "pricing-250+infra-reduced"}

    # 6. Compare three scenarios
    all_three = [store.get(baseline.id), store.get(lower_price.id), store.get(aggressive.id)]
    table = compare_scenarios(all_three)
    assert table["scenarios"] == ["gestnova-baseline", "pricing-250", "pricing-250+infra-reduced"]
    # Baseline revenue should be highest
    revs = table["metrics"]["revenue_y1"]
    assert revs[0] > revs[1]

    # 7. Sensitivity sweep around aggressive
    sens = sensitivity_1d(
        store.get(aggressive.id),
        variable="revenue.sources[0].acquisition.cac_per_customer",
        values=[400, 600, 800, 1000, 1200],
        metric="enterprise_value",
    )
    assert len(sens["points"]) == 5
    # Higher CAC should reduce EV (approximately)
    first_ev = sens["points"][0]["metric_value"]
    last_ev = sens["points"][-1]["metric_value"]
    assert first_ev > last_ev

    # 8. Export all formats from baseline
    to_csv(base_results, view="pnl", path=str(tmp_path / "pnl.csv"))
    to_csv(base_results, view="cashflow", path=str(tmp_path / "cf.csv"))
    to_xlsx(base_results, path=str(tmp_path / "model.xlsx"))
    payload = to_json(base_results)
    parsed = json.loads(payload)
    report = to_markdown_report(base_results)

    assert (tmp_path / "pnl.csv").exists()
    assert (tmp_path / "cf.csv").exists()
    assert (tmp_path / "model.xlsx").exists()
    assert "summary" in parsed
    assert "# " in report

    # 9. Canonical protection
    with pytest.raises(PermissionError):
        store.delete(baseline.id)

    # 10. Delete non-canonical works
    store.delete(aggressive.id)
    assert store.get(aggressive.id).is_deleted is True
```

- [ ] **Step 2: Run the test**

```bash
pytest tests/integration/test_end_to_end.py -v
```

Expected: 1 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_end_to_end.py
git commit -m "test: end-to-end integration covering store + compare + sensitivity + exports"
```

---

### Task 12: Final sanity (pytest + ruff + mypy + smoke)

**Files:** none (verification only). If lints/types fail, fix inline and commit.

- [ ] **Step 1: Run full suite**

```bash
cd "/Users/rikyizquierdo/Documents/New project/asset-finance-modeler"
source .venv/bin/activate
pytest -v 2>&1 | tail -20
```

Expected: ≥ 115 tests passing.

- [ ] **Step 2: Run ruff**

```bash
ruff check src/ tests/
```

Expected: All checks passed. If errors appear, fix them inline (prefer code over rule-relaxation; for tests with magic numbers, the per-file-ignore is already active).

- [ ] **Step 3: Run mypy**

```bash
mypy src/
```

Expected: Success: no issues found. Fix any reported type errors inline.

- [ ] **Step 4: Verify CLI works end-to-end manually**

```bash
python -m asset_finance_modeler.cli.main list-models
python -m asset_finance_modeler.cli.main run --preset gestnova --output summary
python -m asset_finance_modeler.cli.main run --preset gestnova \
    --override 'revenue.sources[0].pricing.per_unit_per_period=250' \
    --output report
```

Expected: each prints sensible output.

- [ ] **Step 5: Commit any fixes**

```bash
git add -u
git commit -m "chore: lint and type fixes after Plan 2 sanity" || true
```

---

## End of Plan 2

After this plan, the library supports:
- Branching scenarios in a persistent tree
- Comparing N scenarios side-by-side
- Running 1D sensitivity on any variable for any summary metric
- Exporting results to CSV / XLSX / JSON / Markdown
- Driving everything from a CLI

**Estimated effort:** 4-5 hours with subagent-driven execution. Next: Plan 3 — wrap all of this as MCP tools so Ian can drive it conversationally.
