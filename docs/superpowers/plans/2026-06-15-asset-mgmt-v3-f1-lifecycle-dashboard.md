# F1 — Ciclo de vida del activo + Dashboard Cartera/Oportunidades — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar a cada activo un ciclo de vida (`opportunity` → `operational`) y un dashboard inicial que separa la **Cartera** (activos en operación) de las **Oportunidades** (valoraciones para comprar/invertir), con un botón "Marcar en operación" que promueve y congela el caso base.

**Architecture:** Migración SQLite **aditiva** sobre el `scenarios` store existente (4 columnas nuevas con defaults). El `Scenario` (Pydantic) gana 4 campos. La API extiende `web_api/assets.py` con `PATCH /api/assets/{id}/lifecycle`, un filtro `?lifecycle=` en el listado y en `/api/portfolio` (por defecto sin filtrar → comportamiento actual intacto). El frontend reemplaza el landing por un Dashboard con dos secciones que reutilizan el agregado de cartera filtrado por ciclo de vida.

**Tech Stack:** Python 3.12 · Pydantic v2 · FastAPI · SQLite · pytest · React 19 + Vite + Tailwind v4 · @tanstack/react-query · recharts · lucide-react (nuevo).

**Spec:** `docs/superpowers/specs/2026-06-15-asset-management-platform-v3-design.md` (F1).

**Reglas:** TDD en backend. No romper los 578 tests existentes ni v1/v2 (`/api/hybrid_consolidated/*`, `/api/models`, curvas, cartera v2). SIN EMOJIS en UI; iconos lucide; grado fondo/banco. Firmar cada commit con `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

**Convención de comandos:** los tests Python se ejecutan con `PYTHONPATH=src python -m pytest <ruta> -q`. El front se construye con `cd web && npm run build` y se testea con `cd web && npm test`.

---

## Task 1: Campos de ciclo de vida en el dataclass `Scenario`

**Files:**
- Modify: `src/asset_finance_modeler/core/scenario.py` (clase `Scenario`, líneas 30-45)
- Test: `tests/unit/test_scenario_lifecycle.py` (crear)

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/unit/test_scenario_lifecycle.py`:

```python
from asset_finance_modeler.core.scenario import Scenario, new_scenario_id


def test_scenario_lifecycle_defaults():
    s = Scenario(id=new_scenario_id(), name="X", base_model="bess_20mw_4h")
    assert s.lifecycle == "opportunity"
    assert s.commissioning_date is None
    assert s.base_locked is False
    assert s.tracking_frequency is None


def test_scenario_lifecycle_operational():
    from datetime import UTC, datetime

    s = Scenario(
        id=new_scenario_id(),
        name="Planta",
        base_model="solar_pv_50mw_spain",
        lifecycle="operational",
        commissioning_date=datetime(2026, 1, 1, tzinfo=UTC),
        base_locked=True,
        tracking_frequency="monthly",
    )
    assert s.lifecycle == "operational"
    assert s.commissioning_date.year == 2026
    assert s.base_locked is True
    assert s.tracking_frequency == "monthly"
```

- [ ] **Step 2: Ejecutar el test para verque falla**

Run: `PYTHONPATH=src python -m pytest tests/unit/test_scenario_lifecycle.py -q`
Expected: FAIL — `Scenario` no acepta `lifecycle` (`ValidationError`/`TypeError`).

- [ ] **Step 3: Añadir los campos al modelo**

En `src/asset_finance_modeler/core/scenario.py`, dentro de `class Scenario(BaseModel)`, después de `workspace_id: str | None = None` (línea 45) añadir:

```python
    # --- Ciclo de vida (v3 asset management) ---
    lifecycle: str = "opportunity"  # "opportunity" | "operational"
    commissioning_date: datetime | None = None
    base_locked: bool = False
    tracking_frequency: str | None = None  # "daily" | "monthly" | "quarterly"
```

(`datetime` ya está importado en la cabecera del archivo.)

- [ ] **Step 4: Ejecutar el test para verificar que pasa**

Run: `PYTHONPATH=src python -m pytest tests/unit/test_scenario_lifecycle.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/asset_finance_modeler/core/scenario.py tests/unit/test_scenario_lifecycle.py
git commit -m "feat(core): campos de ciclo de vida en Scenario (lifecycle/commissioning_date/base_locked/tracking_frequency)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Persistencia del ciclo de vida en `SQLiteScenarioStore` (migración aditiva)

**Files:**
- Modify: `src/asset_finance_modeler/store/scenarios.py` (`_SCHEMA` ~11-34, `initialize` ~62-74, `_to_row` ~76-94, `_from_row` ~96-115, `save` ~117-145, `list` ~154-178)
- Test: `tests/web/test_scenario_store_lifecycle.py` (crear)

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/web/test_scenario_store_lifecycle.py`:

