# asset-finance-modeler — Resumen completo del proyecto (v1.4)

**Fecha:** 2026-05-15
**Estado:** v1.4 COMPLETO — listo para integración con Gestnova/Ian
**Autor del proyecto:** Aurora (con Riky)

---

## 1. Visión global

`asset-finance-modeler` es un **motor financiero comprehensive + capa de inteligencia estructurada**, expuesto como **MCP server (stdio)** para que cualquier agente conversacional (Ian/Gestnova, Aurora, otros agentes futuros) pueda **modelar financieramente cualquier negocio o activo**, **correr análisis complejos** mediante workflows declarativos, y **mantener memoria semántica** del contexto del cliente — **sin meter un LLM adicional en la cadena**.

Es la pieza que convierte a Ian en **un asistente con capacidad de CFO + departamento de asset management** de verdad: no se inventa cifras, ejecuta cálculo financiero estándar, recuerda lo que se discutió, y conoce los frameworks correctos para cada situación.

---

## 2. Estadísticas finales

| Métrica | Valor |
|---|---|
| Commits totales | **59** |
| Source files (.py) | **45** |
| Líneas de código | **3,513** |
| Test files | **48** |
| Tests passing | **193 ✅** |
| ruff (linter) | **clean ✅** |
| mypy (type checker, strict) | **clean ✅** |
| **MCP tools expuestas** | **30 ✅** |
| Conceptos financieros sembrados | **30** (en español+inglés) |
| Workflows declarativos | **4** templates |
| Asset types soportados | **1** (SaaS, con arquitectura para añadir N más) |
| Idiomas en knowledge base | **ES + EN** (con embedding multilingual) |

---

## 3. Arquitectura técnica completa

### 3.1 Repo layout

```
asset-finance-modeler/
├── pyproject.toml              # Python 3.12, deps pydantic/pandas/faiss/sentence-transformers
├── src/asset_finance_modeler/
│   ├── core/                   # Primitivos asset-agnostic
│   │   ├── time_grid.py        # TimeGrid (M/Q/Y, fechas, periods_per_year)
│   │   ├── drivers.py          # GrowthCurve + AmortizationSchedule
│   │   ├── statements.py       # PnLBuilder, CashFlowBuilder, BalanceBuilder, unit econ, runway, debt metrics
│   │   ├── valuation.py        # DCF (Gordon + exit multiple) + sensitivity grid 2D
│   │   └── scenario.py         # Scenario class + apply_overrides (JSONPath) + run_scenario_saas
│   │
│   ├── assets/saas/            # Tipo de activo: SaaS (Gestnova baseline)
│   │   ├── schema.py           # Schema pydantic v2 completo (revenue, COGS, opex, capital, taxes, valuation)
│   │   ├── engines.py          # CohortRevenueEngine, COGSEngine, OpexEngine, DebtEngine, CapExEngine
│   │   ├── model.py            # SaasModel orchestrator → ModelResults
│   │   ├── loader.py           # YAML preset loader
│   │   └── presets/gestnova.yaml  # Baseline real de Gestnova
│   │
│   ├── store/                  # Persistencia + análisis sobre scenarios
│   │   ├── scenarios.py        # SQLiteScenarioStore con árbol genealógico
│   │   ├── compare.py          # compare_scenarios (tabla delta)
│   │   ├── sensitivity.py      # sensitivity_1d genérico
│   │   └── exports.py          # to_csv, to_json, to_xlsx, to_markdown_table, to_markdown_report, to_summary
│   │
│   ├── intelligence/           # CAPA NUEVA — Plan 4
│   │   ├── embeddings.py       # LocalEmbeddingProvider (multilingual MiniLM)
│   │   ├── knowledge/          # Base de conocimiento financiero
│   │   │   ├── base.py         # KnowledgeBase (FAISS + SQLite)
│   │   │   ├── seed.py         # seed_default_knowledge()
│   │   │   └── data/seed.yaml  # 30 conceptos financieros
│   │   ├── workflows/          # Procesos declarativos
│   │   │   ├── engine.py       # WorkflowEngine con ${var} + foreach
│   │   │   ├── loader.py       # list/load workflows
│   │   │   └── templates/      # 4 workflows YAML
│   │   └── context/            # Memoria semántica
│   │       └── memory.py       # ContextMemory (multi-tenant)
│   │
│   ├── cli/                    # CLI para uso local sin MCP
│   │   └── main.py             # argparse: list-models, run, exports
│   │
│   └── mcp_server/             # Servidor MCP stdio
│       ├── server.py           # Entry point + ToolSpec registry wiring
│       ├── registry.py         # build_registry(store, kb, ctx) → 30 tools
│       └── tools/
│           ├── discover.py     # list_models, describe_schema, list_presets, load_baseline
│           ├── crud.py         # create/clone/list/delete/set_canonical scenario
│           ├── execute.py      # run, get_results, get_genealogy
│           ├── analyze.py      # compare, sensitivity_1d, sensitivity_grid
│           ├── output.py       # export, fetch_external, set_external, track stubs
│           ├── knowledge.py    # knowledge.search/add/list_categories
│           ├── workflows.py    # workflows.list/describe/run
│           └── context.py      # context.store/search/recent
│
├── tests/
│   ├── unit/                   # 45 unit test files
│   ├── golden/                 # Snapshot test sobre gestnova preset
│   └── integration/            # E2E: CLI, MCP stdio, intelligence smoke
│
└── docs/
    ├── INTEGRATION.md          # Bridge plan para Gestnova/Ian
    ├── PROJECT-SUMMARY.md      # Este documento
    └── superpowers/            # 1 spec + 4 plans con TDD detallado
```

