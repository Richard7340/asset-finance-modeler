# asset-finance-modeler — Design Spec

**Date:** 2026-05-14
**Author:** Aurora (con Riky)
**Status:** Draft — pending user review
**Scope:** Sub-proyecto 1 de una suite mayor de herramientas financieras

---

## 1. Overview

`asset-finance-modeler` es una herramienta Python que expone un **motor de modelado financiero comprehensive** como **MCP server (stdio)**. Su primer caso de uso es **Gestnova** (negocio SaaS), pero está diseñada desde el primer commit para escalar a cualquier tipo de activo (renovables, real estate, business genérico).

El consumidor primario en V1 es el agente Ian (Gestnova) — vía MCP connector — pero el modeler es agnóstico: cualquier agente (Aurora, scripts, otros) puede invocar las mismas tools.

### Visión a largo plazo (no V1)

Suite de tools financieras:
- `finance.simulate.*` — modelo prospectivo desde inputs declarados (V1)
- `finance.track.*` — seguimiento real del activo, reconciliación, varianza (V2)
- `finance.value.*` — valoración de activos terceros (M&A, due diligence) (V3+)

---

## 2. Goals & Non-Goals

### Goals (V1)

1. Modelar el negocio de Gestnova **end-to-end** con suficiente detalle para tomar decisiones reales sobre pricing, runway, unit economics y valoración.
2. Schema declarativo **comprehensive** que cubra P&L + Cash Flow + Balance + deuda + impuestos + valoración + multi-currency.
3. Sistema de **scenarios** con **árbol genealógico** (cualquier scenario puede ser parent de otro).
4. **Persistencia local** (SQLite) de scenarios + resultados cacheados.
5. **MCP tools** que un agente LLM pueda usar conversacionalmente.
6. **Outputs estructurados** (JSON / CSV / XLSX / Markdown). UI rendering es responsabilidad del consumidor (Ian / Gestnova artifacts).
7. **Web search hook** para que el agente rellene inputs con benchmarks externos (churn p50, FX rates, tipos de interés).
8. Diseño modular: añadir un nuevo asset type = nueva carpeta `assets/<type>/` con schema + mapper. Core inalterado.

### Non-Goals (V1)

- UI / dashboard / artifacts (lo hace Gestnova/Ian).
- Lectura en vivo de contabilidad real (Holded, banca, etc.) — explícitamente excluido por Riky.
- ML / forecasting estadístico sobre series reales.
- Monte Carlo y simulación estocástica (posible V2).
- Otros asset types además de SaaS — pero la **arquitectura debe permitirlo sin tocar el core**.
- Multi-tenant / authentication — uso local single-user en V1.

---

## 3. Architecture

### Repo layout

```
asset-finance-modeler/
├── pyproject.toml
├── README.md
├── docs/
│   └── superpowers/
│       ├── specs/                       # design specs
│       └── plans/                       # implementation plans
├── src/asset_finance_modeler/
│   ├── core/                            # motor agnóstico al asset type
│   │   ├── time_grid.py                 # TimeGrid (periods, frequency, anchor date)
│   │   ├── statements.py                # PnL, CashFlow, Balance computados
│   │   ├── drivers.py                   # primitives: GrowthCurve, Cohort, ChurnCurve, AmortizationSchedule
│   │   ├── valuation.py                 # DCF, NPV, IRR, multiples, sensitivity
│   │   ├── scenario.py                  # Scenario class + override application
│   │   └── currency.py                  # multi-currency conversion + inflation deflator
│   ├── assets/
│   │   ├── saas/
│   │   │   ├── schema.py                # SaasModelConfig (pydantic v2)
│   │   │   ├── model.py                 # SaasModel — mapea SaasModelConfig → core
│   │   │   └── presets/
│   │   │       └── gestnova.yaml        # baseline real de Gestnova
│   │   └── __init__.py                  # AssetRegistry para futuro
│   ├── store/
│   │   ├── scenarios.py                 # ScenarioStore (SQLite) — interfaz abstracta
│   │   └── exports.py                   # to_csv, to_xlsx, to_markdown, to_json
│   ├── mcp_server/
│   │   ├── server.py                    # MCP stdio entrypoint
│   │   ├── tools/
│   │   │   ├── simulate.py              # finance.simulate.* (V1)
│   │   │   └── track.py                 # finance.track.* (stubs)
│   │   └── prompts.py                   # tool descriptions optimizadas para LLM
│   └── external/
│       └── delegation.py                # protocolo fetch_external/set_external (NO hace HTTP)
└── tests/
    ├── unit/                            # core, drivers, valuation
    ├── golden/                          # snapshot tests para cálculos críticos
    └── integration/                     # MCP server end-to-end
```