```python
import sqlite3

from datetime import UTC, datetime

from asset_finance_modeler.core.scenario import Scenario, new_scenario_id
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore


def test_store_roundtrips_lifecycle(tmp_path):
    store = SQLiteScenarioStore(str(tmp_path / "s.db"))
    store.initialize()
    s = Scenario(
        id=new_scenario_id(),
        name="Planta FV",
        base_model="solar_pv_50mw_spain",
        lifecycle="operational",
        commissioning_date=datetime(2026, 1, 1, tzinfo=UTC),
        base_locked=True,
        tracking_frequency="monthly",
    )
    store.save(s)
    got = store.get(s.id)
    assert got is not None
    assert got.lifecycle == "operational"
    assert got.commissioning_date == datetime(2026, 1, 1, tzinfo=UTC)
    assert got.base_locked is True
    assert got.tracking_frequency == "monthly"


def test_store_lifecycle_defaults_for_new_db(tmp_path):
    store = SQLiteScenarioStore(str(tmp_path / "s.db"))
    store.initialize()
    s = Scenario(id=new_scenario_id(), name="Op", base_model="bess_20mw_4h")
    store.save(s)
    got = store.get(s.id)
    assert got.lifecycle == "opportunity"
    assert got.commissioning_date is None
    assert got.base_locked is False
    assert got.tracking_frequency is None


def test_store_list_filters_by_lifecycle(tmp_path):
    store = SQLiteScenarioStore(str(tmp_path / "s.db"))
    store.initialize()
    op = Scenario(id=new_scenario_id(), name="Op", base_model="bess_20mw_4h",
                  lifecycle="operational")
    opp = Scenario(id=new_scenario_id(), name="Opp", base_model="bess_20mw_4h")
    store.save(op)
    store.save(opp)
    ops = store.list(lifecycle="operational")
    assert [s.id for s in ops] == [op.id]
    opps = store.list(lifecycle="opportunity")
    assert [s.id for s in opps] == [opp.id]
    assert len(store.list()) == 2


def test_store_migrates_legacy_db_without_lifecycle_columns(tmp_path):
    # Simula una DB antigua sin las columnas nuevas, con una fila existente.
    db = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(db)
    conn.execute(
        """CREATE TABLE scenarios (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
            base_model TEXT NOT NULL, parent_scenario_id TEXT,
            overrides_json TEXT NOT NULL DEFAULT '{}',
            inputs_snapshot_json TEXT NOT NULL DEFAULT '{}',
            results_snapshot_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL, tags_json TEXT NOT NULL DEFAULT '[]',
            notes TEXT NOT NULL DEFAULT '', is_canonical INTEGER NOT NULL DEFAULT 0,
            is_deleted INTEGER NOT NULL DEFAULT 0, user_id TEXT NOT NULL DEFAULT 'default',
            workspace_id TEXT
        )"""
    )
    conn.execute(
        "INSERT INTO scenarios (id, name, base_model, created_at) VALUES (?,?,?,?)",
        ("scn-old", "Antiguo", "bess_20mw_4h", datetime(2025, 1, 1, tzinfo=UTC).isoformat()),
    )
    conn.commit()
    conn.close()

    store = SQLiteScenarioStore(db)
    store.initialize()  # debe añadir las columnas sin romper
    got = store.get("scn-old")
    assert got is not None
    assert got.lifecycle == "opportunity"  # default tras migración
    assert got.commissioning_date is None
    assert got.base_locked is False
    assert got.tracking_frequency is None
```

- [ ] **Step 2: Ejecutar el test para verificar que falla**

Run: `PYTHONPATH=src python -m pytest tests/web/test_scenario_store_lifecycle.py -q`
Expected: FAIL — las columnas/filtro no existen.

- [ ] **Step 3: Añadir columnas al `_SCHEMA`**

En `src/asset_finance_modeler/store/scenarios.py`, dentro de la tabla `scenarios` del `_SCHEMA`, después de `workspace_id TEXT,` añadir (antes de la línea `FOREIGN KEY (parent_scenario_id) ...`):

```sql
    lifecycle TEXT NOT NULL DEFAULT 'opportunity',
    commissioning_date TEXT,
    base_locked INTEGER NOT NULL DEFAULT 0,
    tracking_frequency TEXT,
```

- [ ] **Step 4: Añadir migración aditiva en `initialize`**

En `initialize`, después del bloque que añade `workspace_id` (línea ~74), añadir:

```python
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
```

- [ ] **Step 5: Serializar en `_to_row`**

En `_to_row`, antes del cierre `}` del dict devuelto, añadir:

```python
            "lifecycle": s.lifecycle,
            "commissioning_date": s.commissioning_date.isoformat() if s.commissioning_date else None,
            "base_locked": int(s.base_locked),
            "tracking_frequency": s.tracking_frequency,
```

- [ ] **Step 6: Deserializar en `_from_row`**

En `_from_row`, antes del cierre `)` de `return Scenario(...)`, añadir (con guardas `in keys` para DBs migradas en caliente):

