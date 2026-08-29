# Plataforma v2 genérica multi-activo — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Generalizar la plataforma a CUALQUIER activo: exponer todos los inputs de cualquier modelo del motor (por secciones), correrlo (KPIs + cuenta de resultados + FCF + curvas), y **guardar/listar/revisar** carteras de activos. Estética grado banco de inversión.

**Architecture:** Mismo contenedor FastAPI+SPA. Se añade introspección genérica (`web_api/introspect.py`), rutas genéricas (`web_api/models.py` → `/api/models/*`) y persistencia (`web_api/assets.py` → `/api/assets/*` sobre el `SQLiteScenarioStore` existente). Frontend `web/` se reescribe a multi-activo (panel de cartera/presets + editor dinámico por secciones + estados financieros), IB-grade sin emojis.

**Tech Stack:** FastAPI/pydantic/pytest (backend), React 19 + Vite + Tailwind v4 + react-query + recharts (frontend).

**Repo/rama:** `/Users/rikyizquierdo/Documents/New project/asset-finance-modeler`, rama `feat/finance-engine-general-deals`. No romper los 557 tests ni la v1 (`deals/hybrid_consolidated.py`, `/api/hybrid_consolidated/*` se mantienen). Solo correr `tests/web tests/core tests/unit`.

## File Structure
- `web_api/introspect.py` — **Create**: `schema_tree`, `set_by_path` (puras).
- `web_api/models.py` — **Create**: lógica genérica (lista de modelos, schema, run→kpis+PyG+FCF+curvas, export) + router `/api/models/*`.
- `web_api/assets.py` — **Create**: persistencia (CRUD) + router `/api/assets/*`.
- `mcp_server/http_server.py` — **Modify**: include_router de los dos nuevos routers.
- `web/src/*` — **Modify/Create**: multi-activo (AssetPanel, DynamicInputs, Statements, restyle).
- `tests/web/test_introspect.py`, `test_models_api.py`, `test_assets_api.py` — **Create**.

---

## FASE A — Backend genérico + persistencia

### Task A1: Introspección genérica (`web_api/introspect.py`)

**Files:** Create `src/asset_finance_modeler/web_api/introspect.py`. Test `tests/web/test_introspect.py`.

- [ ] **Step 1 — Failing test:**
```python
from asset_finance_modeler.web_api.introspect import schema_tree, set_by_path


def test_schema_tree_flattens_nested_and_lists():
    cfg = {"production": {"capacity_mwp": 5.0}, "revenue": [{"price_eur_per_unit": 45.0}], "financing": {"senior": {"interest_rate": 0.032}}}
    leaves = {l["path"]: l for l in schema_tree(cfg)}
    assert "production.capacity_mwp" in leaves
    assert "revenue[0].price_eur_per_unit" in leaves
    assert "financing.senior.interest_rate" in leaves
    assert leaves["production.capacity_mwp"]["type"] == "number"
    assert leaves["production.capacity_mwp"]["section"] == "production"


def test_set_by_path_nested_and_indexed():
    cfg = {"production": {"capacity_mwp": 5.0}, "revenue": [{"price_eur_per_unit": 45.0}]}
    out = set_by_path(cfg, "revenue[0].price_eur_per_unit", 50.0)
    assert out["revenue"][0]["price_eur_per_unit"] == 50.0
    assert cfg["revenue"][0]["price_eur_per_unit"] == 43.0   # no muta el input
    out2 = set_by_path(cfg, "production.capacity_mwp", 5.0)
    assert out2["production"]["capacity_mwp"] == 5.0
```

- [ ] **Step 2 — Run, verify FAIL** (ImportError):
`PYTHONPATH=src .venv/bin/pytest tests/web/test_introspect.py -v`