### Stack

- Python 3.12
- `pydantic` v2 — schema + validación
- `pandas` — series temporales internas
- `numpy_financial` — NPV, IRR, payback
- `openpyxl` — XLSX export
- `mcp` SDK oficial Anthropic — stdio server
- `pytest` + `pytest-snapshot` — testing
- `ruff` + `mypy` — quality gates

### Capas y dependencias (en orden, sin ciclos)

```
mcp_server  →  store  →  assets.saas  →  core
                                  ↘    ↗
                                    external (interfaz)
```

`core` no importa nada de `assets/`. `assets/saas/` traduce su schema a llamadas core. `mcp_server/` orquesta.

---

## 4. Schema completo — `SaasModelConfig`

Todo en pydantic v2 con descripciones semánticas. Cada `Field(description=...)` se usa para que el agente sepa **qué pedirle al usuario** cuando un valor falta.

### 4.1 `meta`

```python
class ModelMeta(BaseModel):
    name: str                              # "gestnova"
    base_currency: str = "EUR"             # ISO 4217
    fx_rates: dict[str, float] = {}        # opcional, agente puede poblar via web
    inflation_annual: float = 0.025
    horizon: HorizonConfig
    start_date: date                       # primer periodo del modelo
    initial_cash: float

class HorizonConfig(BaseModel):
    periods: int                           # 60 o 40 etc.
    frequency: Literal["M", "Q", "Y"]      # mensual, trimestral, anual
```

### 4.2 `revenue`

```python
class RevenueConfig(BaseModel):
    sources: list[RevenueSource]

class RevenueSource(BaseModel):
    name: str
    pricing: PricingConfig
    acquisition: AcquisitionConfig
    retention: RetentionConfig

class PricingConfig(BaseModel):
    per_unit_per_period: float             # €/agente/mes
    setup_one_time: float = 0
    price_escalation_annual: float = 0     # subida automática anual

class AcquisitionConfig(BaseModel):
    new_units_per_period: list[float] | float | GrowthCurve
    avg_units_per_customer: float = 1.0    # ej. 2.5 agentes/cliente Gestnova
    cac_per_customer: float
    cac_payback_target_months: int = 12    # informativo

class RetentionConfig(BaseModel):
    monthly_churn_rate: float              # gross logo churn
    gross_revenue_retention: float = 1.0
    expansion_revenue_pct: float = 0       # net dollar retention extra
```

`GrowthCurve` es un driver con tipos: `linear`, `s_curve`, `step`, `geometric`.

### 4.3 `cost_of_revenue` (COGS)

```python
class COGSConfig(BaseModel):
    per_active_unit: PerUnitCosts          # por agente activo
    per_active_customer: PerCustomerCosts

class PerUnitCosts(BaseModel):
    llm_tokens: list[LLMTier]              # desglose por modelo
    stt: VoiceProviderCost | None = None
    tts: VoiceProviderCost | None = None
    twilio: TwilioCost | None = None
    infra_eur: float = 0

class LLMTier(BaseModel):
    model: str                             # "sonnet-4-7", "haiku-4-5", "gemini-flash"
    eur_per_million_input: float
    eur_per_million_output: float
    avg_tokens_in_per_month: float
    avg_tokens_out_per_month: float

class VoiceProviderCost(BaseModel):
    provider: str
    eur_per_minute: float | None = None    # STT
    eur_per_million_chars: float | None = None  # TTS
    monthly_usage: float                   # minutos o chars según provider

class TwilioCost(BaseModel):
    whatsapp_eur_per_msg: float
    voice_eur_per_min: float
    msgs_per_month: float
    min_per_month: float

class PerCustomerCosts(BaseModel):
    support_eur: float = 0
    onboarding_one_time_eur: float = 0
```

