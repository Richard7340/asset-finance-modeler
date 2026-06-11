# Diseño v2 — Plataforma genérica multi-activo (grado banco de inversión)

**Fecha:** 2026-06-12 · **Autores:** Riky + Aurora · **Repo:** `asset-finance-modeler` · **Estado:** spec para revisión

## 1. Visión

Evolucionar el simulador v1 (dashboard de UN deal, SVJ) a una **plataforma de gestión de activos grado banco de inversión / fondo**: el usuario abre, edita y valora **cualquier activo** (renovable, industrial, inmobiliario, empresa, BESS, datacenter…), con **acceso a TODOS los inputs del modelo** organizados por activo y por sección, y ve la valoración completa (KPIs + **FCF** + **cuenta de resultados** + curvas). Estética profesional, sin emojis, control absoluto. El SVJ queda como un caso más.

Pensada para migrar al webOS (cada usuario gestiona su cartera con su agente). Esta v2 cubre el **núcleo genérico**; persistencia de carteras, seguimiento temporal y migración webOS son trozos posteriores.

### Alcance v2 (esta fase)
- **Backend genérico:** listar modelos/presets disponibles; devolver el **árbol completo de inputs** de cualquier modelo (introspección del schema); **correr** cualquier modelo con overrides de cualquier input → KPIs + FCF + cuenta de resultados + curvas; exportar Excel.
- **Frontend genérico:** panel de **activos a la izquierda** (selector), **editor de inputs por secciones plegables** (generado dinámicamente del schema), vistas de **KPIs + FCF + cuenta de resultados + curvas**, restyle **grado banco de inversión (sin emojis)**.
- El deal SVJ (FV+BESS híbrido) sigue accesible (sus dos presets + la vista híbrida consolidada que ya existe).

### Incluido en v2 — PERSISTENCIA (Riky: "que se guarde para ir monitorizando el activo y revisar simulados")
- **Guardar** un activo configurado (modelo + overrides de inputs + resultados) en el store de escenarios del motor (`store/scenarios.py`: `inputs_snapshot` + `results_snapshot` + `created_at` + name/tags/user/workspace — YA existe).
- **Listar** la cartera de activos guardados (a la izquierda), **recargar** uno para seguir editándolo, y **revisar** una simulación pasada tal como se corrió (con su fecha y sus inputs) — seguimiento en el tiempo / asset management.

### Fuera de alcance v2 (trozos siguientes)
- Crear un activo de tipo totalmente arbitrario desde cero (más allá de partir de un preset/modelo existente) — trozo siguiente.
- Multi-tenant / permisos por workspace (el store ya tiene user_id/workspace_id; el cableado fino es posterior).
- Migración webOS — sesión Torre.

## 2. Arquitectura

Mismo contenedor que v1 (FastAPI sirve API + SPA). Se **generaliza** la capa `/api`:
- `deals/svj.py` (v1) se mantiene para el caso híbrido SVJ; se añade un módulo genérico `web_api/models.py` que trabaja sobre cualquier `InfrastructureModelConfig`/preset.
- El motor ya expone todo lo necesario: `load_preset`, `InfrastructureModel(cfg).run()` → `FinancialOutput` con `pnl` (= cuenta de resultados: revenue, cogs, gross_profit, opex, ebitda, depreciation, ebit, interest_expense, ebt, tax, net_income), `cashflow` (cfo/cfi/cff = estado de flujos), `project_kpis`, `summary`, `revenue_breakdown`.

## 3. Backend genérico (`web_api/models.py` + rutas `/api/models/*`)

- `GET /api/models` → lista de modelos disponibles: presets del motor (`solar_pv_50mw_spain`, `bess_20mw_4h`, `wind_onshore_30mw_spain`, `datacenter_10mw_tier3`, `svj_fv_cordoba`, `svj_bess_cordoba`, …) con `{id, name, asset_type}`. + el deal compuesto `svj_hybrid`.
- `GET /api/models/{id}/schema` → **árbol de inputs** del modelo, por secciones, generado por **introspección del Pydantic `InfrastructureModelConfig`**: para cada sección top-level (meta, production, revenue, capex, opex, degradation, financing, taxes, valuation, capex_events) los campos editables con `{path, label, type (number/select/bool/list), value, unit?, options?}`. (Helper recursivo `schema_tree(config_dict, model_cls)`.)
- `POST /api/models/{id}/run` → body `{overrides: {<dotted.path>: value}}`. Aplica overrides por ruta sobre el dict del preset, valida, corre, y devuelve `{kpis, income_statement: {years, rows:{revenue, ebitda, ebit, interest, ebt, tax, net_income, …}}, cash_flow: {years, cfo, cfi, cff, fcf}, curves: {…}, summary}`. Series anualizadas (helper `_annual`, ppy del meta).
- `POST /api/models/{id}/export` → Excel-foto (reusa `build_xlsx`/`to_xlsx`).
- `GET /api/models/svj_hybrid/run` reusa `deals/svj.run_svj` (el caso híbrido consolidado).
- Auth por token (igual que v1, `require_token`).

