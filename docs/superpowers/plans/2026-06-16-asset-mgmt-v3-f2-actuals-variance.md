# F2 — Captura de datos reales + varianza (seguimiento día a día) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. TDD por fix. Pasos con checkbox `- [ ]`.

**Goal:** Que un activo EN OPERACIÓN pueda recibir **datos reales** (producción, revenue, costes, deuda… cualquier línea de su propio modelo) por periodo, y ver la **desviación frente al caso base** (real vs proyectado, acumulado, % cumplimiento). Sin reproyectar la valoración todavía (eso es F3).

**Architecture:** Tabla nueva `asset_actuals` + `SQLiteActualsStore` (en `store/actuals.py`), router `web_api/actuals.py` (`POST/GET/DELETE /api/assets/{id}/actuals`, `GET /api/assets/{id}/lines`, `GET /api/assets/{id}/variance`), y frontend (cliente + rejilla de entrada + vista de varianza en el detalle del activo). Construye sobre F1 (Scenario con lifecycle/commissioning_date) y la spec `docs/superpowers/specs/2026-06-15-asset-management-platform-v3-design.md` §3.2/§5.

**Tech Stack:** Python 3.12 · FastAPI · SQLite · pytest · React 19 + Vite + Tailwind + react-query + recharts. Interpreter `.venv/bin/python`. Regresión: el comando del plan `2026-06-16-engine-remediation-all-assets.md` (NUNCA pytest pelado). Firmar commits `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

**Reglas:** TDD backend. No romper los 347 tests ni F1/v2/v1. SIN EMOJIS, iconos lucide, grado fondo.

---

## Task F2-1: Tabla `asset_actuals` + `SQLiteActualsStore`
**Files:** Create `src/asset_finance_modeler/store/actuals.py`; Test `tests/web/test_actuals_store.py`.
- [ ] **Test primero:** crear store, guardar varios `Actual(scenario_id, period_start, line_path, value, unit, note, entered_by, entered_at)`, listarlos filtrando por `scenario_id`/`line_path`/rango de fechas, borrar uno por id. Verlo fallar.
- [ ] **Implementar:** dataclass/Pydantic `Actual` + `SQLiteActualsStore(db_path)` con `initialize()` (CREATE TABLE IF NOT EXISTS), `add(actual)->id`, `add_batch(list)`, `list(scenario_id, line_path=None, since=None, until=None)`, `delete(id)`. Esquema:
```sql
CREATE TABLE IF NOT EXISTS asset_actuals (
  id TEXT PRIMARY KEY, scenario_id TEXT NOT NULL, period_start TEXT NOT NULL,
  line_path TEXT NOT NULL, value REAL NOT NULL, unit TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT '', entered_by TEXT NOT NULL DEFAULT 'default', entered_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_actuals_scn ON asset_actuals(scenario_id, line_path, period_start);
```
Id estilo `act-<hex>` (reusar patrón de `new_scenario_id`). Usa la MISMA DB que scenarios (mismo `_db_path()` de `web_api/assets.py`).
- [ ] Test verde. Commit `feat(store): tabla asset_actuals + SQLiteActualsStore (serie temporal de datos reales)`.

## Task F2-2: Endpoints de actuals + líneas trackeables
**Files:** Create `src/asset_finance_modeler/web_api/actuals.py`; Modify `mcp_server/http_server.py` (include router); Test `tests/web/test_actuals_api.py`.
- [ ] **Test primero (TestClient, patrón de `tests/web/test_lifecycle_api.py`):** crear un activo, promoverlo a operational, `GET /api/assets/{id}/lines` devuelve líneas trackeables no vacías; `POST /api/assets/{id}/actuals` (un actual y un lote) → 200; `GET /api/assets/{id}/actuals` los lista; `DELETE /api/assets/{id}/actuals/{actual_id}` lo borra; sin token → 401; activo inexistente → 404. Verlo fallar.
- [ ] **Implementar `web_api/actuals.py`** (router `prefix="/api/assets"`, `dependencies=[Depends(require_token)]`, reusar `_store()`/`_db_path()` de assets.py o factorizarlos):
  - `GET /{asset_id}/lines` → líneas del modelo del activo que se pueden trackear. Derivar del `results_snapshot` del Scenario: las filas de `income_statement.rows` (revenue, ebitda, ebit, interest_expense, ebt, tax, net_income) + `cash_flow` (cfo, cfi, cff); cada línea = `{path, label, unit}`. (Es la lista para elegir qué dato real se mete; suficiente para F2.)
  - `POST /{asset_id}/actuals` body `{actuals:[{period_start, line_path, value, unit?, note?}]}` (acepta uno o lote) → guarda; 404 si el activo no existe.
  - `GET /{asset_id}/actuals?line_path=&since=&until=` → lista.
  - `DELETE /{asset_id}/actuals/{actual_id}`.
- [ ] **Incluir el router** en `mcp_server/http_server.py` (`app.include_router(actuals_router)` antes del mount estático, como los demás).
- [ ] Test verde. Commit `feat(web_api): endpoints de datos reales (/api/assets/{id}/actuals + /lines)`.

## Task F2-3: Endpoint de varianza real-vs-base
**Files:** Modify `src/asset_finance_modeler/web_api/actuals.py`; Test `tests/web/test_variance_api.py`.
- [ ] **Test primero:** activo operational con un `results_snapshot` (income_statement con revenue [r0, r1, ...]); meter actuals de revenue para el año 1; `GET /api/assets/{id}/variance` devuelve por línea: serie base (del snapshot), serie real (actuals agregados por año del modelo), desviación absoluta y %, y acumulado. Verlo fallar.
- [ ] **Implementar `GET /{asset_id}/variance?line_path=`:** para cada línea trackeada (o la pedida), tomar la serie base del `results_snapshot` (anual), agregar los actuals por año del modelo (por `period_start` → índice de año relativo a `commissioning_date` o al inicio), y devolver `{line_path, base:[...], actual:[...], deviation:[...], deviation_pct:[...], cumulative_actual, cumulative_base, fulfillment_pct}`. Años sin dato real → `null` en actual (no se inventan). NO reproyecta la valoración (eso es F3).
- [ ] Test verde. Commit `feat(web_api): varianza real-vs-base por linea (/api/assets/{id}/variance)`.

## Task F2-4: Cliente API frontend
**Files:** Modify `web/src/api.ts`.
- [ ] Tipos `TrackableLine`, `Actual`, `Variance`; funciones `getLines(id)`, `getActuals(id, opts?)`, `postActuals(id, actuals[])`, `deleteActual(id, actualId)`, `getVariance(id, linePath?)`. Mismo patrón `withToken`/`getJson`.
- [ ] `npx tsc -b --noEmit` salvo dependencias de los componentes (Task F2-5/6). Commit `feat(web): cliente API de datos reales + varianza`.

## Task F2-5: Rejilla de entrada de datos reales (detalle del activo operativo)
**Files:** Create `web/src/components/ActualsGrid.tsx`; Modify `web/src/App.tsx` (mostrarla en el detalle solo si el activo es `operational`).
- [ ] Componente: selector de línea (de `getLines`) + frecuencia (del `tracking_frequency` del activo) + rejilla editable por periodo (fecha → valor + unidad + nota) que hace `postActuals` y refresca (`react-query` invalida `["actuals", id]` y `["variance", id]`). Lista los actuals existentes con opción de borrar. SIN EMOJIS, lucide, sobrio.
- [ ] En `App.tsx`, en la vista de detalle, si `selection` es un activo operational, mostrar una pestaña/sección "Datos reales" con `ActualsGrid`.
- [ ] `cd web && npm run build` verde. Commit `feat(web): rejilla de entrada de datos reales en el detalle del activo operativo`.

## Task F2-6: Vista de varianza (real vs base)
**Files:** Create `web/src/components/VariancePanel.tsx`; Modify `web/src/App.tsx`.
- [ ] Componente: por línea, tabla (año · base · real · desviación · % · acumulado · % cumplimiento) + gráfico recharts (línea base vs puntos reales) con la misma paleta sobria. Cues de color sobrios para desviación (sin colores chillones, sin emojis).
- [ ] Mostrarla en el detalle del activo operativo (junto a `ActualsGrid`).
- [ ] `npm run build` verde. Commit `feat(web): panel de varianza real-vs-base en el detalle del activo`.

## Task F2-7: Tests frontend + verificación en vivo
**Files:** Create `web/src/components/ActualsGrid.test.tsx` (o VariancePanel); verificación con server.
- [ ] Test (patrón de `Dashboard.test.tsx`): meter un actual llama a `postActuals` con el path/valor; la varianza renderiza base vs real. `npm test` verde.
- [ ] **Verificación en vivo:** rearrancar server (`HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 SIM_ONLY=1 SIM_WEB_DIST=$(pwd)/web/dist PORT=8015 PYTHONPATH=src .venv/bin/python -m ...`), crear activo, promover a operational, `POST` un actual, `GET /variance` muestra la desviación. Commit del test `test(web): entrada de datos reales + varianza`.

---

## Notas
- F2 NO reproyecta la valoración (base vs live es F3). Aquí: meter reales + ver desviación vs el caso base congelado.
- Tras F2: actualizar `gestnova_finance_engine.md` y planificar F3 (motor LIVE: reproyección base/live).
- El server live 8015 está con código pre-remediación — rearrancar + rebuild dist en la verificación.
