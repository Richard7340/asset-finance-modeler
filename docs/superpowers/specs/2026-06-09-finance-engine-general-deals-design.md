# Diseño — Motor financiero general para deals (híbridos y cualquier estructura)

**Fecha:** 2026-06-09
**Autores:** Riky + Aurora
**Repo:** `asset-finance-modeler`
**Estado:** spec para revisión

---

## 1. Propósito y visión

Convertir `asset-finance-modeler` en el **motor financiero de Gestnova**: una única fuente de verdad determinista en Python capaz de modelar **cualquier deal** — desde uno complejo como el híbrido FV+BESS (SVJ) hasta cualquier otra estructura mezclando activos, streams de revenue y financiación — con **control total** sobre cada input/flujo/KPI, y que **genere un Excel-foto limpio** para inversores.

Cada usuario/agente de Gestnova podrá modelar su negocio con esta capacidad. El principio rector es la **versatilidad general**: las extensiones NO son para SVJ — SVJ es el primer caso (el más complejo) que valida el motor.

### Alcance de ESTA fase (back-end, sesión Claude Code)
- **Sub-proyecto 1:** extender el motor con 5 features generales (E1-E5, abajo).
- **Sub-proyecto 2:** modelar el deal SVJ con el motor extendido, validado nº a nº vs el Excel actual.
- **Sub-proyecto 3:** pulir el generador Excel-foto (`to_xlsx`) a grado-inversor.

### Fuera de alcance (sesión Torre, después)
- Sub-4: app/dashboard interactiva en el webOS (inputs+KPIs vivos, chat/voz).
- Sub-5: wizard end-user (el motor ya tiene `wizard/` base).
- Sub-6: integración en la plataforma Gestnova (el motor se une a la suite `gestnova-*-mcp`).

---

## 2. Lo que YA existe (aprovechar, no reinventar)

- **Core:** `time_grid`, `degradation`, `depreciation`, `financing` (DebtEngine, size_debt DSCR-sculpting, DSRA, cash_sweep), `valuation` (DCF/NPV@WACC, IRR proyecto+equity, LCOE/LCOS, payback, sensitivity_grid), `incentives`, `portfolio`, `statements`, `scenario`.
- **Infrastructure asset:** `schema.py` (producción: solar_pv, wind, **bess**, h2, biomethane, datacenter, generic; streams: **ppa, merchant [con price_curve], arbitrage, ancillary, capacity, offtake, certificate, rental, sla**), `engines/` (production, revenue, capex, opex), `model.py` (orquesta producción→revenue→opex→capex→P&L→deuda→valoración→KPIs).
- **Presets:** `solar_pv_50mw_spain.yaml`, `bess_20mw_4h.yaml`, wind, datacenter.
- **Store:** `exports.py` con **`to_xlsx()` multi-hoja** (Summary + estados + assumptions), to_csv/json/markdown; `compare`, `scenarios`, `sensitivity`, `vdr_sharing`.
- **MCP server (30 tools):** run/clone/compare/sensitivity/export, **dashboard**, **wizard**, vdr_sharing, report, knowledge, workflows, context.
- **Wizard:** `wizard/` (engine, session, persistence) + `wizard.py` MCP tool.

**Implicación:** sub-3 (Excel) y sub-5 (wizard) están casi hechos. El trabajo nuevo de fondo es sub-1 (las extensiones).

---

## 3. Las 5 extensiones (sub-proyecto 1) — todas GENERALES

### E1 — Activo/proyecto HÍBRIDO acoplado
Hoy: assets sueltos; `portfolio.analyze_portfolio` solo **agrega** escenarios (totales + medias ponderadas), no acopla flujos físicos.
Necesidad general: un **proyecto híbrido** que combine N activos con acoplamiento:
- **Acoplamiento de energía:** la salida de un activo alimenta la entrada de otro (FV → carga del BESS). Parámetro general `charge_source` / `coupling` entre activos.
- **Restricción compartida:** punto de conexión común con tope de potencia (MW) que limita la descarga conjunta.
- **Tope de "energía barata" cargable:** % de la producción de un activo disponible como carga barata para otro (general; en SVJ = ~50% de la FV a ~€0).
- **Caja consolidada:** P&L y cashflow combinados; los flujos intra-grupo (p.ej. PPA interno) se **cancelan** a nivel consolidado.
- **Diseño:** nuevo `HybridModel` (o `assets/hybrid/`) que compone `InfrastructureModel` por activo + reglas de acoplamiento. Interfaz: lista de activos + reglas de coupling.