- [ ] **Step 3 — Implement:**
```python
from __future__ import annotations

import copy
import re
from typing import Any


def _leaf(path: str, value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        t = "bool"
    elif isinstance(value, (int, float)):
        t = "number"
    else:
        t = "text"
    return {
        "path": path,
        "value": value,
        "type": t,
        "section": path.split(".")[0].split("[")[0],
        "label": path.split(".")[-1].split("[")[0].replace("_", " "),
    }


def schema_tree(config: dict[str, Any], _path: str = "") -> list[dict[str, Any]]:
    """Flatten a model config dict into editable input leaves with dotted/
    indexed paths and inferred types. Lists of dicts → indexed paths; scalar
    leaves carry value+type+section."""
    leaves: list[dict[str, Any]] = []
    for key, val in config.items():
        path = f"{_path}.{key}" if _path else key
        if isinstance(val, dict):
            leaves.extend(schema_tree(val, path))
        elif isinstance(val, list):
            for i, item in enumerate(val):
                ip = f"{path}[{i}]"
                if isinstance(item, dict):
                    leaves.extend(schema_tree(item, ip))
                elif not isinstance(item, (dict, list)):
                    leaves.append(_leaf(ip, item))
        elif val is not None:
            leaves.append(_leaf(path, val))
    return leaves


def set_by_path(config: dict[str, Any], path: str, value: Any) -> dict[str, Any]:
    """Return a deep copy of config with `value` set at the dotted/indexed
    path (e.g. 'financing.senior.interest_rate' or 'revenue[0].price')."""
    out = copy.deepcopy(config)
    keys: list[Any] = []
    for name, idx in re.findall(r"(\w+)|\[(\d+)\]", path):
        keys.append(name if name else int(idx))
    node: Any = out
    for k in keys[:-1]:
        node = node[k]
    node[keys[-1]] = value
    return out
```

- [ ] **Step 4 — Run, verify PASS.** `tests/web -q` green. ruff+mypy clean.
- [ ] **Step 5 — Commit:**
```bash
git add src/asset_finance_modeler/web_api/introspect.py tests/web/test_introspect.py
git commit -m "feat(web_api): introspect (schema_tree + set_by_path) para inputs genericos"
```

### Task A2: Rutas genéricas `/api/models/*` (`web_api/models.py`)

**Files:** Create `src/asset_finance_modeler/web_api/models.py`. Modify `mcp_server/http_server.py` (include_router). Test `tests/web/test_models_api.py`.

**VERIFY FIRST:** los nombres reales de los presets (`ls src/asset_finance_modeler/assets/infrastructure/presets/`), la firma de `load_preset`, y las claves reales de `FinancialOutput.pnl` (`revenue, cogs, gross_profit, opex, ebitda, depreciation, ebit, interest_expense, ebt, tax, net_income`) y `.cashflow` (`cfo, cfi, cff`). El `meta.horizon.frequency` da ppy (M=12, Q=4, Y=1).

- [ ] **Step 1 — Failing test:**
```python
import os
from fastapi.testclient import TestClient


def _client(monkeypatch):
    monkeypatch.setenv("SIM_TOKEN", "tk")
    monkeypatch.setenv("SIM_ONLY", "1")
    from asset_finance_modeler.mcp_server.http_server import app
    return TestClient(app)


def test_list_models(monkeypatch):
    c = _client(monkeypatch)
    r = c.get("/api/models?t=tk")
    ids = {m["id"] for m in r.json()["models"]}
    assert {"bess_20mw_4h", "solar_pv_50mw_spain", "hybrid_consolidated"} <= ids


def test_model_schema(monkeypatch):
    c = _client(monkeypatch)
    r = c.get("/api/models/bess_20mw_4h/schema?t=tk")
    leaves = r.json()["inputs"]
    sections = {l["section"] for l in leaves}
    assert "production" in sections and "financing" in sections
    assert any(l["path"] == "production.power_mw" for l in leaves)


def test_model_run_with_override_and_statements(monkeypatch):
    c = _client(monkeypatch)
    base = c.post("/api/models/bess_20mw_4h/run?t=tk", json={"overrides": {}}).json()
    assert "income_statement" in base and "cash_flow" in base and "kpis" in base
    assert len(base["income_statement"]["years"]) >= 1
    up = c.post("/api/models/bess_20mw_4h/run?t=tk",
                json={"overrides": {"production.power_mw": 40}}).json()
    # doblar potencia cambia el revenue del año 1
    assert up["income_statement"]["rows"]["revenue"][0] != base["income_statement"]["rows"]["revenue"][0]
```