### 4.4 `operating_expenses`

```python
class OpexConfig(BaseModel):
    team: list[TeamRole]
    infra_fixed_eur: float = 0
    marketing_eur: float | list[float] = 0     # constante o serie
    legal_admin_eur: float = 0
    other_eur: float = 0

class TeamRole(BaseModel):
    role: str
    monthly_cost: float                        # bruto + SS empresa
    headcount: int | None = None               # constante
    headcount_schedule: list[int] | None = None  # ramp explícito
    start_period: int = 0
    end_period: int | None = None              # None = hasta el final
```

Validador: `headcount` y `headcount_schedule` son mutuamente excluyentes.

### 4.5 `capital`

```python
class CapitalConfig(BaseModel):
    capex_schedule: list[CapExItem] = []
    working_capital: WorkingCapital
    funding_rounds: list[FundingRound] = []
    debt: list[DebtInstrument] = []

class WorkingCapital(BaseModel):
    days_sales_outstanding: int = 30
    days_payable_outstanding: int = 30
    days_inventory: int = 0                    # SaaS = 0

class FundingRound(BaseModel):
    period: int
    amount: float
    type: str                                  # "pre_seed", "seed", "series_a"
    dilution: float                            # 0-1
    valuation_pre: float | None = None

class DebtInstrument(BaseModel):
    name: str
    principal: float
    drawdown_period: int
    interest_rate_annual: float
    term_months: int
    grace_period_months: int = 0
    amortization: Literal["french", "bullet", "linear", "custom"]
    custom_schedule: list[float] | None = None
    origination_fee_pct: float = 0

class CapExItem(BaseModel):
    name: str
    amount: float
    period: int
    depreciation_years: int
```

### 4.6 `taxes`

```python
class TaxesConfig(BaseModel):
    corporate_income_tax_rate: float = 0.25
    vat_rate: float = 0.21
    payroll_taxes_pct: float = 0.30
    r_and_d_deduction_pct: float = 0
    tax_loss_carryforward: bool = True         # España SÍ
```

### 4.7 `valuation`

```python
class ValuationConfig(BaseModel):
    discount_rate_annual: float
    terminal_growth_rate: float = 0.025
    exit_multiple_arr: float | None = None
    exit_multiple_ebitda: float | None = None
    terminal_method: Literal["gordon", "exit_multiple"] = "gordon"
    sensitivity_grid: SensitivityGrid | None = None

class SensitivityGrid(BaseModel):
    wacc: list[float]
    growth: list[float]
```

### 4.8 `external_data`

```python
class ExternalDataConfig(BaseModel):
    benchmarks: dict[str, ExternalValue] = {}
    fx_source: str | None = None
    bond_yields_source: str | None = None

class ExternalValue(BaseModel):
    value: float
    source: str | None = None
    fetched_at: datetime | None = None
    confidence: Literal["low", "medium", "high"] = "medium"
```

---

## 5. Engine semantics — qué calcula y cómo

### 5.1 Cohort-based revenue (correcto para SaaS)

Cada `new_units_per_period[t]` crea una **cohorte**. Cada cohorte tiene retention curve = `(1 - monthly_churn_rate) ^ months_since_acquisition`. Active units en periodo T = suma de cohortes vivas × `avg_units_per_customer`. Revenue = active_units × price + setup_fees en mes de adquisición.

### 5.2 P&L (income statement) por periodo

```
Revenue (subscription + setup)
- COGS (LLM + voice + Twilio + infra variable + support)
= Gross Profit
- OPEX (team + marketing + infra fixed + legal/admin + other)
= EBITDA
- Depreciation & Amortization (de capex schedule)
= EBIT
- Interest Expense (de tabla de amortización deuda)
+ Interest Income (sobre cash position, opcional)
= EBT (Earnings Before Taxes)
- Tax (aplicando carryforward si está habilitado)
= Net Income
```

### 5.3 Cash Flow (método indirecto)