```python
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
```

- [ ] **Step 7: Persistir en `save` (INSERT + ON CONFLICT)**

En `save`, en la lista de columnas del INSERT añadir `, lifecycle, commissioning_date, base_locked, tracking_frequency` tras `workspace_id`, y en `VALUES (...)` añadir `, :lifecycle, :commissioning_date, :base_locked, :tracking_frequency` tras `:workspace_id`. En el bloque `ON CONFLICT(id) DO UPDATE SET` añadir tras `workspace_id = excluded.workspace_id`:

```sql
,
                    lifecycle = excluded.lifecycle,
                    commissioning_date = excluded.commissioning_date,
                    base_locked = excluded.base_locked,
                    tracking_frequency = excluded.tracking_frequency
```

(Es decir: la coma va al final de la línea `workspace_id = excluded.workspace_id` y luego las cuatro asignaciones nuevas.)

- [ ] **Step 8: Añadir filtro `lifecycle` a `list`**

Cambiar la firma de `list` para añadir `lifecycle: str | None = None` (tras `workspace_id`) y, dentro, después del bloque `if workspace_id is not None:`, añadir:

```python
        if lifecycle is not None:
            clauses.append("lifecycle = ?")
            params.append(lifecycle)
```

Actualizar también la firma del `Protocol` `ScenarioStore.list` (líneas 41-47) para incluir `lifecycle: str | None = None`.

- [ ] **Step 9: Ejecutar tests + suite del store**

Run: `PYTHONPATH=src python -m pytest tests/web/test_scenario_store_lifecycle.py tests/web/test_assets_api.py tests/web/test_portfolio_api.py -q`
Expected: PASS (todos verdes).

- [ ] **Step 10: Commit**

```bash
git add src/asset_finance_modeler/store/scenarios.py tests/web/test_scenario_store_lifecycle.py
git commit -m "feat(store): persistir ciclo de vida del activo (migracion aditiva + filtro list)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Endpoint `PATCH /api/assets/{id}/lifecycle` + `lifecycle` en el listado

**Files:**
- Modify: `src/asset_finance_modeler/web_api/assets.py` (`list_assets` ~100-114, añadir endpoint PATCH; imports)
- Test: `tests/web/test_lifecycle_api.py` (crear)

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/web/test_lifecycle_api.py`:

```python
from fastapi.testclient import TestClient


def _client(monkeypatch, tmp_path):
    monkeypatch.setenv("SIM_TOKEN", "tk")
    monkeypatch.setenv("SIM_ONLY", "1")
    monkeypatch.setenv("ASSET_FINANCE_DB_PATH", str(tmp_path))
    from asset_finance_modeler.mcp_server.http_server import app
    return TestClient(app)


def test_new_asset_is_opportunity_by_default(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    aid = c.post("/api/assets?t=tk",
                 json={"model_id": "bess_20mw_4h", "name": "B", "overrides": {}}).json()["id"]
    lst = c.get("/api/assets?t=tk").json()["assets"]
    row = next(a for a in lst if a["id"] == aid)
    assert row["lifecycle"] == "opportunity"


def test_promote_to_operational(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    aid = c.post("/api/assets?t=tk",
                 json={"model_id": "bess_20mw_4h", "name": "B", "overrides": {}}).json()["id"]
    r = c.patch(f"/api/assets/{aid}/lifecycle?t=tk",
                json={"lifecycle": "operational", "tracking_frequency": "monthly"})
    assert r.status_code == 200
    body = r.json()
    assert body["lifecycle"] == "operational"
    assert body["base_locked"] is True
    assert body["commissioning_date"]  # fecha fijada
    assert body["tracking_frequency"] == "monthly"


def test_list_filters_by_lifecycle(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    a1 = c.post("/api/assets?t=tk", json={"model_id": "bess_20mw_4h", "name": "A1"}).json()["id"]
    a2 = c.post("/api/assets?t=tk", json={"model_id": "bess_20mw_4h", "name": "A2"}).json()["id"]
    c.patch(f"/api/assets/{a1}/lifecycle?t=tk", json={"lifecycle": "operational"})
    op = c.get("/api/assets?t=tk&lifecycle=operational").json()["assets"]
    assert [a["id"] for a in op] == [a1]
    opp = c.get("/api/assets?t=tk&lifecycle=opportunity").json()["assets"]
    assert [a["id"] for a in opp] == [a2]


def test_demote_to_opportunity(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    aid = c.post("/api/assets?t=tk", json={"model_id": "bess_20mw_4h", "name": "B"}).json()["id"]
    c.patch(f"/api/assets/{aid}/lifecycle?t=tk", json={"lifecycle": "operational"})
    body = c.patch(f"/api/assets/{aid}/lifecycle?t=tk", json={"lifecycle": "opportunity"}).json()
    assert body["lifecycle"] == "opportunity"
    assert body["base_locked"] is False
    assert body["commissioning_date"] is None


def test_patch_unknown_asset_404(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    r = c.patch("/api/assets/scn-nope/lifecycle?t=tk", json={"lifecycle": "operational"})
    assert r.status_code == 404


def test_patch_invalid_lifecycle_422(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    aid = c.post("/api/assets?t=tk", json={"model_id": "bess_20mw_4h", "name": "B"}).json()["id"]
    r = c.patch(f"/api/assets/{aid}/lifecycle?t=tk", json={"lifecycle": "bogus"})
    assert r.status_code == 422
```

