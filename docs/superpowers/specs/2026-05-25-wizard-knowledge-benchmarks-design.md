# Wizard + Knowledge + Benchmarks — Design Spec

**Date**: 2026-05-25
**Status**: Approved
**Scope**: Intelligent wizard system with financial knowledge base, benchmark lookup, and guided questioning for the asset-finance-modeler
**Depends on**: Infrastructure Module (Plans 1-3, complete)

## Overview

Add an intelligent wizard layer on top of the existing financial engine (359 tests, 31 MCP tools, 7+ production types). The wizard asks the right questions, proposes benchmark data when the user doesn't know, adapts to the user's expertise level, and produces a fully traceable scenario with provenance on every input.

**Approach**: Knowledge-Driven Wizard (Enfoque A). The wizard engine is a generic orchestrator — all intelligence comes from a 4-layer knowledge base. New sectors = new KB entries, not new code.

**Users**: Adapts to both financial analysts (fast, technical) and non-financial users (guided, explanatory). Detects expertise from responses.

**Data sources**: KB local first (curated IRENA/Lazard/BNEF), internet fallback (web search, capped at 0.6 confidence). Always shows source + confidence.

## Architecture

### Knowledge Base — 4 Separate Layers

Each layer has a different lifecycle, maintainer, and schema:

```
intelligence/knowledge/data/
  concepts/           # Domain knowledge (DSCR, IRR, MACRS explanations)
    solar_pv.yaml
    wind.yaml
    bess.yaml
    hydrogen.yaml
    real_estate.yaml
    corporate_ma.yaml
    generic.yaml      # Fallback for unknown sectors
  benchmarks/         # Market data with versioning
    capex.yaml
    opex.yaml
    pricing.yaml
    financing.yaml
  questions/          # Question templates per asset type
    solar_pv.yaml
    wind.yaml
    bess.yaml
    hydrogen.yaml
    datacenter.yaml
    real_estate.yaml
    corporate_ma.yaml
    generic.yaml      # Minimal questions for any asset
  validations/        # Ranges and sanity checks
    ranges.yaml
  presets/            # Quick-start scenarios
    quick_start.yaml
  intents/            # NL → asset_type mapping
    asset_recognition.yaml
```

| Layer | What it stores | Maintainer | Lifecycle |
|-------|---------------|------------|-----------|
| Concepts | Financial explanations, formulas, context | Technical editor | Near-static |
| Benchmarks | Numeric values with source + confidence + versioning | Financial analyst | Every 6 months |
| Questions | Ordered templates with options, dependencies, help text | UX designer | Stable |
| Validations | Valid ranges per field, sanity checks | Analyst + engineer | Quarterly |

### Benchmark Entry Schema

```yaml
- field: capex_per_kwp_eur
  asset_type: solar_pv
  region: ES
  value: 550
  valid_from: 2026-01-01
  valid_to: 2026-12-31
  source: "Lazard LCOE v17.0"
  confidence: 0.92
  source_url: "https://www.lazard.com/research-insights/lcoe"
  unit: EUR/kWp
  methodology: "EPC + grid connection, excludes land and dev costs"
  assumptions:
    - "utility-scale (>10 MWp)"
    - "Spanish irradiation 1700 kWh/kWp/yr"
    - "fixed-tilt, no tracker"
```

Required fields: `field`, `asset_type`, `value`, `valid_from`, `valid_to`, `source`, `confidence`, `unit`, `methodology`.

### Question Template Schema

```yaml
- field_path: production.capacity_mwp
  question: "¿Qué capacidad tiene la planta?"
  help_text: "Potencia pico instalada en megavatios. Utility-scale suele ser 10-200 MWp."
  options:
    - label: "10 MWp (pequeña)"
      value: 10
    - label: "50 MWp (media)"
      value: 50
    - label: "100 MWp (utility-scale)"
      value: 100
  required: true
  order: 1
  depends_on: null
  benchmark_key: null
  validation: "capacity_mwp.utility_scale_range"
  expert_only: false
  group: "production"
```