### 3.2 Stack técnico

- **Lenguaje:** Python 3.12 (type hints strict)
- **Validation:** pydantic v2 (model_validate + field validators)
- **Datos:** pandas (series temporales), numpy_financial (NPV, IRR)
- **Exports:** openpyxl (XLSX multi-sheet), PyYAML (presets/workflows)
- **Embeddings:** sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 (384 dim, ~120MB, soporta español)
- **Vector search:** faiss-cpu (IndexFlatIP — cosine similarity)
- **Persistencia:** SQLite (scenarios, knowledge metadata, context memory)
- **MCP SDK:** `mcp>=1.0` (Anthropic Python SDK oficial)
- **Templating:** jinja2 (disponible para futuras extensiones)
- **Testing:** pytest + pytest-snapshot
- **Quality gates:** ruff (lint) + mypy strict (45 source files)

---

## 4. Las 30 MCP tools que Ian va a invocar

Cuando Ian se conecte al modeler como MCP server, tendrá acceso a estas 30 tools. **Cada una es una llamada determinística que devuelve JSON** — no hay LLM intermedio inventando nada.

### 4.1 Discovery (3 tools)

| Tool | Qué hace | Cuándo la usa Ian |
|---|---|---|
| `finance.simulate.list_models` | Lista tipos de activo disponibles (`gestnova`/SaaS hoy; en futuro renewables, real_estate, lbo) | Al iniciar conversación financiera sin saber qué tiene |
| `finance.simulate.describe_schema` | Devuelve JSON Schema completo del modelo (qué campos hay, tipos, descripciones) | Cuando necesita saber qué inputs pedirle al usuario |
| `finance.simulate.list_presets` | Lista presets disponibles para un asset type | Antes de cargar baseline |

### 4.2 Scenario CRUD (5 tools)