- [ ] **Step 2: Ejecutar el test para verificar que falla**

Run: `PYTHONPATH=src python -m pytest tests/web/test_lifecycle_api.py -q`
Expected: FAIL — el endpoint PATCH no existe y `lifecycle` no está en el listado.

- [ ] **Step 3: Añadir imports**

En `src/asset_finance_modeler/web_api/assets.py`, en las importaciones de cabecera añadir:

```python
from datetime import UTC, datetime
from typing import Literal
```

(`Any` ya está importado; `BaseModel` y `Field` vienen de pydantic — cambiar la línea `from pydantic import BaseModel` por `from pydantic import BaseModel, Field`.)

- [ ] **Step 4: Incluir `lifecycle` en `list_assets` + filtro**

Reemplazar la función `list_assets` (líneas ~100-114) por:

```python
@router.get("")
def list_assets(lifecycle: str | None = None) -> dict[str, Any]:
    scenarios = _store().list(lifecycle=lifecycle)
    return {
        "assets": [
            {
                "id": s.id,
                "name": s.name,
                "model_id": s.base_model,
                "created_at": s.created_at.isoformat(),
                "kpis": s.results_snapshot.get("kpis", {}),
                "lifecycle": s.lifecycle,
                "commissioning_date": (
                    s.commissioning_date.isoformat() if s.commissioning_date else None
                ),
                "tracking_frequency": s.tracking_frequency,
            }
            for s in scenarios
        ]
    }
```

- [ ] **Step 5: Añadir el endpoint PATCH**

Justo después de `delete_asset` (línea ~135) y antes de `portfolio_router = ...` (línea ~138), añadir:

```python
class LifecycleBody(BaseModel):
    lifecycle: Literal["opportunity", "operational"]
    tracking_frequency: Literal["daily", "monthly", "quarterly"] | None = None
    commissioning_date: str | None = None  # ISO; si falta al promover, se usa ahora


@router.patch("/{asset_id}/lifecycle")
def set_lifecycle(asset_id: str, body: LifecycleBody) -> dict[str, Any]:
    store = _store()
    s = store.get(asset_id)
    if s is None or s.is_deleted:
        raise HTTPException(status_code=404, detail=f"unknown asset: {asset_id}")
    if body.lifecycle == "operational":
        s.lifecycle = "operational"
        s.base_locked = True
        s.is_canonical = True
        s.tracking_frequency = body.tracking_frequency or s.tracking_frequency or "monthly"
        if body.commissioning_date:
            s.commissioning_date = datetime.fromisoformat(body.commissioning_date)
        elif s.commissioning_date is None:
            s.commissioning_date = datetime.now(UTC)
    else:  # demote -> opportunity
        s.lifecycle = "opportunity"
        s.base_locked = False
        s.is_canonical = False
        s.commissioning_date = None
        s.tracking_frequency = None
    store.save(s)
    return {
        "id": s.id,
        "lifecycle": s.lifecycle,
        "base_locked": s.base_locked,
        "commissioning_date": (
            s.commissioning_date.isoformat() if s.commissioning_date else None
        ),
        "tracking_frequency": s.tracking_frequency,
    }
```

> Nota: `set_canonical` del store fuerza is_canonical pero también puede renombrar; aquí persistimos `is_canonical` directamente vía `save` (más simple y suficiente para F1). `delete` ya impide borrar canónicos, lo que protege el caso base de un activo en operación — comportamiento deseado.

- [ ] **Step 6: Ejecutar tests**

Run: `PYTHONPATH=src python -m pytest tests/web/test_lifecycle_api.py tests/web/test_assets_api.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/asset_finance_modeler/web_api/assets.py tests/web/test_lifecycle_api.py
git commit -m "feat(web_api): PATCH /api/assets/{id}/lifecycle (promover/degradar) + lifecycle en listado

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Filtro `lifecycle` en `/api/portfolio`

**Files:**
- Modify: `src/asset_finance_modeler/web_api/assets.py` (`portfolio` ~166-210)
- Test: `tests/web/test_portfolio_lifecycle.py` (crear)

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/web/test_portfolio_lifecycle.py`:

```python
from fastapi.testclient import TestClient


def _client(monkeypatch, tmp_path):
    monkeypatch.setenv("SIM_TOKEN", "tk")
    monkeypatch.setenv("SIM_ONLY", "1")
    monkeypatch.setenv("ASSET_FINANCE_DB_PATH", str(tmp_path))
    from asset_finance_modeler.mcp_server.http_server import app
    return TestClient(app)


def test_portfolio_filters_by_lifecycle(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    a1 = c.post("/api/assets?t=tk", json={"model_id": "bess_20mw_4h", "name": "Op"}).json()["id"]
    c.post("/api/assets?t=tk", json={"model_id": "bess_20mw_4h", "name": "Opp"})
    c.patch(f"/api/assets/{a1}/lifecycle?t=tk", json={"lifecycle": "operational"})

    op = c.get("/api/portfolio?t=tk&lifecycle=operational").json()
    assert op["totals"]["count"] == 1
    assert [a["id"] for a in op["assets"]] == [a1]

    opp = c.get("/api/portfolio?t=tk&lifecycle=opportunity").json()
    assert opp["totals"]["count"] == 1

    all_ = c.get("/api/portfolio?t=tk").json()  # sin filtro = todos (compat v2)
    assert all_["totals"]["count"] == 2
```

- [ ] **Step 2: Ejecutar el test para verificar que falla**

Run: `PYTHONPATH=src python -m pytest tests/web/test_portfolio_lifecycle.py -q`
Expected: FAIL — `portfolio` no acepta `lifecycle`.

- [ ] **Step 3: Añadir el filtro a `portfolio`**

En `portfolio` (línea ~166), cambiar la firma a:

```python
@portfolio_router.get("")
def portfolio(ids: str | None = None, lifecycle: str | None = None) -> dict[str, Any]:
```

y cambiar la línea `for s in _store().list():` (línea ~178) por:

```python
    for s in _store().list(lifecycle=lifecycle):
```

(El resto del cuerpo no cambia: por defecto `lifecycle=None` → lista todos, comportamiento v2 intacto.)

- [ ] **Step 4: Ejecutar tests + suite de portfolio**

Run: `PYTHONPATH=src python -m pytest tests/web/test_portfolio_lifecycle.py tests/web/test_portfolio_api.py tests/unit/test_portfolio.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/asset_finance_modeler/web_api/assets.py tests/web/test_portfolio_lifecycle.py
git commit -m "feat(web_api): filtro lifecycle en /api/portfolio (cartera vs oportunidades), sin filtro = compat v2

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Suite backend completa (regresión)

**Files:** ninguno (verificación)

- [ ] **Step 1: Ejecutar la suite completa**

Run: `PYTHONPATH=src python -m pytest -q`
Expected: PASS — los 578 previos + los nuevos (≈ +12). Si algún test de v1/v2 falla, corregir la causa (no el test) antes de seguir.

- [ ] **Step 2: Lint/types si están configurados**

Run: `ruff check src/asset_finance_modeler/core/scenario.py src/asset_finance_modeler/store/scenarios.py src/asset_finance_modeler/web_api/assets.py` y `mypy src/asset_finance_modeler/web_api/assets.py` (si el repo los usa).
Expected: limpio. Corregir lo que salga.

(No hay commit en esta tarea salvo que el lint exija cambios; en ese caso commitea con `chore: lint F1 backend`.)

---

## Task 6: Cliente API frontend — ciclo de vida

**Files:**
- Modify: `web/src/api.ts` (tipos `SavedAssetSummary` ~128-134, `listAssets` ~212-215, `getPortfolio` ~271-274; añadir `setLifecycle`)
- Test: ninguno nuevo (se cubre vía build + el test de Task 8)

- [ ] **Step 1: Añadir el tipo de ciclo de vida y ampliar `SavedAssetSummary`**

En `web/src/api.ts`, antes de `export type SavedAssetSummary` (línea ~128) añadir:

```typescript
export type Lifecycle = "opportunity" | "operational";
export type TrackingFrequency = "daily" | "monthly" | "quarterly";
```

y ampliar `SavedAssetSummary`:

```typescript
export type SavedAssetSummary = {
  id: string;
  name: string;
  model_id: string;
  created_at: string;
  kpis: Kpis;
  lifecycle: Lifecycle;
  commissioning_date: string | null;
  tracking_frequency: TrackingFrequency | null;
};
```

- [ ] **Step 2: Filtro en `listAssets` y `getPortfolio`**

Reemplazar `listAssets` (líneas ~212-215) por:

```typescript
export async function listAssets(lifecycle?: Lifecycle): Promise<SavedAssetSummary[]> {
  const q = lifecycle ? `?lifecycle=${lifecycle}` : "";
  const d = await getJson<{ assets: SavedAssetSummary[] }>(`/api/assets${q}`);
  return d.assets;
}
```

Reemplazar `getPortfolio` (líneas ~271-274) por:

```typescript
export async function getPortfolio(
  opts?: { ids?: string[]; lifecycle?: Lifecycle },
): Promise<Portfolio> {
  const qs: string[] = [];
  if (opts?.ids && opts.ids.length > 0)
    qs.push(`ids=${opts.ids.map(encodeURIComponent).join(",")}`);
  if (opts?.lifecycle) qs.push(`lifecycle=${opts.lifecycle}`);
  const q = qs.length ? `?${qs.join("&")}` : "";
  return getJson<Portfolio>(`/api/portfolio${q}`);
}
```

> Esto cambia la firma de `getPortfolio` (antes `ids?: string[]`). El único llamador actual está en `PortfolioOverview.tsx` y se actualiza en la Task 7.

- [ ] **Step 3: Añadir `setLifecycle`**

Al final de la sección de persistencia (tras `deleteAsset`, ~línea 238) añadir:

```typescript
export async function setLifecycle(
  id: string,
  body: { lifecycle: Lifecycle; tracking_frequency?: TrackingFrequency; commissioning_date?: string },
): Promise<{ id: string; lifecycle: Lifecycle; base_locked: boolean; commissioning_date: string | null; tracking_frequency: TrackingFrequency | null }> {
  const r = await fetch(withToken(`/api/assets/${id}/lifecycle`), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`lifecycle update failed: ${r.status}`);
  return r.json();
}
```

- [ ] **Step 4: Verificar tipos (build parcial)**

Run: `cd web && npx tsc -b --noEmit`
Expected: PASS salvo el llamador de `getPortfolio` en `PortfolioOverview.tsx` (se arregla en Task 7). Si el único error de tipos es ese, continúa; si hay otros, corrígelos.

- [ ] **Step 5: Commit**

```bash
git add web/src/api.ts
git commit -m "feat(web): cliente API de ciclo de vida (setLifecycle + filtros lifecycle en listAssets/getPortfolio)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Dashboard con dos secciones — Cartera (operación) y Oportunidades