### Quick-Start Preset Schema

```yaml
- asset_type: solar_pv
  region: ES
  size_bracket: [10, 100]
  defaults:
    production.capacity_mwp: 50
    production.specific_yield_kwh_kwp: ref:benchmarks#specific_yield_solar_es
    capex.items[0].amount_per_unit: ref:benchmarks#capex_per_kwp_eur_solar_es
    opex.om_fixed_eur_per_mw_yr: ref:benchmarks#opex_fixed_solar_es
    degradation.annual_rate: 0.005
    financing.senior.dscr_target: 1.30
    financing.max_leverage: 0.75
    valuation.discount_rate_annual: 0.07
```

### Intent Recognition Schema

```yaml
- patterns: ["planta solar", "paneles fotovoltaicos", "FV", "PV", "solar", "fotovoltaica"]
  asset_type: solar_pv
- patterns: ["batería", "BESS", "almacenamiento eléctrico", "storage", "baterías"]
  asset_type: bess
- patterns: ["eólica", "viento", "wind", "aerogeneradores", "parque eólico"]
  asset_type: wind_onshore
- patterns: ["hidrógeno", "H2", "electrolizador", "electrolyzer", "green hydrogen"]
  asset_type: hydrogen
- patterns: ["data center", "centro de datos", "datacenter", "colocation", "hosting"]
  asset_type: data_center
- patterns: ["inmobiliario", "vivienda", "edificio", "real estate", "alquiler", "promoción"]
  asset_type: real_estate
- patterns: ["empresa", "negocio", "M&A", "adquisición", "fusión", "corporate"]
  asset_type: corporate_ma
```

### ResolvedInput — Core Dataclass

```python
@dataclass
class ResolvedInput:
    field_path: str
    value: float | str | bool | int
    source: Literal["user", "benchmark", "preset", "default", "internet"]
    provenance: str
    confidence: float
    benchmark_id: str | None = None
```

Every input in the final scenario carries provenance. The Assumptions Table in reports cites this.

## Wizard Engine — Orchestration Flow

```
1. User describes asset (NL text or structured)
2. Detect asset_type:
   a. Pattern match against intents/asset_recognition.yaml
   b. LLM fallback if no match
3. Load question template for asset_type (or generic fallback)
4. Search quick_start_preset for (asset_type, region, size_bracket)
5. If preset found:
   a. Resolve all ref: entries from benchmarks
   b. Present proposed scenario: "Here's a baseline for your 50MW solar in Spain. Any changes?"
   c. User adjusts specific inputs via wizard.adjust()
6. If no preset:
   a. Full question-by-question flow
   b. For each question (ordered, respecting depends_on):
      - Skip if depends_on not satisfied
      - Skip if expert_only and user detected as novato
      - Present question with options + "proponer otro valor"
      - If user says "no sé" → benchmark lookup (KB → internet)
      - Validate against validation rules
      - Store as ResolvedInput
7. Generate scenario_spec (all ResolvedInputs)
8. Present summary for review (wizard.finalize)
9. User confirms → create scenario + execute model (scenario.run)
```

### LLM-vs-KB Protocol (4 rules)

1. LLM **MUST NOT invent** numeric values. Only from: KB, internet trusted source, or user.
2. LLM **MUST NOT skip** questions marked `required: true`.
3. LLM **MAY reorder** questions if context justifies (e.g., user already mentioned capacity).
4. LLM **MAY paraphrase** questions but must maintain the `field_path` target.

## MCP Tools

### Wizard Tools (9 tools)