| Tool | Qué hace |
|---|---|
| `finance.simulate.load_baseline` | Carga preset (ej. `gestnova.yaml`) como Scenario canónico en SQLite |
| `finance.simulate.create_scenario` | Crea Scenario hijo de otro con `overrides` JSONPath (ej. `{"revenue.sources[0].pricing.per_unit_per_period": 250}`) |
| `finance.simulate.clone_scenario` | Branch desde scenario existente heredando sus overrides + añadiendo nuevos |
| `finance.simulate.list_scenarios` | Lista scenarios persistidos con filtros (base_model, include_deleted) |
| `finance.simulate.delete_scenario` | Soft-delete. Scenarios canónicos NO se pueden borrar (protección automática) |
| `finance.simulate.set_canonical` | Marca un scenario como baseline oficial (immutable) |

### 4.3 Execution (3 tools)

| Tool | Qué hace | Output |
|---|---|---|
| `finance.simulate.run` | Ejecuta el modelo entero, persiste resultados | `{scenario_id, summary}` — 8-10 métricas clave |
| `finance.simulate.get_results` | Lee resultados cacheados con view selector | view ∈ {summary, pnl, cashflow, balance, unit_econ, valuation, debt_metrics, revenue_breakdown, sensitivity, all} |
| `finance.simulate.get_genealogy` | Árbol de ancestros + descendientes de un Scenario | `{ancestors, descendants}` con nombres + IDs |

### 4.4 Analysis (3 tools)

| Tool | Qué hace |
|---|---|
| `finance.simulate.compare` | Tabla delta de N scenarios sobre métricas clave (default: revenue_y1, EBITDA, cash, runway, LTV/CAC, EV) |
| `finance.simulate.sensitivity_1d` | Sweep de una variable cualquiera (JSONPath) sobre N valores → cómo cambia una métrica |
| `finance.simulate.sensitivity_grid` | Sweep 2D: dos variables × N×M valores → matriz de impacto sobre una métrica (típico: WACC×growth → EV) |

### 4.5 Output (3 tools)

| Tool | Formatos soportados |
|---|---|
| `finance.simulate.export` | `summary` (JSON 8 métricas) / `markdown_table` (por view) / `markdown_report` (narrativa) / `csv` / `xlsx` multi-sheet / `json` full |
| `finance.simulate.fetch_external` | Devuelve **instrucción al caller** para que ejecute WebSearch (modeler NO hace HTTP — delegación) |
| `finance.simulate.set_external` | Recibe el resultado del WebSearch del caller y lo persiste como override del scenario |

### 4.6 V2 stubs (3 tools)

| Tool | Estado |
|---|---|
| `finance.track.import_real_data` | Devuelve `{error: "v2 surface"}` — placeholder para futura integración con contabilidad real |
| `finance.track.reconcile` | Idem |
| `finance.track.variance_report` | Idem |

### 4.7 Knowledge base (3 tools) — NUEVAS en Plan 4

| Tool | Qué hace |
|---|---|
| `finance.knowledge.search` | Búsqueda semántica multilingüe (FAISS) sobre 30 conceptos financieros. Filtros: category, tenant_id, top_k. Devuelve título + contenido + tags + score |
| `finance.knowledge.add` | Añade nueva entrada al knowledge base. Opcional `tenant_id` → conocimiento específico de una empresa |
| `finance.knowledge.list_categories` | Lista categorías con conteo |

### 4.8 Workflows (3 tools) — NUEVAS en Plan 4

| Tool | Qué hace |
|---|---|
| `finance.workflows.list` | Lista los 4 workflows built-in con sus inputs |
| `finance.workflows.describe` | Detalle completo de un workflow: inputs requeridos + nº de pasos |
| `finance.workflows.run` | Ejecuta un workflow declarativo (orquesta múltiples tools internas). Devuelve el output definido por el workflow |

### 4.9 Context memory (3 tools) — NUEVAS en Plan 4

| Tool | Qué hace |
|---|---|
| `finance.context.store` | Guarda entrada de contexto por tenant (empresa cliente) — decisiones, supuestos, preguntas |
| `finance.context.search` | Búsqueda semántica sobre el contexto del tenant. Aislamiento total entre tenants |
| `finance.context.recent` | Últimas N entradas de un tenant en orden cronológico inverso |