```
Net Income
+ D&A (non-cash)
± Δ Working Capital (AR/AP)
= CFO (Cash Flow from Operations)

- CapEx
= CFI (Cash Flow from Investing)

+ Funding round drawdowns
+ Debt drawdowns
- Debt principal repayments
- Origination fees
= CFF (Cash Flow from Financing)

Cash[t] = Cash[t-1] + CFO + CFI + CFF
```

### 5.4 Balance simplificado

`Cash + AR (=DSO/30 × revenue) + Fixed Assets (net of depreciation) = Equity + Debt outstanding + AP (=DPO/30 × COGS)`. Útil para sanity check y para ratios.

### 5.5 Unit economics

- **ARPU** = revenue / active customers
- **CAC** = total acquisition cost / new customers
- **LTV** = ARPU × gross_margin / monthly_churn_rate
- **LTV/CAC**
- **Payback months** = CAC / (ARPU × gross_margin)
- **Magic Number** = (ΔARR_quarter × 4) / sales_marketing_spend_prev_quarter
- **Rule of 40** = revenue_growth_yoy + ebitda_margin

### 5.6 Runway

`runway_months = min(t : Cash[t] < 0)` o `inf` si nunca cruza cero. También burn_rate (mensual de los últimos 3 meses).

### 5.7 Valuation

- **DCF**: descuenta FCF (= CFO − CapEx) a WACC. Terminal value vía Gordon `FCF_terminal × (1+g) / (WACC − g)` o vía exit multiple sobre ARR/EBITDA terminal. Suma PV(FCF) + PV(TV).
- **NPV / IRR del founder**: aplicando dilución de funding rounds.
- **Sensitivity grid**: tabla 2D NPV por (WACC × growth) — heatmap-ready.

### 5.8 Debt metrics

- **DSCR** = EBITDA / (interest + principal) por periodo
- **Interest Coverage** = EBIT / Interest Expense
- **Leverage** = Debt outstanding / EBITDA

---

## 6. Scenarios

### 6.1 Modelo conceptual

Un `Scenario` es **inmutable** después de creado: snapshot de inputs resueltos + resultados cacheados. Mutar = clonar con overrides.

```python
class Scenario(BaseModel):
    id: str                          # "scn-2026-05-14-a3f2c1"
    name: str
    description: str
    base_model: str                  # "gestnova"
    parent_scenario_id: str | None
    overrides: dict[str, Any]        # JSONPath → new value
    inputs_snapshot: dict            # config completo resuelto (frozen)
    results_snapshot: dict           # cálculos cacheados (frozen)
    created_at: datetime
    tags: list[str]
    notes: str
    is_canonical: bool = False       # baselines oficiales — no se pueden eliminar
```

### 6.2 Overrides (sintaxis JSONPath simple)

```python
overrides = {
    "revenue.sources[0].pricing.per_unit_per_period": 250,
    "revenue.sources[0].acquisition.new_units_per_period": [3,5,8,10,12],
    "capital.debt[0].principal": 300000,
}
```

Resolver: `jsonpath_ng` para parse, recursive set sobre dict resuelto. Validación post-aplicación re-corre `SaasModelConfig.model_validate(...)`.

### 6.3 Genealogía — árbol completo

Cualquier scenario puede ser parent de otro. Recorrer ancestors permite mostrar "este scenario = baseline + 3 cambios encadenados". UI puede renderizar como tree (CLI / dashboard externos).

### 6.4 Persistencia — SQLite

`store/scenarios.db` en `XDG_DATA_HOME/asset-finance-modeler/` o `~/.asset-finance-modeler/`.

Schema:
```sql
CREATE TABLE scenarios (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  base_model TEXT NOT NULL,
  parent_scenario_id TEXT REFERENCES scenarios(id),
  overrides_json TEXT,
  inputs_snapshot_json TEXT,
  results_snapshot_json TEXT,
  created_at TIMESTAMP,
  tags_json TEXT,
  notes TEXT,
  is_canonical INTEGER DEFAULT 0,
  is_deleted INTEGER DEFAULT 0
);
CREATE INDEX idx_parent ON scenarios(parent_scenario_id);
CREATE INDEX idx_base_model ON scenarios(base_model);
```

Interfaz `ScenarioStore` abstracta — drop-in para Postgres futuro.

---

## 7. MCP Tools Surface