- [ ] **Step 2 — Run, verify FAIL.**
- [ ] **Step 3 — Implement** `web_api/models.py`:
```python
from __future__ import annotations
from pathlib import Path
from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from asset_finance_modeler.assets.infrastructure.loader import load_preset
from asset_finance_modeler.assets.infrastructure.model import InfrastructureModel
from asset_finance_modeler.assets.infrastructure.schema import InfrastructureModelConfig
from asset_finance_modeler.web_api.auth import require_token
from asset_finance_modeler.web_api.introspect import schema_tree, set_by_path

_PRESETS_DIR = Path(InfrastructureModelConfig.__module__ and __file__).resolve()  # placeholder; use loader dir
_PPY = {"M": 12, "Q": 4, "Y": 1}
router = APIRouter(prefix="/api/models", dependencies=[Depends(require_token)])


def _preset_ids() -> list[str]:
    d = Path(load_preset.__globals__["__file__"]).resolve().parent / "presets"  # VERIFY: derive presets dir robustly
    return sorted(p.stem for p in d.glob("*.yaml"))


def _annual(series: list[float], ppy: int) -> list[float]:
    return [sum(series[y * ppy:(y + 1) * ppy]) for y in range(len(series) // ppy)]


def _run_config(cfg_dict: dict[str, Any]) -> dict[str, Any]:
    cfg = InfrastructureModelConfig.model_validate(cfg_dict)
    out = InfrastructureModel(cfg).run()
    ppy = _PPY.get(cfg_dict.get("meta", {}).get("horizon", {}).get("frequency", "M"), 12)
    pnl = out.pnl
    years = list(range(1, len(_annual(pnl["revenue"], ppy)) + 1))
    rows = {k: [round(x) for x in _annual(pnl[k], ppy)]
            for k in ("revenue", "ebitda", "ebit", "interest_expense", "ebt", "tax", "net_income") if k in pnl}
    cf = {k: [round(x) for x in _annual(out.cashflow[k], ppy)] for k in ("cfo", "cfi", "cff") if k in out.cashflow}
    k = out.project_kpis
    kpis = {"npv": round(getattr(k, "npv", 0)), "irr_project": round(getattr(k, "irr_project", 0), 4),
            "irr_equity": round(getattr(k, "irr_equity", 0), 4), "dscr_min": round(getattr(k, "dscr_min", 0), 2),
            "total_capex": round(out.summary.get("total_capex", 0))}
    return {"kpis": kpis, "income_statement": {"years": years, "rows": rows},
            "cash_flow": {"years": years, **cf}, "summary": dict(out.summary)}


class RunBody(BaseModel):
    overrides: dict[str, Any] = {}


@router.get("")
def list_models() -> dict[str, Any]:
    models = [{"id": pid, "name": pid.replace("_", " ").title(), "asset_type": pid.split("_")[0]} for pid in _preset_ids()]
    models.append({"id": "hybrid_consolidated", "name": "hybrid consolidated 1&2 — FV + BESS (Hibrido)", "asset_type": "hybrid"})
    return {"models": models}


@router.get("/{model_id}/schema")
def model_schema(model_id: str) -> dict[str, Any]:
    if model_id == "hybrid_consolidated":
        from asset_finance_modeler.deals.hybrid_consolidated import hybrid_consolidated_input_spec
        return {"inputs": [{"path": s["key"], "value": s["default"], "type": "number",
                            "section": "deal", "label": s["label"]} for s in hybrid_consolidated_input_spec()]}
    try:
        cfg = load_preset(model_id).model_dump()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(404, f"unknown model: {model_id}") from exc
    return {"inputs": schema_tree(cfg)}


@router.post("/{model_id}/run")
def model_run(model_id: str, body: RunBody) -> dict[str, Any]:
    if model_id == "hybrid_consolidated":
        from asset_finance_modeler.deals.hybrid_consolidated import run_hybrid_consolidated
        return run_hybrid_consolidated(body.overrides)
    try:
        cfg = load_preset(model_id).model_dump()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(404, f"unknown model: {model_id}") from exc
    for path, value in body.overrides.items():
        cfg = set_by_path(cfg, path, value)
    return _run_config(cfg)
```
NOTE: the presets-dir derivation above is illustrative — VERIFY the robust way (e.g. `from asset_finance_modeler.assets.infrastructure import presets as _p; Path(_p.__file__).parent`) and fix. In `http_server.py` add `from asset_finance_modeler.web_api.models import router as models_router; app.include_router(models_router)` (before the static mount).

