# F3 (motor LIVE: reproyección base-vs-live) + F4 (riqueza visual fondo) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. TDD por fix. Pasos con checkbox `- [ ]`.

**Goal:** F3 — con los datos reales metidos (F2), reproyectar la valoración: mostrar el **caso BASE congelado** junto al **LIVE** (reales en los periodos ya ocurridos + proyección del futuro), con VAN/TIR/DSCR live y desviación. F4 — dejar la plataforma con impacto visual de fondo/banco: mapa de activos por ubicación, dark theme, alertas por desviación, tiles ricos.

**Architecture:** F3 backend = `core/live.py::compute_live(...)` (overlay por agregación: serie base con periodos pasados sustituidos por reales, futuro = base; recalcula KPIs) + `GET /api/assets/{id}/live`. F3 frontend = cards/gráfico BASE vs LIVE en el detalle del activo operativo. F4 = frontend (mapa, dark theme, alertas, tiles). Spec `docs/superpowers/specs/2026-06-15-asset-management-platform-v3-design.md` §3.3/§4.

**Decisión de modelado (de la spec):** overlay por agregación; el motor proyecta anual; los reales se agregan a año; años pasados = reales, años futuros = supuestos base; el motor multi-periodo nativo queda fuera (v4). Documentar las simplificaciones.