### 7.1 Namespace `finance.simulate.*` (V1)

| Tool | Args | Returns |
|---|---|---|
| `list_models` | — | `[{name, description, asset_type}]` |
| `describe_schema` | `model: str` | JSON schema completo con field descriptions |
| `list_presets` | `model: str` | `[{key, name, description}]` |
| `load_baseline` | `model: str, preset: str` | `scenario_id` |
| `create_scenario` | `name, base_scenario_id, overrides, notes?` | `scenario_id` |
| `clone_scenario` | `scenario_id, name, overrides?` | `new_scenario_id` |
| `run` | `scenario_id` | `summary: dict` (8-10 metrics clave) |
| `get_results` | `scenario_id, view: "pnl"\|"cashflow"\|"balance"\|"unit_econ"\|"valuation"\|"summary"\|"all"` | dict / table |
| `compare` | `scenario_ids: list[str], metrics?: list[str]` | tabla delta |
| `sensitivity_1d` | `scenario_id, variable: jsonpath, values: list[float], metric` | `[{value, metric_value}]` |
| `sensitivity_grid` | `scenario_id, var_x, values_x, var_y, values_y, metric` | matrix 2D |
| `export` | `scenario_id, format: "csv"\|"xlsx"\|"json"\|"markdown", view?` | `{path, bytes_b64?}` |
| `fetch_external` | `scenario_id, field_path, query, hint?` | `{query, field_path, hint}` — devuelve instrucción para que el agente caller ejecute WebSearch |
| `set_external` | `scenario_id, field_path, value, source, confidence?` | `{ok: bool}` — el agente caller usa esto para devolver el valor encontrado |
| `list_scenarios` | `filter?: {base_model?, tags?, since?}` | `[{id, name, created_at, tags, parent}]` |
| `get_genealogy` | `scenario_id` | árbol de ancestros y descendientes |
| `delete_scenario` | `scenario_id` | `{ok: bool}` — falla si is_canonical |
| `set_canonical` | `scenario_id, name` | `{ok: bool}` |

### 7.2 Namespace `finance.track.*` (V2 stubs)

`import_real_data`, `reconcile`, `variance_report` — registradas en V1 pero devuelven error `NotImplementedError: V2 surface`. Esto permite que el agente conozca el camino y el documenting plan.

### 7.3 Cómo `fetch_external` funciona en práctica

`fetch_external` **no** hace HTTP por sí mismo (el modeler no tiene credenciales web). En cambio:

1. Devuelve al agente caller un payload tipo: `{"query": "average SaaS churn rate B2B 2025", "field_path": "external_data.benchmarks.saas_churn_p50", "hint": "look for industry reports 2024-2025"}`
2. El agente (Ian) ejecuta su propia tool `WebSearch` (que ya existe en Gestnova).
3. Llama de vuelta a `finance.simulate.set_external(scenario_id, field_path, value, source)`.

Esto desacopla credenciales y mantiene el modeler portable.

---

## 8. Outputs

| Format | Use case | Implementación |
|---|---|---|
| `summary` (JSON) | Default — agente recita 8-10 métricas en chat | dict pequeño hardcoded |
| `markdown_table` | Tabla en chat WhatsApp | pandas → markdown |
| `csv` | "Mándame el cash flow en CSV" | pandas.to_csv |
| `xlsx` | "Quiero verlo en Excel" | openpyxl multi-sheet (P&L / CF / Balance / Unit econ / Inputs) |
| `json` (full series) | Para que Ian renderice **artifact dashboard** | dict con todas las series por periodo |
| `markdown_report` | Email — texto narrativo con highlights | Jinja2 template |
| `pdf_report` | NO — lo hace Gestnova via DocumentTemplate (v2.1c) | El modeler entrega `json` + `markdown_report`; Gestnova compone el PDF |

**Invariante**: el modeler nunca renderiza UI/HTML/PDF. Solo datos.

---

## 9. Integration con Gestnova/Ian (bridge plan)

Trabajo en `livekit-voice-platform` cuando el modeler esté listo (estimación 3-4h según sesión paralela):