- [ ] **Step 4 — Run, verify PASS.** Regression `tests/web tests/core tests/unit -q`. ruff+mypy clean.
- [ ] **Step 5 — Commit:**
```bash
git add src/asset_finance_modeler/web_api/models.py src/asset_finance_modeler/mcp_server/http_server.py tests/web/test_models_api.py
git commit -m "feat(web_api): rutas genericas /api/models (lista+schema+run con PyG/FCF)"
```

### Task A3: Persistencia `/api/assets/*` (`web_api/assets.py`)

**Files:** Create `src/asset_finance_modeler/web_api/assets.py`. Modify `http_server.py` (include_router). Test `tests/web/test_assets_api.py`.

**VERIFY FIRST:** el constructor de `Scenario` (ver `mcp_server/tools/crud.py` para los args exactos: id, name, base_model, inputs_snapshot, results_snapshot, created_at, tags, user_id…) y `SQLiteScenarioStore(db_path)` + `initialize/save/get/list/delete`. Para el id usar `uuid4().hex`; para created_at pasar `datetime.now(UTC)` (o el patrón que use crud.py). DB path desde `ASSET_FINANCE_DB_PATH` env o un temp; en test usar `tmp_path`.

- [ ] **Step 1 — Failing test:**
```python
def test_assets_crud(monkeypatch, tmp_path):
    monkeypatch.setenv("SIM_TOKEN", "tk")
    monkeypatch.setenv("SIM_ONLY", "1")
    monkeypatch.setenv("ASSET_FINANCE_DB_PATH", str(tmp_path))
    from asset_finance_modeler.mcp_server.http_server import app
    from fastapi.testclient import TestClient
    c = TestClient(app)
    created = c.post("/api/assets?t=tk", json={"model_id": "bess_20mw_4h", "name": "Mi BESS", "overrides": {}}).json()
    aid = created["id"]
    lst = c.get("/api/assets?t=tk").json()["assets"]
    assert any(a["id"] == aid and a["name"] == "Mi BESS" for a in lst)
    got = c.get(f"/api/assets/{aid}?t=tk").json()
    assert got["model_id"] == "bess_20mw_4h" and "results_snapshot" in got
    c.delete(f"/api/assets/{aid}?t=tk")
    assert all(a["id"] != aid for a in c.get("/api/assets?t=tk").json()["assets"])
```

- [ ] **Step 2 — Run, verify FAIL.**
- [ ] **Step 3 — Implement** `web_api/assets.py` (use the Scenario+SQLiteScenarioStore API confirmed; POST runs the model via `models._run_config`/`run_hybrid_consolidated` to capture results_snapshot, then saves a Scenario; GET list maps to `{id,name,model_id,created_at,kpis}`; GET {id} returns model_id+overrides+results_snapshot+created_at; DELETE). Router `/api/assets` with `Depends(require_token)`. Store path from `ASSET_FINANCE_DB_PATH`.
- [ ] **Step 4 — Run, verify PASS.** Regression completa. ruff+mypy clean.
- [ ] **Step 5 — Commit:**
```bash
git add src/asset_finance_modeler/web_api/assets.py src/asset_finance_modeler/mcp_server/http_server.py tests/web/test_assets_api.py
git commit -m "feat(web_api): persistencia /api/assets (guardar/listar/revisar/borrar) sobre ScenarioStore"
```

