# Simulador / Centro de Operaciones Financiero — Plan de implementación (v1 SVJ)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Dashboard web interactivo del deal SVJ sobre el motor `asset-finance-modeler`, desplegado con link público (torre + Cloudflare Tunnel), con recálculo en vivo y descarga Excel-foto.

**Architecture:** Backend = FastAPI del motor extendida con un router `/api/svj/*` que usa un módulo `deals/svj.py` (fuente de verdad: construye FV+BESS, corre `HybridProject`, devuelve KPIs+series). Frontend = SPA React+Vite+Tailwind+recharts en `web/` que llama esa API y recalcula en vivo. Un contenedor Docker (FastAPI sirve la SPA estática + la API) tras Cloudflare Tunnel con token.

**Tech Stack:** Python/FastAPI/pytest (backend), React 19 + Vite + Tailwind v4 + @tanstack/react-query + recharts + TypeScript (frontend), Docker + Cloudflare Tunnel (deploy).

**Repo/rama:** `/Users/rikyizquierdo/Documents/New project/asset-finance-modeler`, rama `feat/finance-engine-general-deals`. No romper los 556 tests existentes.

## File Structure
- `src/asset_finance_modeler/deals/__init__.py`, `deals/svj.py` — **Create**: lógica del deal (build+run+export) y spec de inputs. ÚNICA fuente de verdad del deal.
- `src/asset_finance_modeler/web_api/__init__.py`, `web_api/routes.py`, `web_api/auth.py` — **Create**: router `/api/svj/*`, dependencia de token, montaje estático.
- `src/asset_finance_modeler/mcp_server/http_server.py` — **Modify**: incluir el router web + montar estático.
- `tests/web/test_svj_deal.py`, `tests/web/test_api.py` — **Create**: tests backend.
- `web/` — **Create**: SPA (package.json, vite, src/api.ts, src/App.tsx, src/components/*, src/hooks/useRun.ts).
- `Dockerfile`, `web/README.md` — **Create/Modify**: deploy.

---

## FASE A — Backend (API del deal)

### Task A1: Módulo del deal `deals/svj.py`

**Files:** Create `src/asset_finance_modeler/deals/__init__.py` (vacío), `src/asset_finance_modeler/deals/svj.py`. Test `tests/web/test_svj_deal.py` (+ `tests/web/__init__.py`).

- [ ] **Step 1: Failing test**
```python
# tests/web/test_svj_deal.py
from asset_finance_modeler.deals.svj import run_svj, svj_input_spec


def test_svj_input_spec_has_key_drivers():
    keys = {i["key"] for i in svj_input_spec()}
    assert {"spread_capture", "ancillary_base", "bess_capex_eur_kwh", "sub_tenor_years", "sub_rate"} <= keys


def test_run_svj_reproduces_validated_kpis():
    r = run_svj({})  # defaults = deal calibrado
    k = r["kpis"]
    assert 0.8e6 < k["npv_hybrid"] < 1.3e6        # ~1.032M conservador
    assert 1.25 < k["moic_sub"] < 1.45            # ~1.37
    assert k["npv_fv"] < 0 < k["npv_bess"]        # FV marginal, BESS positivo
    assert len(r["cashflows"]["years"]) == 30
    assert len(r["curves"]["spread"]) == 30
    assert "bridge" in r and "dscr_profile" in r


def test_run_svj_overrides_move_kpis():
    base = run_svj({})["kpis"]["npv_hybrid"]
    up = run_svj({"spread_capture": 0.95})["kpis"]["npv_hybrid"]  # más captura → más NPV
    assert up > base
```

- [ ] **Step 2: Run, verify FAIL** (ModuleNotFoundError deals.svj):
`PYTHONPATH=src .venv/bin/pytest tests/web/test_svj_deal.py -v`

- [ ] **Step 3: Implement `deals/svj.py`** — usa los presets calibrados + `HybridProject`. Estructura:
```python
from __future__ import annotations
from typing import Any
from asset_finance_modeler.assets.infrastructure.loader import load_preset
from asset_finance_modeler.assets.infrastructure.model import InfrastructureModel
from asset_finance_modeler.assets.infrastructure.schema import InfrastructureModelConfig
from asset_finance_modeler.assets.hybrid.model import HybridProject, TrancheSpec
from asset_finance_modeler.core.portfolio import consolidate_npv

WACC = 0.0537
PPY = 12

def svj_input_spec() -> list[dict[str, Any]]:
    return [
        {"key": "spread_capture", "label": "Captura de spread BESS", "unit": "x", "default": 0.80, "min": 0.5, "max": 1.0},
        {"key": "ancillary_base", "label": "Ancillary aFRR año 1", "unit": "€/MW", "default": 74000, "min": 30000, "max": 100000},
        {"key": "bess_capex_eur_kwh", "label": "CAPEX BESS", "unit": "€/kWh", "default": 130.6, "min": 90, "max": 200},
        {"key": "sub_tenor_years", "label": "Plazo deuda inversor", "unit": "años", "default": 7, "min": 5, "max": 12},
        {"key": "sub_rate", "label": "Tipo deuda inversor", "unit": "%", "default": 0.085, "min": 0.05, "max": 0.12},
        {"key": "fv_ppa_price", "label": "PPA FV", "unit": "€/MWh", "default": 43, "min": 30, "max": 60},
    ]

def _annual(series: list[float]) -> list[float]:
    return [sum(series[y*PPY:(y+1)*PPY]) for y in range(len(series)//PPY)]

def _apply_overrides(fv: dict, bess: dict, ov: dict[str, Any]) -> None:
    if "fv_ppa_price" in ov:
        for s in fv["revenue"]:
            if s.get("type") == "ppa": s["price_eur_per_unit"] = float(ov["fv_ppa_price"])
    for s in bess["revenue"]:
        if s.get("type") == "arbitrage" and "spread_capture" in ov:
            s["spread_capture_ratio"] = float(ov["spread_capture"])
        if s.get("type") == "ancillary" and "ancillary_base" in ov:
            s["afrr_eur_mw_yr"] = float(ov["ancillary_base"])
    if "bess_capex_eur_kwh" in ov:
        for it in bess["capex"]["items"]:
            if it.get("unit") == "kWh": it["amount_per_unit"] = float(ov["bess_capex_eur_kwh"])

def _npv_unlevered(cfgdict: dict) -> float:
    d = dict(cfgdict); d["financing"] = {"max_leverage": 0.0}
    out = InfrastructureModel(InfrastructureModelConfig.model_validate(d)).run()
    fcf = [_annual(out.cashflow["cfo"])[i] + _annual(out.cashflow["cfi"])[i] for i in range(len(_annual(out.cashflow["cfo"])))]
    return consolidate_npv(fcf, WACC)

def run_svj(overrides: dict[str, Any]) -> dict[str, Any]:
    fv = load_preset("svj_fv_cordoba").model_dump()
    bess = load_preset("svj_bess_cordoba").model_dump()
    _apply_overrides(fv, bess, overrides)
    fv_cfg = InfrastructureModelConfig.model_validate(fv)
    bess_cfg = InfrastructureModelConfig.model_validate(bess)
    npv_fv = _npv_unlevered(fv); npv_bess = _npv_unlevered(bess)
    sub_tenor = int(overrides.get("sub_tenor_years", 7)); sub_rate = float(overrides.get("sub_rate", 0.085))
    hp = HybridProject([fv_cfg, bess_cfg], WACC,
                       senior=TrancheSpec(2_220_000, 0.032, 10),
                       subordinated=TrancheSpec(1_841_000, sub_rate, sub_tenor)).run()
    fv_out = InfrastructureModel(fv_cfg).run(); bess_out = InfrastructureModel(bess_cfg).run()
    years = list(range(1, len(_annual(bess_out.pnl["revenue"])) + 1))
    return {
        "kpis": {
            "npv_fv": round(npv_fv), "npv_bess": round(npv_bess), "npv_hybrid": round(npv_fv + npv_bess),
            "dscr_sub_min": round(hp.dscr_subordinated_min, 2), "dscr_sub_avg": round(hp.dscr_subordinated_avg, 2),
            "dscr_senior_min": round(hp.dscr_senior_min, 2),
            "moic_sub": round(hp.moic_subordinated, 2), "recovery": round(hp.recovery_going_concern, 2),
        },
        "cashflows": {"years": years,
                      "fv": [round(x) for x in _annual(fv_out.pnl["ebitda"])],
                      "bess": [round(x) for x in _annual(bess_out.pnl["ebitda"])]},
        "curves": {"spread": [], "ancillary": []},  # rellenar desde la curva del BESS (ver abajo)
        "bridge": {"fv": round(npv_fv), "bess": round(npv_bess), "hybrid": round(npv_fv + npv_bess)},
        "dscr_profile": [round(x, 2) for x in (hp.consolidated_ebitda or [])][:sub_tenor],
    }
```
Para `curves`: extraer la curva de spread y ancillary del BESS (cargar `Curve.from_library("spread_da_es").to_list(30)` y la curva ancillary). Implementar de forma que los tests pasen; ajustar nombres reales (`hp.consolidated_ebitda` puede ser None → usar `[]`).

- [ ] **Step 4: Run, verify PASS.** `tests/web -q` verde. ruff+mypy clean en `deals/svj.py`.
- [ ] **Step 5: Commit** `git add src/asset_finance_modeler/deals tests/web/test_svj_deal.py tests/web/__init__.py && git commit -m "feat(deals): modulo svj (run+input spec) fuente de verdad del deal"`

### Task A2: Auth por token

**Files:** Create `src/asset_finance_modeler/web_api/__init__.py`, `web_api/auth.py`. Test in `tests/web/test_api.py`.

- [ ] **Step 1: Failing test**
```python
# tests/web/test_api.py
import os
from fastapi.testclient import TestClient


def _client(monkeypatch):
    monkeypatch.setenv("SIM_TOKEN", "secret123")
    from asset_finance_modeler.mcp_server.http_server import app
    return TestClient(app)


def test_run_requires_token(monkeypatch):
    c = _client(monkeypatch)
    assert c.post("/api/svj/run", json={"overrides": {}}).status_code == 401
    ok = c.post("/api/svj/run?t=secret123", json={"overrides": {}})
    assert ok.status_code == 200
    assert "kpis" in ok.json()
```

- [ ] **Step 2: Run, verify FAIL** (404/no route).
- [ ] **Step 3: Implement** `web_api/auth.py`:
```python
from __future__ import annotations
import os
from fastapi import HTTPException, Request

def require_token(request: Request) -> None:
    expected = os.getenv("SIM_TOKEN")
    if not expected:
        return  # sin token configurado → abierto (dev local)
    supplied = request.query_params.get("t") or request.headers.get("x-sim-token")
    if supplied != expected:
        raise HTTPException(status_code=401, detail="invalid or missing token")
```

- [ ] **Step 4: (continúa en A3 con las rutas) — ejecutar tras A3.**
- [ ] **Step 5: Commit junto con A3.**

### Task A3: Router `/api/svj/*` + montaje estático

**Files:** Create `web_api/routes.py`. Modify `mcp_server/http_server.py`. Test `tests/web/test_api.py`.

- [ ] **Step 1: Failing tests** (añadir):
```python
def test_model_endpoint(monkeypatch):
    c = _client(monkeypatch)
    r = c.get("/api/svj/model?t=secret123")
    assert r.status_code == 200 and isinstance(r.json()["inputs"], list)

def test_export_returns_xlsx(monkeypatch):
    c = _client(monkeypatch)
    r = c.post("/api/svj/export?t=secret123", json={"overrides": {}})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/")
    assert len(r.content) > 1000
```

- [ ] **Step 2: Run, verify FAIL.**
- [ ] **Step 3: Implement** `web_api/routes.py`:
```python
from __future__ import annotations
import io
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from asset_finance_modeler.deals.svj import run_svj, svj_input_spec, build_svj_xlsx
from asset_finance_modeler.web_api.auth import require_token

router = APIRouter(prefix="/api/svj", dependencies=[Depends(require_token)])

class RunBody(BaseModel):
    overrides: dict = {}

@router.get("/model")
def model() -> dict:
    return {"inputs": svj_input_spec(), "name": "SVJ 1&2 — FV + BESS (Córdoba)"}

@router.post("/run")
def run(body: RunBody) -> dict:
    return run_svj(body.overrides)

@router.post("/export")
def export(body: RunBody) -> StreamingResponse:
    data = build_svj_xlsx(body.overrides)  # bytes
    return StreamingResponse(io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=SVJ_simulacion.xlsx"})
```
Add `build_svj_xlsx(overrides)->bytes` to `deals/svj.py` (run the model, write via `store.exports.to_xlsx` to a temp path or BytesIO, return bytes). In `http_server.py`: `from asset_finance_modeler.web_api.routes import router as svj_router; app.include_router(svj_router)`. Add static mount AFTER routes: if `web/dist` exists, `app.mount("/", StaticFiles(directory=..., html=True), name="spa")`.

- [ ] **Step 4: Run, verify PASS** (`tests/web -q`). Full regression `tests/core tests/unit tests/golden tests/web -q` (no rompe los 556). ruff+mypy clean.
- [ ] **Step 5: Commit** `git add src/asset_finance_modeler/web_api src/asset_finance_modeler/mcp_server/http_server.py src/asset_finance_modeler/deals/svj.py tests/web/test_api.py && git commit -m "feat(web_api): router /api/svj (model/run/export) + token + static mount"`

---

## FASE B — Frontend (`web/` SPA React)

### Task B1: Scaffold + cliente API
**Files:** Create `web/package.json`, `web/vite.config.ts`, `web/tsconfig.json`, `web/index.html`, `web/tailwind.config.*`, `web/src/main.tsx`, `web/src/api.ts`.
- [ ] **Step 1:** `cd web && npm create vite@latest . -- --template react-ts` (o crear manual). Instalar: `react@19 react-dom@19 @tanstack/react-query recharts tailwindcss@4 @tailwindcss/vite clsx`.
- [ ] **Step 2:** `web/src/api.ts`:
```ts
const BASE = import.meta.env.VITE_API_BASE ?? "";
const token = new URLSearchParams(location.search).get("t") ?? "";
const q = token ? `?t=${token}` : "";
export async function getModel() { return (await fetch(`${BASE}/api/svj/model${q}`)).json(); }
export async function runModel(overrides: Record<string, number>) {
  return (await fetch(`${BASE}/api/svj/run${q}`, {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({overrides})})).json();
}
export function exportUrl() { return `${BASE}/api/svj/export${q}`; }
```
- [ ] **Step 3:** verificar `npm run build` genera `web/dist`. **Commit** `web/` scaffold.

### Task B2: Hook de recálculo en vivo + tarjetas KPI
**Files:** `web/src/hooks/useRun.ts`, `web/src/components/KpiCards.tsx`, `web/src/App.tsx`.
- [ ] `useRun(overrides)`: react-query `useQuery` con key=overrides, debounce 300ms (estado local + useEffect), llama `runModel`. Devuelve `{data, isFetching}`.
- [ ] `KpiCards`: tarjetas NPV FV/BESS/híbrido, DSCR sub avg/min, MOIC, recovery, IRR con formato €/x y color. Test (Testing Library): renderiza con datos mock y muestra "1.37x".
- [ ] Build OK. **Commit.**

### Task B3: Panel de inputs
**Files:** `web/src/components/InputsPanel.tsx`.
- [ ] Lee `getModel().inputs`, renderiza slider+número por input (label+unidad), `onChange` actualiza el estado de overrides (que dispara `useRun`). Test: cambiar un input llama el callback con el override correcto.
- [ ] Build OK. **Commit.**

### Task B4: Gráficos (recharts)
**Files:** `web/src/components/Charts.tsx` (Cashflows barras, Curves líneas spread+ancillary, Bridge, DscrProfile).
- [ ] 4 componentes recharts alimentados por `data.cashflows/curves/bridge/dscr_profile`. Test: renderiza sin crash con datos mock.
- [ ] Build OK. **Commit.**

### Task B5: Descarga Excel + escenarios + layout final
**Files:** `web/src/components/Toolbar.tsx`, `web/src/App.tsx`.
- [ ] Botón "Descargar Excel" → `window.location = exportUrl()` (con overrides actuales como query/post — usar un form POST o pasar overrides por query si pequeños; v1: POST vía fetch→blob→download). Guardar/cargar escenarios en localStorage (nombre→overrides). Layout: header (nombre deal), izquierda InputsPanel, derecha KpiCards+Charts. `?embed=1` oculta header. 
- [ ] Build OK. **Commit.**

---

## FASE C — Deploy (torre + Cloudflare Tunnel)

### Task C1: Dockerfile multi-stage + README
**Files:** `Dockerfile`, `web/README.md`.
- [ ] `Dockerfile`: stage1 node → `cd web && npm ci && npm run build`; stage2 python → instalar el paquete (`pip install .`), copiar `web/dist`, `CMD asset-finance-modeler-http` (PORT=8015, sirve `/api` + estático). 
- [ ] `web/README.md`: `docker build -t gestnova-sim . && docker run -e SIM_TOKEN=… -e PORT=8015 -p 8015:8015 gestnova-sim`; config Cloudflare Tunnel (`cloudflared tunnel ... → sim.gestnova.eu:8015`); el link al inversor = `https://sim.gestnova.eu/?t=<token>`.
- [ ] **Verify:** build local del contenedor, `curl /health`, `curl "/api/svj/run?t=…"`. **Commit.**

---

## Self-Review
- **Spec coverage:** API (A1-A3 = /model,/run,/export+token+static), deal source-of-truth (A1 deals/svj.py), frontend (B1-B5 = inputs/KPIs/charts/recalc/export/embed), deploy (C1 = Docker+Tunnel+token). ✅
- **Placeholders:** el código backend está completo; `curves` y `build_svj_xlsx` marcados como "implementar contra estructura real" (verify-and-implement, como en fases anteriores). Frontend con código concreto de cliente/hook; componentes React descritos con su contrato (testing React más ligero por naturaleza).
- **Type consistency:** `run_svj`/`svj_input_spec`/`build_svj_xlsx`, claves de inputs (`spread_capture`, `ancillary_base`, `bess_capex_eur_kwh`, `sub_tenor_years`, `sub_rate`, `fv_ppa_price`), JSON `{kpis,cashflows,curves,bridge,dscr_profile}` coherentes entre backend y frontend (`api.ts`).
- **No rompe lo existente:** todo aditivo (nuevos módulos/rutas); regresión completa en A3 Step 4.

## Notas migración webOS (no aquí): la SPA con `VITE_API_BASE` + `?embed=1` se incrusta como app webOS (iframe-kernel-bridge); generalizar `/api/svj/*`→`/api/model/{id}/*` = v2.