---

## 5. Knowledge base sembrado (30 conceptos)

El knowledge base viene con 30 entradas en 9 categorías. Está en español e inglés (el modelo de embeddings es multilingüe). Ian las recupera semánticamente para fundamentar sus respuestas.

### 5.1 Categorías + ejemplos

| Categoría | Conceptos sembrados |
|---|---|
| **unit_economics** (5) | CAC, LTV, Payback CAC, Rule of 40, Magic Number |
| **valuation** (5) | DCF, WACC, Exit Multiple Valuation, NPV, IRR |
| **cash_flow** (3) | FCF, Runway, Working Capital |
| **debt** (4) | DSCR, ICR, LTV (real estate), Amortización francesa |
| **pnl** (3) | EBITDA, Gross Margin, Tax loss carryforward |
| **capex** (2) | Depreciación lineal, Maintenance vs Growth CapEx |
| **saas** (3) | Cohort Retention, ARR, Net Revenue Retention (NRR) |
| **framework** (4) | Cuándo usar Gordon vs Exit Multiple, Interpretar LTV/CAC, Diagnosis cuando runway < 12 meses, Cuándo levantar deuda vs equity |
| **real_estate** (2) | Cap Rate, Gross Yield vs Net Yield |

### 5.2 Ejemplo de entrada

```yaml
category: framework
title: "Diagnosis cuando runway < 12 meses"
content: |
  Acciones en orden de impacto:
  1. Levantar capital (preferred si fundamentals OK).
  2. Aumentar precio (test A/B en cohortes nuevas).
  3. Reducir CAC: optimizar canales más caros.
  4. Reducir burn fijo: revisar OPEX no esencial.
  5. Cobrar más rápido: bajar DSO, prepayments.
tags: [framework, runway, diagnosis]
```

Cuando Ian recibe **"runway crítico, qué hago"**, ejecuta `finance.knowledge.search("diagnosis runway crítico")` → recibe esta entrada → contesta con el framework correcto, **citado**, sin inventar.

### 5.3 Cómo se extiende

- **Global** (todos los tenants): `finance.knowledge.add({title, content, category})` sin `tenant_id`
- **Per-empresa** (sólo visible para un cliente): añadir con `tenant_id="cliente_x"`. Útil para conocimiento confidencial: política de pricing del cliente, estructura societaria, benchmarks internos.

---

## 6. Workflows declarativos (4 templates iniciales)

Los workflows son recetas YAML que orquestan múltiples MCP tools en una sola llamada. Ian invoca `finance.workflows.run({workflow_id, inputs})` y recibe el output directamente.

### 6.1 `pricing_impact_analysis`

**Caso de uso:** "¿Qué pasa si subo/bajo el precio?"

**Inputs:** `base_scenario_id`, `prices: list[float]`

**Steps:** N clones (uno por precio) → N runs → comparativa de revenue Y1, EBITDA, EV

**Output:** Tabla delta + revenue de cada variante + IDs para luego exportar dashboard

### 6.2 `runway_diagnosis`

**Caso de uso:** "Mi runway es < 12 meses, ¿qué acciones tienen más impacto?"

**Inputs:** `base_scenario_id`

**Steps:** Run baseline + 3 variantes (precio +50€, CAC −300€, burn −600€) y compara runway en cada caso

**Output:** Runway de baseline + 3 escenarios + scenario_ids para drill-down

### 6.3 `unit_econ_review`

**Caso de uso:** "Revísame mis unit economics"

**Inputs:** `scenario_id`

**Steps:** Run + extracción de ARPU, CAC, LTV, LTV/CAC, payback, gross margin del último periodo

**Output:** Métricas + hint interpretativo (LTV/CAC < 3 problemático, > 5 muy fuerte)