```
finance.wizard.start(asset_description: str, region: str | None)
  → Detect asset_type, load template, search quick_start
  → Returns: {session_id, asset_type, mode: "quick_start"|"full",
              proposed_inputs: list[ResolvedInput] (if quick_start),
              first_question: Question (if full),
              total_questions: int}

finance.wizard.answer(session_id: str, value: any)
  → Validate, store ResolvedInput
  → Returns: {next_question | completed: true, progress: {answered, total}}

finance.wizard.skip(session_id: str)
  → User doesn't know → search KB → internet → propose
  → Returns: {proposed_value, source, confidence, alternatives[],
              methodology, assumptions[]}

finance.wizard.back(session_id: str)
  → Go back to previous question, undo last ResolvedInput
  → Returns: {previous_question, current_answer}

finance.wizard.adjust(session_id: str, field_path: str, new_value: any)
  → Change a specific input (quick_start mode)
  → Re-validate, update ResolvedInput
  → Returns: {updated_input, validation_result}

finance.wizard.status(session_id: str)
  → Returns: {answered: int, pending: int, current_question,
              resolved_inputs: list[ResolvedInput]}

finance.wizard.cancel(session_id: str)
  → Discard session state
  → Returns: {cancelled: true}

finance.wizard.finalize(session_id: str)
  → Generate scenario_spec from all ResolvedInputs
  → Returns: {scenario_spec, assumptions_table, warnings[],
              confidence_summary: {high: N, medium: N, low: N}}

finance.wizard.run(session_id: str)
  → Create scenario in store, execute model
  → Returns: {scenario_id, summary, project_kpis, dashboard_url}
```

### Knowledge Tool (1 tool)

```
finance.knowledge.retrieve(topic: str, asset_type: str | None, region: str | None)
  → RAG search over all 4 KB layers via FAISS
  → Returns: top-k entries with score + full metadata
```

## Benchmark Lookup — Internet Fallback

When KB local doesn't have a benchmark for a given (field, asset_type, region):

1. **Search KB** (FAISS semantic + exact field match)
2. If found with confidence >= 0.7 → return
3. **Fallback: internet** via WebSearch
4. **LLM extracts** value + source from web results
5. **Multi-source consensus**: if web returns multiple values from different sources, show range to user instead of picking one
6. **Persist** extraction in KB with `unverified: true` for batch review later
7. **Cache** by (field, asset_type, region) with 7-day TTL

### Confidence Hierarchy

| Source | Confidence Range |
|--------|-----------------|
| User confirmed | 1.0 |
| Curated KB (IRENA, Lazard, BNEF) | 0.85-0.95 |
| Regulatory data (CNMC, FERC, ARERA) | 0.80-0.90 |
| Web search verified | 0.40-0.60 |
| Schema default | 0.30 |

Web extractions are capped at 0.6 confidence regardless of source quality.

### Evidence Storage

Web-sourced benchmarks store: URL, extraction date, snippet of source text. This provides audit trail if the source page changes later.

## Conversational Flow (Section 6)

### Paraphrasing Rules

The LLM reads question templates but paraphrases naturally in conversation. It must:
- Maintain the `field_path` target (the answer maps to the right schema field)
- Include help_text when user seems confused (detected by short/vague answers)
- Show options as presented in the template but can add context

### Batch Input Parsing

If the user provides multiple inputs at once ("solar de 50MW en Sevilla con PPA a 42€/MWh"), the wizard:
1. Extracts all identifiable inputs via LLM
2. Maps each to a field_path
3. Calls wizard.answer() for each in sequence
4. Skips those questions in the flow
5. Continues with remaining unanswered questions

### Auto-Default on "decide tú"

If the user says "como tú veas", "decide tú", or similar:
- The wizard accepts the benchmark/preset default for the current question
- Stores it as `source: "preset"` or `source: "benchmark"` (NOT "user")
- Confidence remains at the benchmark's level (not 1.0)
- Notes in provenance: "Auto-accepted by user delegation"

### Off-Topic Handling

If the user asks a conceptual question during the wizard ("¿qué es DSCR?"):
1. The wizard calls `finance.knowledge.retrieve("DSCR", asset_type)`
2. The LLM explains the concept using KB content
3. Returns to the current wizard question without losing state
4. Session state is preserved — no need to restart

### Confidence Transparency