**Introspección de inputs:** función pura que, dado el `model_dump()` del config y el modelo Pydantic, recorre los campos y produce el árbol con `path` (p.ej. `production.capacity_mwp`, `revenue[0].price_eur_per_unit`, `financing.senior.interest_rate`), inferring type from the value/annotation. Editar = enviar ese `path` en overrides; un helper `set_by_path(dict, path, value)` lo aplica.

### Persistencia (`web_api/assets.py` + rutas `/api/assets/*`, sobre `store/scenarios.py`)
- `POST /api/assets` → body `{model_id, name, overrides, tags?}`. Corre el modelo, guarda un `Scenario` (inputs_snapshot = {model_id, overrides}, results_snapshot = {kpis, summary}, created_at, name, tags). Devuelve el `id`.
- `GET /api/assets` → lista la cartera guardada `[{id, name, model_id, created_at, kpis_resumen}]` (para el panel izquierdo).
- `GET /api/assets/{id}` → el activo guardado completo (model_id + overrides + results_snapshot + created_at) para **recargar/revisar** la simulación tal como se corrió.
- `DELETE /api/assets/{id}` → borrar.
- Reusa el `ScenarioStore` existente (SQLite, `ASSET_FINANCE_DB_PATH`/volumen `/data/scenarios`). Auth por token.

## 4. Frontend genérico (extiende `web/`)

- **Panel de activos (izquierda):** dos grupos — **"Mi cartera"** (`GET /api/assets`, los guardados, con su fecha) y **"Nuevo desde modelo"** (`GET /api/models`, los presets/tipos). Seleccionar carga el activo (sus inputs) en el editor. Botón **Guardar** (`POST /api/assets`) y, sobre cada guardado, **revisar** (recarga su simulación tal como se corrió) y borrar.
- **Editor de inputs por secciones:** del `schema`, render dinámico — secciones plegables (Producción, Revenue/Curvas, CAPEX, OPEX, Degradación, Financiación, Impuestos, Valoración). Cada input: number/select/toggle según type. Cambiar cualquiera → `run` (debounce) → actualiza salida.
- **Salida (derecha):** tarjetas **KPI**, tabla **Cuenta de resultados** (años × filas), tabla/gráfico **Flujos de caja (FCF)**, **curvas** y gráficos. Pestañas o secciones limpias.
- **Restyle grado banco de inversión:** sin emojis, paleta sobria (grises/azul marino/acento), tipografía clara, tablas densas y legibles, números bien formateados (€, %, ×). Cabecera "Gestnova · Plataforma de Valoración de Activos".
- `?embed=1` y `VITE_API_BASE` se mantienen (webOS-ready).

## 5. Testing
- **Backend:** `schema_tree` (introspección produce paths esperados para un preset), `set_by_path`, `/api/models` (lista), `/api/models/{id}/schema` (secciones), `/api/models/{id}/run` (un override por path mueve un KPI; income_statement y cash_flow presentes y anualizados), reproduce KPIs de un preset conocido.
- **Frontend:** render del editor dinámico desde un schema mock; cambiar un input llama run; tablas de cuenta de resultados/FCF renderizan.

## 6. Criterios de aceptación (v2)
1. `GET /api/models` lista los presets + svj_hybrid.
2. `GET /api/models/{id}/schema` devuelve el árbol completo de inputs por secciones para cualquier preset.
3. `POST /api/models/{id}/run` con override de cualquier `path` recalcula y devuelve KPIs + cuenta de resultados + FCF + curvas.
4. **Persistencia:** `POST /api/assets` guarda; `GET /api/assets` lista la cartera; `GET /api/assets/{id}` recarga una simulación pasada con su fecha e inputs; `DELETE` borra.
5. Frontend: panel izquierdo con "Mi cartera" (guardados) + "Nuevo desde modelo" (presets); seleccionar → editor de inputs por secciones + salida; cambiar cualquier input recalcula en vivo; Guardar y Revisar funcionan.
6. Estética grado banco de inversión, sin emojis. SVJ sigue accesible.
7. No rompe la v1 ni los 557 tests existentes; arquitectura webOS-ready intacta.

## 7. Notas trozos siguientes (no aquí)
Persistencia (store scenarios: guardar/recargar activos por usuario/workspace) · activo nuevo desde cero · seguimiento temporal (asset management) · combinación híbrida arbitraria de N activos seleccionados · migración webOS (iframe-kernel-bridge, el agente llama `/api/models/*`).