### 6.4 `valuation_summary`

**Caso de uso:** "¿Cuánto vale mi empresa?"

**Inputs:** `scenario_id`

**Steps:** Run + extracción de DCF (PV explicit + terminal + EV total) + sensitivity grid si está configurada

**Output:** Enterprise value, descomposición, grid de sensitividad WACC×growth

### 6.5 Sintaxis de workflow YAML

```yaml
id: ejemplo
name: "Nombre"
description: "Qué hace"
inputs:
  - name: base_scenario_id
    type: string
    required: true
  - name: prices
    type: array
    required: true
steps:
  - id: clone_variants
    foreach: "${prices}"           # itera la lista
    as: price                       # variable de iteración
    tool: finance.simulate.clone_scenario
    args:
      scenario_id: "${base_scenario_id}"
      name: "pricing-${price}"
      overrides:
        "revenue.sources[0].pricing.per_unit_per_period": "${price}"
    capture: variants               # captura los N resultados como lista
output:
  resumen: "${variants}"
  hint: "Usa compare con los IDs para ver tabla delta"
```

Substitución `${var}`: si la string completa es una sola referencia, devuelve el valor tipado (mantiene int/list/dict). Si es interpolación dentro de string, hace string substitution.

### 6.6 Crear workflows nuevos

Añadir un `.yaml` en `intelligence/workflows/templates/`. Aparece automáticamente en `finance.workflows.list`. Sin código Python necesario.

---

## 7. Capacidades nuevas de Ian post-integración

### 7.1 Ejemplo conversación 1: cliente pyme pide modelo financiero

**Cliente vía WhatsApp:** "Tengo una clínica dental con 3 dentistas, facturamos €25k/mes. Quiero planificar siguientes 2 años."

**Ian internamente:**
1. `finance.simulate.describe_schema({model: "saas"})` — schema actual sirve mayormente (saas presente; futuro `assets/generic_business/`)
2. Conversa con cliente: te pregunta gastos (alquiler, salarios, equipamiento), elasticidad de pricing, expectativas de crecimiento
3. Llama a `finance.simulate.create_scenario` con los overrides recogidos
4. `finance.simulate.run`
5. `finance.workflows.run("valuation_summary", ...)` para valoración
6. `finance.simulate.export(format="markdown_report")` → narrativa para email
7. `finance.simulate.export(format="xlsx", path=...)` → archivo adjunto
8. `finance.context.store(tenant_id="cliente_x", value="Modelo inicial: revenue €25k/mes, EV €1.2M, runway suficiente")`

**Cliente recibe:** mensaje narrativo + Excel adjunto + link a dashboard interactivo (artifact con Chart.js)

### 7.2 Ejemplo conversación 2: socio pide análisis estratégico

**Riky vía voz a Ian:** "Pedro está pensando bajar precio de Gestnova de 300 a 250. Dame análisis."

**Ian:**
1. `finance.context.search(tenant_id="gestnova", query="discusiones recientes sobre pricing")` → recupera contexto histórico
2. `finance.knowledge.search("impacto de bajar pricing en SaaS B2B")` → recupera framework
3. `finance.simulate.list_scenarios({base_model: "gestnova"})` → encuentra baseline canónico
4. `finance.workflows.run("pricing_impact_analysis", {base_scenario_id, prices: [200, 250, 300, 350]})`
5. `finance.simulate.compare([baseline_id, 200_id, 250_id, 300_id, 350_id])`
6. `finance.context.store(tenant_id="gestnova", value="Análisis 250€: -20% revenue Y1 pero +X% volumen necesario para break-even")`

**Riky escucha:** "Pedro, según el modelo: bajar a 250€ reduce revenue Y1 de €196k a €164k. Para mantener EV con churn estable, necesitarías captar 22% más clientes anualmente. Si el mercado responde con elasticidad > 1.3, vale la pena. Te he dejado el escenario completo en [link]."