**Tech Stack:** Python 3.12 · FastAPI · pytest · React 19 + Vite + Tailwind + react-query + recharts · lucide. Interpreter `.venv/bin/python`. Regresión: comando de `2026-06-16-engine-remediation-all-assets.md` (NUNCA pytest pelado). Baseline 362. Firmar commits `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. SIN EMOJIS.

---

# FASE F3 — Motor LIVE (reproyección base-vs-live)

## Task F3-1: `compute_live` (overlay por agregación)
**Files:** Create `src/asset_finance_modeler/core/live.py`; Test `tests/unit/test_live.py`.
- [ ] **Test primero:** dado un `base` (series anuales: revenue, ebitda, ..., cfo/cfi/cff + un FCF para NPV) + `actuals_by_line_by_year` (p.ej. revenue año1 real) + `elapsed_years=1`, `compute_live(...)` devuelve series LIVE donde el año 1 de las líneas con dato real = el real (y las líneas dependientes re-derivadas para ese año con los ratios del año base), el resto = base; y KPIs LIVE (npv, irr, dscr) recomputados sobre el FCF empalmado. Casos: (a) sin actuals → LIVE == BASE; (b) revenue real por encima del base → npv_live > npv_base; (c) años futuros intactos. Verlo fallar.
- [ ] **Implementar `compute_live(base_output, actuals_by_line_by_year, elapsed_years)`:**
  - Copia las series base. Para cada `year < elapsed_years` y cada línea con real: sustituye el valor base por el real agregado.
  - Re-derivación mínima del P&L para esos años pasados: si se sustituye una línea "alta" (revenue), recomputar gross/ebitda/ebit/ebt/tax/net_income de ese año usando los ratios coste/impuesto del base de ese año; si se sustituye una línea de coste/cfo directamente, ajustarla y propagar a EBITDA/net_income/CFO. Líneas no trackeadas en años pasados = base. Años futuros = base sin tocar.
  - Recomputar el FCF empalmado y los KPIs: `compute_irr`, NPV (misma convención que el base), DSCR (sobre CFADS empalmado). Reusar `core/valuation.py` y `core/financing.py`.
  - Devolver `{base: {series, kpis}, live: {series, kpis}, deviation_summary}`.
  - Documentar inline la simplificación (overlay anual; re-derivación por ratios).
- [ ] Test verde. Commit `feat(core): compute_live — reproyeccion base-vs-live por overlay de datos reales`.

## Task F3-2: Endpoint `GET /api/assets/{id}/live`
**Files:** Modify `src/asset_finance_modeler/web_api/actuals.py` (o nuevo `web_api/live.py` incluido en http_server); Test `tests/web/test_live_api.py`.
- [ ] **Test primero:** activo operational con results_snapshot (base) + actuals; `GET /api/assets/{id}/live` → `{base:{kpis,income_statement,cash_flow}, live:{kpis,income_statement,cash_flow}, comparison:{npv_base,npv_live,delta,...}}`. Sin actuals → live ≈ base. Sin token → 401; activo no operational → 400/422 con mensaje claro (live solo aplica a activos en operación). Verlo fallar.
- [ ] **Implementar:** cargar el Scenario, su `results_snapshot` (base) y sus actuals; calcular `elapsed_years` desde `commissioning_date`; llamar `compute_live`; devolver base+live+comparison. Reusar `_store()`/actuals store.
- [ ] Test verde. Commit `feat(web_api): GET /api/assets/{id}/live (base vs live + comparativa)`.

## Task F3-3: Frontend — cliente + cards/gráfico BASE vs LIVE
**Files:** Modify `web/src/api.ts` (`getLive(id)` + tipos); Create `web/src/components/LivePanel.tsx`; Modify `web/src/App.tsx` (mostrar en detalle de activo operational).
- [ ] `api.ts`: `getLive(id)` + tipos `LiveResult` (base/live kpis + comparison).
- [ ] `LivePanel.tsx`: cabecera con KPIs **BASE vs LIVE lado a lado** (VAN, TIR, DSCR; con delta y flecha sobria ▲/▼ sin emojis) + gráfico recharts (línea base, puntos reales hasta hoy, reproyección del futuro en trazo discontinuo). Paleta sobria.
- [ ] En `App.tsx`, mostrar `LivePanel` en el detalle del activo operational (junto a ActualsGrid/VariancePanel), invalidado por `["live", id]` cuando se meten actuals.
- [ ] `cd web && npm run build` verde; `npm test` verde (añadir un test de LivePanel: base vs live render + delta). Commit `feat(web): panel BASE vs LIVE (reproyeccion viva) en el detalle del activo`.

---

# FASE F4 — Riqueza visual (grado fondo/banco)

## Task F4-1: Dark theme conmutable
**Files:** `web/src/` (theme: Tailwind dark classes + toggle persistido en localStorage); `web/src/App.tsx`.
- [ ] Toggle de tema (claro/oscuro) en el header, persistido. Paleta oscura sobria tipo "operations" (las referencias que pasó Riky). Asegurar contraste y que todos los componentes (KpiCards, tablas, charts, paneles) se ven bien en ambos. Sin emojis, iconos lucide (Moon/Sun).
- [ ] `npm run build` verde. Commit `feat(web): dark theme conmutable (operations) persistido`.

## Task F4-2: Mapa de activos por ubicación
**Files:** `web/src/components/AssetsMap.tsx`; backend: que el activo tenga lat/lon (campo opcional en el Scenario/asset o derivado de un campo `location`). 
- [ ] Añadir ubicación opcional al activo (campo `location`/`lat`/`lon` en el guardado de asset — edición mínima de `web_api/assets.py` SaveAssetBody + persistencia en tags/inputs_snapshot). 
- [ ] `AssetsMap.tsx`: mapa (react-simple-maps o similar ligero, sin API key) con los activos de la cartera por ubicación, tooltip con VAN/estado. Mostrar en el dashboard de Cartera.
- [ ] `npm run build` verde. Commit `feat(web): mapa de activos por ubicacion en el dashboard`.

## Task F4-3: Alertas por desviación
**Files:** `web/src/components/Alerts.tsx`; usa `/variance` y `/live`.
- [ ] Banda/lista de alertas en el dashboard y en el detalle: marca activos cuya desviación real-vs-base supera un umbral (p.ej. |dev%| > 10% o DSCR live < 1,0). Sobrio, iconos lucide (AlertTriangle), sin colores chillones.
- [ ] `npm run build` verde. Commit `feat(web): alertas por desviacion (cartera + detalle)`.

## Task F4-4: Tiles ricos + pulido visual
**Files:** `web/src/components/` (KpiCards, PortfolioOverview).
- [ ] Tiles de KPI con sparkline/mini-tendencia, agrupación visual clara, densidad de fondo. Revisar consistencia (sin emojis, lucide, tipografía/espaciado de banco de inversión). 
- [ ] `npm run build` verde. Commit `feat(web): tiles ricos + pulido visual grado fondo`.

---

# Verificación final (asegurar cero errores en cualquier activo)

## Task V-1: Regresión completa + smoke de todos los activos
- [ ] Ejecutar el comando de regresión completo → todo verde.
- [ ] Smoke: para CADA modelo (los 11 + saas) correr vía API `/run` y confirmar kpis finitos, income_statement/cash_flow presentes, sin NaN/inf; `/portfolio` agrega bien; `/curves` lista; un activo operational con actuals → `/variance` y `/live` coherentes (live≈base sin actuals). 
- [ ] Rearrancar server + rebuild dist; verificar dashboard (Cartera/Oportunidades), detalle (inputs+curvas+actuals+varianza+live), mapa, dark theme.
- [ ] Documentar el resultado. (Sin commit salvo fixes.)

---

## Notas
- F3 es overlay anual (no motor multi-periodo nativo — v4). Documentar.
- Tras F3+F4+V-1: actualizar memoria y PASAR AL DEAL SVJ (reconciliación Excel + rentabilidad/estructuración + teaser final con números reales).
- Server live con código pre-remediación — rebuild+restart en V-1.