Every time the wizard proposes a benchmark value, it says:
> "Te propongo 550 €/kWp basado en Lazard LCOE 2026 (confianza 92%, EPC + grid, utility-scale). ¿Te sirve o tienes mejor dato?"

If confidence < 0.6:
> "He encontrado un rango de 500-600 €/kWp de varias fuentes web (confianza 55%). Te recomiendo verificar con datos propios."

Confidence is NEVER hidden from the user.

### Expertise Detection

The wizard starts in "guided" mode (assumes non-expert). Switches to "expert" mode if:
- User provides technical terms unprompted (DSCR, LCOE, IRR, WACC)
- User skips help text and provides numeric values directly
- User says "skip the explanations" or similar

In expert mode:
- Questions are shorter, no help text
- `expert_only` questions are included
- Options show raw values without descriptions
- Batch input parsing is more aggressive

## Output — Assumptions Table

The wizard generates an Assumptions Table with every ResolvedInput:

| Input | Value | Source | Provenance | Confidence |
|-------|-------|--------|-----------|------------|
| Capacity | 50 MWp | User | User @ 2026-05-25 | 100% |
| CAPEX | 550 €/kWp | Benchmark | Lazard LCOE v17.0 | 92% |
| PPA Price | 42 €/MWh | User | User @ 2026-05-25 | 100% |
| O&M | 11,000 €/MW/yr | Benchmark | IRENA 2024 | 88% |
| Debt rate | 4.5% | Preset | solar_pv_50mw_spain default | 30% |

Disclaimer v1:
> "3 de 12 inputs provienen de benchmarks (confianza media). Para mayor precisión, verifique: CAPEX (Lazard 2026, 92%), O&M (IRENA 2024, 88%), tasa deuda (preset default, 30%). Los resultados son indicativos."

## File Structure

```
src/asset_finance_modeler/
  core/
    resolved_input.py    → NEW: ResolvedInput dataclass
  intelligence/
    knowledge/
      data/
        concepts/*.yaml   → NEW: domain knowledge per sector
        benchmarks/*.yaml → NEW: market data with versioning
        questions/*.yaml  → NEW: question templates per asset type
        validations/ranges.yaml → NEW: field validation ranges
        presets/quick_start.yaml → NEW: quick-start scenarios
        intents/asset_recognition.yaml → NEW: NL → asset_type
      retriever.py        → NEW: unified RAG retriever over 4 layers
    benchmarks/
      engine.py           → NEW: benchmark lookup with internet fallback
      cache.py            → NEW: 7-day cache for web queries
  wizard/
    engine.py             → NEW: WizardEngine (session state, flow control)
    session.py            → NEW: WizardSession (state per interaction)
    parser.py             → NEW: batch input parser (NL → field_path mapping)
  mcp_server/tools/
    wizard.py             → NEW: 9 wizard MCP tools
    knowledge_retrieve.py → NEW: knowledge.retrieve tool
    registry.py           ← MODIFY: register new tools

tests/unit/
  test_resolved_input.py
  test_wizard_engine.py
  test_wizard_session.py
  test_benchmark_engine.py
  test_knowledge_retriever.py
  test_wizard_mcp_tools.py
tests/integration/
  test_wizard_e2e.py
```

## KB Initial Construction

**Pipeline**: Semi-supervised agent ingestion.
1. Agent parses Lazard LCOE PDF, IRENA Power Generation Costs CSV
2. Normalizes to benchmark schema (field, value, source, confidence, etc.)
3. Proposes entries → analyst validates in batch
4. Pipeline becomes permanent infrastructure for KB refresh

**Seed data for v1**: Top 5 sectors (solar, wind, BESS, corporate, real estate) × key metrics (CAPEX, OPEX, financing terms, typical yields). ~100 curated benchmark entries + ~50 domain concepts.

## Post-MVP

- Monte Carlo uncertainty propagation (v2)
- Project memory and scenario versioning (separate spec)
- Professional PDF reports with cover page and disclaimers (separate spec)
- Wizard state persistence across sessions (DB table)