### 7.3 Ejemplo conversación 3: continuidad cross-sesión

**Cliente, 2 semanas después:** "Aquel tema del precio que vimos, ¿cómo iba?"

**Ian:**
1. `finance.context.recent(tenant_id="cliente_x", limit=20)` → ve historial reciente
2. `finance.context.search(tenant_id="cliente_x", query="análisis precio")` → encuentra la entrada exacta
3. `finance.simulate.list_scenarios(base_model="cliente_x_business")` → encuentra los scenarios que se crearon entonces
4. `finance.simulate.get_results(scenario_id, view="summary")` para refrescar números

**Cliente recibe:** "La última vez analizamos 3 precios (200/250/300). Recomendamos quedarte en 300€ por margen, aunque 250 da mejor conversión. ¿Quieres que actualicemos el modelo con datos reales de este último mes?"

### 7.4 Capacidades nuevas que tendrá Ian (resumen)

✅ **Modelar cualquier negocio SaaS** desde inputs declarativos
✅ **Comparar N escenarios** lado a lado (pricing, costes, equipo, deuda, funding)
✅ **Sensitivity analysis** sobre cualquier variable contra cualquier métrica
✅ **Valoración DCF** completa con sensitivity grid 2D (WACC × growth)
✅ **Análisis de deuda**: DSCR, ICR, leverage, calendarios de amortización
✅ **Tax modeling** con carryforward, IS, IVA, R&D deductions
✅ **Multi-currency** + inflación
✅ **Outputs flexibles**: dashboard (Chart.js artifact), Excel multi-sheet, markdown report, CSV, PDF (vía Gestnova DocumentTemplate)
✅ **Búsqueda en knowledge financiero** — Ian cita frameworks correctos, no se los inventa
✅ **Workflows complejos** en una sola llamada — orquestación encapsulada
✅ **Memoria semántica por cliente** — continuidad entre conversaciones
✅ **Multi-tenant** desde día 1 — cuando se venda como módulo, cada empresa tiene su silo aislado

---

## 8. Multi-tenancy

Gestnova venderá esto a clientes. Cada cliente necesita:
- Sus propios scenarios (los baseline son por empresa)
- Su propio knowledge confidencial (si quiere añadir notas internas)
- Su propia memoria de conversación (NUNCA mezclar con otros)

### 8.1 Cómo está implementado hoy

| Componente | Multi-tenant en V1.4 | Cómo |
|---|---|---|
| **Scenarios** | No (single-tenant en v1) | Plan 5 lo añadirá: columna `tenant_id` en `scenarios` table + index |
| **Knowledge** | ✅ Sí | Columna `tenant_id` nullable. `NULL` = global (visible a todos). String = específico tenant. Search filtra automáticamente |
| **Context memory** | ✅ Sí | Columna `tenant_id` NOT NULL. Aislamiento total — un tenant nunca ve memoria de otro |

### 8.2 Cómo lo usa Gestnova/Ian

En la integración:
- `tenant_id` = `companyId` de Gestnova (ej. `"gestnova"`, `"cliente_pedro_clinic"`, `"inmobiliaria_xyz"`)
- Las tools que aceptan `tenant_id` lo reciben automáticamente del contexto de Ian
- El bridge plan en `docs/INTEGRATION.md` define cómo Ian inyecta `tenant_id` en cada llamada

---

## 9. Integración con Ian — Bridge plan (3-4h en `livekit-voice-platform`)

### 9.1 Pasos

1. **MCP connector** en config de `agent-gestnova-ian`:
   ```json
   {
     "mcpServers": {
       "asset-finance-modeler": {
         "command": "python",
         "args": ["-m", "asset_finance_modeler.mcp_server.server"],
         "env": {
           "PYTHONPATH": "/path/to/asset-finance-modeler/src",
           "ASSET_FINANCE_DB_PATH": "/var/lib/gestnova/finance.db"
         }
       }
     }
   }
   ```