### E2 — Subsistema GENERAL de curvas (librería + búsqueda + custom, cualquier activo/parámetro)
Hoy: `MerchantStream.price_curve` existe; `ArbitrageStream.avg_spread` y `AncillaryStream` son escalares; no hay librería ni curvas reutilizables.
Necesidad general (versatilidad máxima): **cualquier parámetro de cualquier activo** (renovable, industrial, comercial…) puede proyectarse con una **curva**, y la curva puede venir de tres fuentes:

**a) Objeto `Curve` de primera clase** (`core/curves.py`): representa una serie temporal proyectada. Constructores:
- `from_points(values)` — lista de valores por periodo.
- `from_phases(base, phases)` — fases {años, %crecimiento/decrecimiento} (p.ej. spread +2%/0%/−2%; ancillary −12%/−8%/−2%).
- `from_library(name)` — curva pre-cargada y bancable (ver b).
- `from_growth(base, rate)` / `from_inflation(...)` — atajos.
- Atachable a CUALQUIER stream o parámetro (precio, spread, ancillary, demanda, coste, FX, índice…), no solo revenue.

**b) Librería de curvas bancables** (`data/curves/`, YAML/JSON, citadas y versionadas): curvas proyectadas aprobadas/defendibles por tipo de activo y parámetro. No solo renovables:
- *Renovables/energía:* spread DA (Agere/Modo TB2), ancillary (aFRR), captura solar/eólica, precio pool, PPA, curva Poyry.
- *Industrial/commodities:* precios de materias primas, energía industrial, índices de coste, demanda.
- *Transversal:* inflación, FX, WACC/tipos, curvas de degradación.
- Cada entrada lleva **fuente + fecha + nota de bancabilidad**. Extensible: añadir curvas nuevas = añadir un YAML.

**c) Fuentes dinámicas (interfaz definida aquí; ejecución en wizard/Torre):**
- **Agente busca en internet** → precios/curvas → construye una `Curve` (interfaz `from_search(query)` que el wizard/agente rellena).
- **Usuario define la suya** (precios propios, fases propias) → `Curve` custom.
- **Agente sugiere** en el wizard la curva de librería más adecuada al activo.

- En SVJ: spread €82 `from_phases(+2%/0%/−2%)`, ancillary €74k `from_phases(−0/−12/−8/−2)`, captura FV `from_library("solar_capture_es")` — todo trazable a fuente.

### E3 — Deuda multi-tramo + waterfall de subordinación
Hoy: `financing.senior` (un tramo, DSCR-sized). 
Necesidad general: estructura de capital con **múltiples tramos ordenados por prelación** (senior, subordinado, mezzanine…), cada uno con su tipo/plazo/amortización, y **DSCR por tramo** calculado en cascada:
- DSCR_senior = CFADS / DS_senior.
- DSCR_subordinado = (CFADS − DS_senior) / DS_subordinado.
- Extender `core/financing.py`: `tranches: list[DebtTranche]` con `seniority`; `compute_waterfall()` que reparte CFADS por prelación y calcula DSCR de cada tramo.
- En SVJ: senior FV (€2,22M @3,2%, 10a) + subordinada inversor (€1,84M @8,5%, 7a francesa); DSCR subordinado neto del senior = 1,14-1,31×.

### E4 — Eventos de capex / repowering
Hoy: capex inicial (yr0) + degradación continua.
Necesidad general: **eventos de capex en año N** (repowering, augmentation, overhaul) que (a) inyectan un coste en ese año y (b) opcionalmente **resetean la degradación** del activo.
- Añadir `capex_events: list[CapexEvent]` (cada uno {year, amount_or_per_unit, resets_degradation: bool}) al schema de activo.
- En `engines/capex.py` + `core/degradation.py`: aplicar el coste en el año y reiniciar el factor de degradación si procede.
- En SVJ: repowering BESS yr15 (~€60/kWh) + reset de degradación → vida 30a.

### E5 — Outputs de valoración completos (proyecto Y equity, DSCR subordinado)
Hoy: NPV proyecto @WACC, IRR proyecto+equity, DSCR (min/avg).
Necesidad general: exponer de forma limpia y etiquetada:
- **NPV proyecto** @WACC (cada activo y el híbrido, mismo WACC → apples-to-apples).
- **NPV equity** @Ke (coste de equity, no WACC) — vista del propietario.
- **DSCR por tramo** (senior, subordinado) — min/avg/perfil año a año.
- **MOIC** del prestamista subordinado; **recovery going-concern** (NPV de la caja restante del activo / principal pendiente) como métrica de colateral.
- En SVJ: NPV proy FV −1.220 / BESS +2.172 / híbrido +1.644; equity Ke FV −102 / BESS +93; DSCR sub 1,14-1,31×; MOIC 1,37×; recovery ~1,4×.