---

## FASE B — Frontend multi-activo (IB-grade, sin emojis)

### Task B1: API client genérico + panel de activos
**Files:** `web/src/api.ts` (extender), `web/src/components/AssetPanel.tsx`, `web/src/App.tsx`.
- [ ] Extender `api.ts`: `listModels()`, `getSchema(id)`, `runGeneric(id, overrides)`, `listAssets()`, `saveAsset(payload)`, `getAsset(id)`, `deleteAsset(id)`. 
- [ ] `AssetPanel` (izquierda): dos grupos — **"Mi cartera"** (`listAssets()`, con fecha + KPI resumen, click = revisar) y **"Nuevo desde modelo"** (`listModels()` agrupado por asset_type, click = cargar schema). Estado: `selected = {kind:'asset'|'model', id}`.
- [ ] Build OK. Commit.

### Task B2: Editor dinámico de inputs por secciones
**Files:** `web/src/components/DynamicInputs.tsx`.
- [ ] Del `getSchema(id)` → agrupar leaves por `section`, render secciones plegables; cada leaf: input number/text/toggle según `type`, con label. onChange → actualiza `overrides[path]` → dispara `runGeneric` (debounce). Test: render con schema mock muestra las secciones y un cambio llama el callback con el path.
- [ ] Build OK. Commit.

### Task B3: Salida financiera (KPIs + Cuenta de resultados + FCF + curvas)
**Files:** `web/src/components/Statements.tsx`, `web/src/components/Charts.tsx` (reusar/ampliar).
- [ ] KPI cards (genéricas, del `kpis`). **Tabla Cuenta de resultados** (filas: revenue, ebitda, ebit, interest, ebt, tax, net_income × años). **Tabla/gráfico FCF** (cfo/cfi/cff). Curvas si el modelo las trae. Test: render con datos mock.
- [ ] Build OK. Commit.

### Task B4: Guardar/Revisar + restyle grado banco de inversión
**Files:** `web/src/components/Toolbar.tsx`, `web/src/App.tsx`, `web/src/index.css`.
- [ ] Botón **Guardar** (`saveAsset({model_id, name, overrides})` → aparece en "Mi cartera"). Click en un guardado → `getAsset(id)` carga sus overrides+resultados (revisar la simulación con su fecha). 
- [ ] **Restyle IB:** quitar TODO emoji, paleta sobria (gris/azul marino + un acento), tipografía clara, tablas densas legibles, cabecera "Gestnova · Plataforma de Valoración de Activos". Layout: AssetPanel izq · centro DynamicInputs · derecha Statements+Charts (o pestañas).
- [ ] `npm run build` OK (dist). Commit.

---

## Self-Review
- **Spec coverage:** introspección todos-los-inputs (A1), lista/schema/run genérico con PyG+FCF (A2), persistencia guardar/listar/revisar/borrar (A3), frontend cartera+presets+editor dinámico+estados financieros+guardar/revisar+IB-restyle (B1-B4). ✅
- **Placeholders:** A1 código completo. A2/A3 con verify-first para la derivación del dir de presets y la API exacta de Scenario (patrón usado en fases previas con éxito). Frontend con contratos concretos.
- **Type consistency:** `schema_tree`/`set_by_path`/`_run_config` (kpis,income_statement{years,rows},cash_flow), `/api/models`,`/api/assets`, contrato JSON coherente backend↔`api.ts`. hybrid consolidated v1 intacto.
- **No rompe:** todo aditivo; `deals/hybrid_consolidated.py` y `/api/hybrid_consolidated/*` se mantienen; regresión en cada task.

## Notas trozos siguientes: activo nuevo de tipo arbitrario · multi-tenant/permisos workspace · migración webOS (iframe-kernel-bridge → `/api/models`+`/api/assets`).