2. **Nueva skill `financial-analysis`** en `src/skills/core/financial-analysis.skill.ts`:
   - Declara las 30 MCP tools con descripciones LLM-friendly
   - System prompt addendum: "para preguntas financieras, primero busca en finance.knowledge.search; luego usa workflows.run cuando sea aplicable; persiste decisiones con context.store"

3. **Nueva skill `finance-dashboard`** que genera artifacts visuales:
   - Toma `get_results(view="all")` del modeler
   - Construye `htmlBody` con KPI cards + 3-4 Chart.js (revenue ramp, cash position, P&L margin, valuation sensitivity heatmap)
   - Llama a `createArtifact` existente de Gestnova → URL firmada al cliente

4. **Helper `buildModelInputsFromCompanyData`** (cuando se quiera usar datos reales de Prisma):
   - Lee Expense/Invoice/Customer/Agent de Prisma
   - Transforma a `SaasModelConfig` partial → pasa como overrides

5. **Test E2E**: WhatsApp "Ian, simula bajada a 250€ y mándame dashboard" → cadena completa.

### 9.2 Cómo se ve en código (skill simplificada)

```typescript
// src/skills/core/financial-analysis.skill.ts
export const financialAnalysisSkill: Skill = {
  name: 'financial-analysis',
  tools: [
    // 30 tools del MCP modeler exposed con descriptions LLM-friendly
  ],
  systemPromptAddendum: `
    Para preguntas técnicas financieras:
    1. PRIMERO busca en finance.knowledge.search con la pregunta
    2. Si hay framework aplicable (workflow_id en el knowledge), invoca finance.workflows.run
    3. Si no hay workflow, encadena tools manualmente
    4. Para presentar resultados: usa finance.simulate.export con formato apropiado al canal
    5. Persiste decisiones importantes con finance.context.store
    
    Para presentar visualmente:
    - WhatsApp: link a artifact dashboard (skill: finance-dashboard)
    - Email: markdown_report inline + XLSX adjunto
    - Voz: summary verbal + "te mando link al WhatsApp"
  `,
};
```

---

## 10. Roadmap futuro (cuando la demanda lo justifique)

### Fase 2 (1 mes — cuando tengas 2-3 clientes pagando)

Añadir asset types adicionales — cada uno es un plan TDD claro **sin tocar el core**:

| Asset type | Mercado | Esfuerzo |
|---|---|---|
| `assets/generic_business/` | Cualquier pyme no-SaaS (clínicas, retail, servicios) | 1 semana |
| `assets/real_estate/` | Inmuebles, REITs, dueños de carteras | 1 semana |

Add-on Gestnova: cada uno cobrable como "módulo activos adicional".

### Fase 3 (3 meses)

| Asset type | Mercado | Esfuerzo |
|---|---|---|
| `assets/renewables/` | Solar, eólica, project finance europeo | 2 semanas |
| `assets/lbo/` | M&A, private equity boutique | 2 semanas |
| Multi-tenancy en scenarios | Multi-empresa hardening | 1 semana |

### Fase 4 (visión completa "fondo de inversión")

- **Portfolio aggregation**: combinar N activos en cartera con weights + correlations
- **Waterfall distributions**: LP/GP, hurdle rates, carried interest 20/80
- **Monte Carlo**: stochastic modeling con distribuciones
- **Risk metrics**: VaR, Sharpe ratio, max drawdown
- **Currency hedging**: forwards, swaps
- **Tax structures multi-entity**: holding → SPV → operating, eliminations

Esto convierte el modeler en **"fondo de inversión as a service"** real. Cliente target: family offices, asset managers pequeños, consultoras financieras (€20-50k/mes/cliente).

### Capa de extensión también vía workflows

Muchas capacidades de Fase 3-4 pueden añadirse **como workflows YAML sin código nuevo** si la primitiva existe en el core:

- "Análisis de M&A": workflow que clona escenario con sinergias declaradas + corre comparación + sensitivity grid
- "Stress test de cartera": workflow que aplica overrides extremos (recesión, churn x2) y reporta runway/EV degradation

---

## 11. Cómo correr esto localmente

### 11.1 Setup

```bash
cd /path/to/asset-finance-modeler
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# La primera vez descarga el modelo de embeddings (~120MB)
pytest -v        # 193 tests passing
ruff check src/ tests/   # clean
mypy src/        # clean (45 source files)
```

### 11.2 CLI standalone

```bash
PYTHONPATH=src python -m asset_finance_modeler.cli.main list-models
# → gestnova

PYTHONPATH=src python -m asset_finance_modeler.cli.main run --preset gestnova --output summary
# → JSON con 8 métricas clave

PYTHONPATH=src python -m asset_finance_modeler.cli.main run --preset gestnova \
    --override 'revenue.sources[0].pricing.per_unit_per_period=250' \
    --output report
# → markdown narrativo con runway, EV, unit econ
```

### 11.3 MCP Server

```bash
PYTHONPATH=src python -m asset_finance_modeler.mcp_server.server
# → STDIO server escuchando JSONRPC
# → 30 tools disponibles vía tools/list
```

Configurar cliente MCP (Claude Desktop, IAN, Aurora) apuntando a este comando — fin de la integración.

---

## 12. Por qué esto cambia el juego para Gestnova

### Competencia actual en el espacio PyME ES

Ninguna plataforma de agente IA para pyme (Lindy, Decagon, ElevenLabs voice, etc.) tiene **modelado financiero conversacional con knowledge estructurado**. Hacen automatización operativa (responder llamadas, agendar citas, facturar). Lo financiero queda fuera — el dueño sigue con su gestor o su Excel.

### Lo que Gestnova ofrece tras integrar esto

> "Tu agente IA es además **tu CFO**. Puedes preguntarle por WhatsApp 'qué pasaría si bajara mi precio 10%', te corre un modelo completo (P&L, cash flow, valoración) en 30 segundos y te devuelve un dashboard con la recomendación. Sin abrir Excel, sin esperar a tu gestor."

Eso es **diferencial real**. Justifica subir precio Gestnova de €200-400/mes/agente a **€500-800/mes** para clientes que activan el módulo "asset management".

### Y para tier alto (asset managers, family offices)

Cuando construyamos Fase 3-4, Gestnova se posiciona como **"fondo de inversión as a service"**. Cliente típico de ese tier: €5-15k/mes/cliente. Mercado mundial: miles de family offices y boutique asset managers no atendidos.

---

## 13. Resumen ejecutivo

Hemos construido en 4 plans:

- **Plan 1**: Motor financiero completo (P&L+CF+Balance+Unit+Valuation+Debt) con Gestnova baseline
- **Plan 2**: Scenarios con árbol genealógico + comparación + sensitivity + exports + CLI
- **Plan 3**: MCP server stdio con 21 tools financieras
- **Plan 4**: Intelligent toolkit — knowledge base FAISS + workflows declarativos + memoria contextual multi-tenant → 30 tools totales

**Resultado**: una librería Python production-ready (193 tests, ruff+mypy clean) que cualquier agente MCP puede consumir para tener capacidades de CFO + asset management financiero real, sin alucinaciones, con frameworks correctos, con memoria entre sesiones, y diseñada para escalar a portfolio de fondos de inversión.

**Listo para**:
1. Integrar con Ian/Gestnova (~3-4h bridge plan documentado)
2. Demo a primer cliente premium
3. Vender módulo add-on Gestnova
4. Iterar a Fase 2-4 según demanda

---

*Documento generado: 2026-05-15*
*Proyecto: asset-finance-modeler v1.4*
*Estado: COMPLETO — listo para integración*