1. **MCP connector** en `agent-gestnova-ian` apuntando a `asset-finance-modeler` stdio binary. ~30 LoC.
2. **Skill `financial-analysis`** en `src/skills/core/financial-analysis.skill.ts` exponiendo las tools del modeler con descriptions LLM-friendly.
3. **Prompt update** — Ian aprende:
   - Cuándo declarar supuestos vs usar datos reales (Expenses/Invoices/Customers de Prisma)
   - Cuándo devolver dashboard artifact vs CSV vs PDF
   - Patrón conversacional: pedir inputs missing → load_baseline → create_scenario → run → export/render
4. **Helper `buildModelInputsFromCompanyData`** que extrae Expenses/Invoices/Customers de Prisma y los formatea como inputs SaasModelConfig parciales. Para cuando Ian use datos reales.
5. **Tests + smoke**: "Ian, simula Gestnova con bajada a 250€/agente. Mándame el cash flow en Excel" → cadena end-to-end verificada.

---

## 10. Future scope (V2/V3 — fuera de este spec)

- **Asset types adicionales**:
  - `assets/renewables/` (LCOE, PPA pricing, project finance con SPV)
  - `assets/real_estate/` (rental yield, cap rate, ICR, LTV)
  - `assets/generic_business/` (P&L genérico no-SaaS)
- **`finance.track.*`** completo — reconciliación con contabilidad real
- **Monte Carlo** sobre variables clave (churn, growth)
- **Optimización**: dado objective (max NPV / min runway), encuentra pricing óptimo
- **Postgres backend** para multi-tenant (cuando Gestnova ofrezca esto a clientes)

---

## 11. Testing strategy

### 11.1 Unit tests

- `core/drivers.py`: GrowthCurve shapes, AmortizationSchedule (french vs bullet vs linear) contra valores cerrados conocidos
- `core/valuation.py`: DCF vs valores Excel calculados manualmente
- `assets/saas/model.py`: cohort retention math, unit econ formulas

### 11.2 Golden tests (snapshot)

Carga `presets/gestnova.yaml`, corre el modelo, compara JSON resultado contra snapshot guardado. Cualquier cambio en motor que altere outputs reales rompe el test.

### 11.3 Integration tests

- MCP server stdio: spawn server, mandar tools/call, verificar shape de respuesta
- End-to-end scenario flow: load_baseline → create_scenario → run → compare → export

### 11.4 Quality gates

- `ruff check` clean
- `mypy --strict` clean en `core/` y `assets/`
- Coverage > 80% en `core/` y `assets/saas/`

---

## 12. Open questions / risks

1. **Granularidad de cohorts**: ¿guardamos retention curve por cohorte individual o solo agregada? Para Gestnova con churn flat, agregada vale. Cuando modelamos expansion revenue, cohort-level se vuelve necesario. **Decisión V1**: agregada con escape hatch para cohort-level.
2. **Working capital signo**: convención contable estricta (Δ AR positivo = uso de cash) — fácil bug. Tests específicos.
3. **Tax loss carryforward**: en España hay límite del 70% de base imponible positiva. Modelado simple en V1; afinable.
4. **Override JSONPath sobre arrays**: `revenue.sources[0]` está bien para SaaS con 1 fuente. Si Gestnova añade consultoría, hay que poder targetear `sources[name='consulting']`. `jsonpath_ng` lo soporta.
5. **MCP stdio binary**: ¿se instala como `pipx install asset-finance-modeler` y se invoca con `asset-finance-mcp`? Confirmar UX.
6. **Schema versioning**: cuando el schema cambie en V1.x, scenarios viejos deben seguir cargando. Añadir `schema_version` en `meta` desde el principio.

---

## 13. Resumen ejecutivo

Un repo Python nuevo (`asset-finance-modeler`) que expone via MCP stdio un motor financiero completo y declarativo. V1 enfocado en Gestnova SaaS, arquitectura preparada para añadir renovables, real estate y otros sectores sin tocar el core. El agente Ian (Gestnova) lo consumirá vía MCP connector — bridge plan documentado de 3-4h cuando el modeler esté funcional. Output siempre estructurado (datos); rendering de dashboards/PDFs es responsabilidad del consumer.

**Próximo paso**: escribir el plan de implementación (`writing-plans` skill).