**Files:**
- Create: `web/src/components/Dashboard.tsx`
- Create: `web/src/components/AssetGroup.tsx`
- Modify: `web/src/components/PortfolioOverview.tsx` (adaptar `getPortfolio` a la nueva firma + aceptar `lifecycle`)
- Modify: `web/src/App.tsx` (usar `Dashboard` en el landing en lugar de `PortfolioOverview` directo; etiqueta header)
- Modify: `web/package.json` (añadir `lucide-react`)

- [ ] **Step 1: Instalar lucide-react**

Run: `cd web && npm install lucide-react`
Expected: añade `lucide-react` a `dependencies`. (Iconos limpios, SIN emojis.)

- [ ] **Step 2: Adaptar `PortfolioOverview` a la nueva firma y a un `lifecycle` opcional**

En `web/src/components/PortfolioOverview.tsx`:
- Ampliar `Props`:

```typescript
type Props = {
  /** Open a saved asset in the detail editor (drill-in). */
  onOpenAsset: (a: SavedAssetSummary) => void;
  /** Restrict the listing+aggregate to one lifecycle bucket. */
  lifecycle?: import("../api").Lifecycle;
  /** Optional action column rendered per row (e.g. "Marcar en operación"). */
  rowAction?: (a: SavedAssetSummary) => React.ReactNode;
};
```

- Cambiar la query de assets para filtrar por lifecycle:

```typescript
  const assetsQuery = useQuery({
    queryKey: ["assets", lifecycle ?? "all"],
    queryFn: () => listAssets(lifecycle),
  });
```

- Cambiar la query de portfolio a la nueva firma (objeto):

```typescript
  const portfolioQuery = useQuery({
    queryKey: ["portfolio", lifecycle ?? "all", allIncluded ? "all" : includedIds.join(",")],
    queryFn: () =>
      getPortfolio({ lifecycle, ids: allIncluded ? undefined : includedIds }),
  });
```

- Añadir `import type React from "react";` arriba si hace falta para `React.ReactNode` (o usa `ReactNode` importado de "react").
- Si se pasa `rowAction`, renderizar una columna extra "Acción" al final de la tabla: añadir `<th className="px-3 py-2.5 text-right font-medium">Acción</th>` en el `<thead>` y, en cada fila, antes del `</tr>`, una celda:

```tsx
                  {rowAction && (
                    <td className="px-3 py-2.5 text-right">
                      {(() => {
                        const a = allAssets.find((x) => x.id === r.id);
                        return a ? rowAction(a) : null;
                      })()}
                    </td>
                  )}
```

- Quitar el texto de cabecera fijo "Vista de cartera"/"Centro de control…" para que el título lo ponga el contenedor (Dashboard). Sustituir el bloque `<div className="flex items-end justify-between">…</div>` (líneas ~222-232) por solo el `recalcBadge` alineado a la derecha:

```tsx
      <div className="flex justify-end">{recalcBadge}</div>
```

- [ ] **Step 3: Crear `AssetGroup.tsx` (cabecera de sección con icono + contador)**