---

## 4. Sub-proyecto 2 — Modelo SVJ (caso de validación)

Configurar SVJ con el motor extendido y validar que reproduce los KPIs ya validados (tolerancia ~2-3%):

| KPI | Objetivo |
|---|---|
| NPV proyecto Híbrido @WACC 5,37% | +€1.644k |
| NPV proyecto FV / BESS | −€1.220k / +€2.172k |
| IRR proyecto FV / BESS / Híbrido | 2,6% / 17,1% / 8,0% |
| NPV equity Ke FV / BESS | −€102k / +€93k |
| DSCR subordinado inversor (mín-máx, 7a) | 1,14 – 1,31× |
| MOIC inversor / IRR cupón | 1,37× / 8,5% |
| Recovery going-concern colateral | ~1,4× |

Inputs SVJ (resumen): FV 4,76 MWp (yield 1.582, PR 86%, degr 0,6%/a, 7.530 MWh/a, PPA €43 sobre vol. al BESS + spot ~€36 merchant); BESS 4,7 MW / 14,1 MWh (3h), DoD 80%, RTE, 330 ciclos/a, arbitraje spread €82 (curva) + ancillary €74k/MW (curva compresión), carga de FV ~€0 (tope ~50% FV); repowering yr15; deuda senior FV €2,22M @3,2%/10a + subordinada inversor €1,84M @8,5%/7a francesa; WACC híbrido 5,37%, Ke FV 7,5% / BESS 8,5%; impuestos sociedades 25% + eléctrico 7%; vida 30a.

---

## 5. Sub-proyecto 3 — Generador Excel-foto (grado inversor)

Partir de `store/exports.py::to_xlsx()` (ya multi-hoja) y pulirlo a presentación-inversor:
- Hojas: **Resumen KPIs** (FV/BESS/Híbrido, NPV proy+equity, IRR, DSCR por tramo, MOIC), **Flujos de caja** (FV, BESS, híbrido año a año), **Curvas de revenue** (spread+ancillary 30a con fuentes Agere/Modo), **Cuadro de deuda** (senior+subordinado, DSCR perfil), **Sensibilidad** (por ancillary/spread), **Assumptions** (todos los inputs trazables).
- **Excel-foto estático** (valores + gráficos, sin fórmulas frágiles). Coherente por construcción con el motor.
- Formato limpio (cabeceras, € miles, % , gráficos NPV-por-duración y DSCR-perfil).

---

## 6. Validación y testing

- **Tests unitarios** por extensión (E1-E5): acoplamiento, curvas por fases, waterfall multi-tramo, eventos capex, NPV equity/DSCR subordinado. (El motor tiene ≥193 tests; añadir los nuevos sin romper los existentes.)
- **Test de validación SVJ:** un test que monta el modelo SVJ y asierta los KPIs de §4 dentro de tolerancia.
- **Sanity-check vs Excel actual:** confirmar que el rebuild reproduce los KPIs validados; documentar cualquier diferencia.
- `ruff` + `mypy` limpios.

---

## 7. Criterios de aceptación (definición de "hecho" esta fase)

1. Las 5 extensiones implementadas, testeadas y generales (un preset hybrid/SVJ las ejercita).
2. El modelo SVJ reproduce los KPIs de §4 (±2-3%); Python = fuente de verdad.
3. `to_xlsx` genera un Excel-foto grado-inversor del modelo SVJ, coherente con el motor.
4. Tests verdes, lint/typing limpios, sin romper lo existente.
5. Documentado cómo el motor se expone vía MCP (`finance.simulate.run/export/...`) para que la sesión Torre conecte el dashboard/webOS sin tocar el motor.

---

## 8. Notas de integración (para la sesión Torre — no construir aquí)

- El Excel-foto se mostrará/editará en el webOS vía el **bridge OnlyOffice (F0)**.
- El **dashboard MCP tool** + **wizard MCP tool** alimentan la app interactiva del webOS.
- El motor se une a la suite `gestnova-*-mcp` → cada agente obtiene capacidad financiera.
- Patrón de wiring webOS (manifest+executors+iframe-bridge) ya documentado.