Crear `web/src/components/AssetGroup.tsx`:

```tsx
import type { ReactNode } from "react";

type Props = {
  title: string;
  subtitle: string;
  icon: ReactNode;
  count: number;
  children: ReactNode;
};

export default function AssetGroup({ title, subtitle, icon, count, children }: Props) {
  return (
    <section className="space-y-4">
      <div className="flex items-center gap-3 border-b border-slate-200 pb-3">
        <span className="grid h-9 w-9 place-items-center rounded-lg bg-accent-600/10 text-accent-700">
          {icon}
        </span>
        <div className="flex-1">
          <h2 className="text-base font-semibold text-slate-900">{title}</h2>
          <p className="text-xs text-slate-500">{subtitle}</p>
        </div>
        <span className="rounded-full bg-slate-100 px-3 py-1 text-sm font-semibold tabular-nums text-slate-700">
          {count}
        </span>
      </div>
      {children}
    </section>
  );
}
```

- [ ] **Step 4: Crear `Dashboard.tsx` (las dos secciones + botón "Marcar en operación")**

Crear `web/src/components/Dashboard.tsx`:

```tsx
import { useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, Search } from "lucide-react";
import { listAssets, setLifecycle } from "../api";
import type { SavedAssetSummary } from "../api";
import AssetGroup from "./AssetGroup";
import PortfolioOverview from "./PortfolioOverview";

type Props = {
  onOpenAsset: (a: SavedAssetSummary) => void;
};

export default function Dashboard({ onOpenAsset }: Props) {
  const queryClient = useQueryClient();
  // Lightweight counts for the section headers (cheap list, not the heavy aggregate).
  const allQuery = useQuery({ queryKey: ["assets", "all"], queryFn: () => listAssets() });
  const all = allQuery.data ?? [];

  const counts = useMemo(() => {
    let op = 0;
    let opp = 0;
    for (const a of all) (a.lifecycle === "operational" ? (op += 1) : (opp += 1));
    return { op, opp };
  }, [all]);

  const promote = async (a: SavedAssetSummary) => {
    await setLifecycle(a.id, { lifecycle: "operational" });
    queryClient.invalidateQueries({ queryKey: ["assets"] });
    queryClient.invalidateQueries({ queryKey: ["portfolio"] });
  };

  return (
    <div className="mx-auto max-w-[1400px] space-y-10">
      <AssetGroup
        title="Cartera · activos en operación"
        subtitle="Gestión y seguimiento del día a día"
        icon={<Building2 size={18} strokeWidth={2} />}
        count={counts.op}
      >
        <PortfolioOverview onOpenAsset={onOpenAsset} lifecycle="operational" />
      </AssetGroup>

      <AssetGroup
        title="Oportunidades · valoraciones"
        subtitle="Simulaciones para evaluar compra o inversión (no cuentan como cartera)"
        icon={<Search size={18} strokeWidth={2} />}
        count={counts.opp}
      >
        <PortfolioOverview
          onOpenAsset={onOpenAsset}
          lifecycle="opportunity"
          rowAction={(a) => (
            <button
              type="button"
              onClick={() => promote(a)}
              className="rounded-md border border-accent-300 bg-accent-50 px-2.5 py-1 text-xs font-medium text-accent-700 transition hover:bg-accent-100"
            >
              Marcar en operación
            </button>
          )}
        />
      </AssetGroup>
    </div>
  );
}
```

- [ ] **Step 5: Usar `Dashboard` en `App.tsx`**

En `web/src/App.tsx`:
- Cambiar el import `import PortfolioOverview from "./components/PortfolioOverview";` por `import Dashboard from "./components/Dashboard";`.
- En el bloque `view === "portfolio"` (líneas ~201-204), sustituir `<PortfolioOverview onOpenAsset={selectAsset} />` por `<Dashboard onOpenAsset={selectAsset} />`.
- Cambiar el texto del botón del header `Cartera` (línea ~184) por `Inicio` (el landing ahora muestra Cartera + Oportunidades).

- [ ] **Step 6: Build**

Run: `cd web && npm run build`
Expected: PASS — genera `web/dist`. Corregir cualquier error de tipos (especialmente el `getPortfolio` de PortfolioOverview ya adaptado en Step 2).

- [ ] **Step 7: Commit**

```bash
git add web/src/components/Dashboard.tsx web/src/components/AssetGroup.tsx web/src/components/PortfolioOverview.tsx web/src/App.tsx web/package.json web/package-lock.json
git commit -m "feat(web): dashboard inicial con Cartera (operacion) y Oportunidades + boton Marcar en operacion

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Test del frontend — el dashboard separa y promueve

**Files:**
- Create: `web/src/components/Dashboard.test.tsx`

- [ ] **Step 1: Escribir el test**

Crear `web/src/components/Dashboard.test.tsx` (sigue el patrón de `PortfolioOverview.test.tsx` ya existente — léelo primero para reusar el wrapper de QueryClient y los mocks de `../api`):

```tsx
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Dashboard from "./Dashboard";

vi.mock("../api", () => ({
  listAssets: vi.fn(),
  setLifecycle: vi.fn().mockResolvedValue({ id: "scn-2", lifecycle: "operational" }),
  getPortfolio: vi.fn().mockResolvedValue({ assets: [], totals: { npv: 0, capex: 0, revenue_y1: 0, count: 0 } }),
}));

import { listAssets, setLifecycle } from "../api";

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("Dashboard", () => {
  beforeEach(() => {
    vi.mocked(listAssets).mockResolvedValue([
      { id: "scn-1", name: "Planta", model_id: "solar_pv_50mw_spain", created_at: "2026-01-01T00:00:00Z", kpis: {}, lifecycle: "operational", commissioning_date: "2026-01-01T00:00:00Z", tracking_frequency: "monthly" },
      { id: "scn-2", name: "Oportunidad X", model_id: "bess_20mw_4h", created_at: "2026-02-01T00:00:00Z", kpis: {}, lifecycle: "opportunity", commissioning_date: null, tracking_frequency: null },
    ]);
  });

  it("muestra las dos secciones Cartera y Oportunidades", async () => {
    wrap(<Dashboard onOpenAsset={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText(/Cartera/i)).toBeInTheDocument();
      expect(screen.getByText(/Oportunidades/i)).toBeInTheDocument();
    });
  });

  it("el botón Marcar en operación llama a setLifecycle con operational", async () => {
    wrap(<Dashboard onOpenAsset={() => {}} />);
    const btn = await screen.findByText("Marcar en operación");
    fireEvent.click(btn);
    await waitFor(() =>
      expect(setLifecycle).toHaveBeenCalledWith("scn-2", { lifecycle: "operational" }),
    );
  });
});
```

> Si `PortfolioOverview` requiere más exports mockeados de `../api` (p. ej. `getPortfolio` ya está), añádelos al `vi.mock`. Ajusta el matcher de texto si aparece duplicado (usa `getAllByText` o un selector más específico).

- [ ] **Step 2: Ejecutar el test**

Run: `cd web && npm test`
Expected: PASS — los nuevos + los existentes (CurvesPanel, KpiCards, PortfolioOverview).

- [ ] **Step 3: Commit**

```bash
git add web/src/components/Dashboard.test.tsx
git commit -m "test(web): dashboard separa Cartera/Oportunidades y promueve a operacion

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Verificación end-to-end en vivo

**Files:** ninguno (verificación manual asistida)

- [ ] **Step 1: Arrancar el servidor (con los flags operativos)**

Run (una sola vez, sin matar procesos después):
```bash
cd "/Users/rikyizquierdo/Documents/New project/asset-finance-modeler" && \
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 SIM_ONLY=1 SIM_WEB_DIST=$(pwd)/web/dist PORT=8015 PYTHONPATH=src \
nohup python -m asset_finance_modeler.mcp_server.http_server > /tmp/afm_server.log 2>&1 &
sleep 3
```

- [ ] **Step 2: Verificar el flujo lifecycle por API**

```bash
curl -s -X POST localhost:8015/api/assets -H 'Content-Type: application/json' \
  -d '{"model_id":"bess_20mw_4h","name":"BESS Demo"}'   # → {"id":"scn-..."}
# usar ese id:
curl -s localhost:8015/api/assets?lifecycle=opportunity   # aparece BESS Demo
curl -s -X PATCH localhost:8015/api/assets/<ID>/lifecycle -H 'Content-Type: application/json' \
  -d '{"lifecycle":"operational","tracking_frequency":"monthly"}'   # → lifecycle operational
curl -s localhost:8015/api/portfolio?lifecycle=operational           # count 1
curl -s localhost:8015/api/portfolio?lifecycle=opportunity           # count 0
```
Expected: el activo se mueve de Oportunidades a Cartera; `commissioning_date` queda fijada.

- [ ] **Step 3: Verificar el dashboard servido**

Run: `curl -s -o /dev/null -w "%{http_code}\n" localhost:8015/`
Expected: `200` (SPA servida). (Opcional: abrir en navegador y ver las dos secciones.)

- [ ] **Step 4: Registrar el resultado** (sin commit). Si algo falla, volver a la tarea correspondiente.

---

## Notas de cierre (no es una tarea de implementación)

- F1 NO toca el motor ni añade datos reales (eso es F2/F3). El caso base se "congela" marcando `is_canonical=True` (el store ya impide borrar canónicos).
- Tras F1: actualizar la memoria `gestnova_finance_engine.md` con el hito y arrancar el plan de F2 (tabla `asset_actuals` + captura + varianza).
- La migración es aditiva: DBs v2 existentes siguen cargando y sus activos aparecen como `opportunity` por defecto (revisar si alguno debería marcarse en operación al desplegar).
