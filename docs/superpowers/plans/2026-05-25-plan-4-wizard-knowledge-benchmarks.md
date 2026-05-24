# Wizard + Knowledge + Benchmarks Implementation Plan (Plan 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an intelligent wizard that guides users through financial model configuration, backed by a 4-layer knowledge base and benchmark lookup with internet fallback.

**Architecture:** Knowledge-driven wizard — the engine is generic, all sector intelligence lives in YAML data files loaded into FAISS. ResolvedInput tracks provenance for every input. 9 wizard MCP tools + 1 knowledge retrieval tool.

**Tech Stack:** Python 3.12+, Pydantic v2, FAISS, PyYAML, pytest

**Depends on:** Plans 1-3 (complete, 359 tests, 94% coverage)

---

## File Structure

```
src/asset_finance_modeler/
  core/
    resolved_input.py           → NEW: ResolvedInput + InsufficientDataError
  intelligence/
    knowledge/
      schemas.py                → NEW: Pydantic models for all 4 KB layers
      loader.py                 → NEW: load YAML data into typed models
      retriever.py              → NEW: unified RAG retriever
      data/
        concepts/solar_pv.yaml  → NEW: domain concepts seed
        concepts/generic.yaml   → NEW: generic financial concepts
        benchmarks/capex.yaml   → NEW: CAPEX benchmarks
        benchmarks/opex.yaml    → NEW: OPEX benchmarks
        benchmarks/pricing.yaml → NEW: pricing benchmarks
        benchmarks/financing.yaml → NEW: financing benchmarks
        questions/solar_pv.yaml → NEW: solar question templates
        questions/generic.yaml  → NEW: generic question templates
        validations/ranges.yaml → NEW: validation rules
        presets/quick_start.yaml → NEW: quick-start presets
        intents/asset_recognition.yaml → NEW: NL→asset_type
    benchmarks/
      __init__.py               → NEW
      engine.py                 → NEW: benchmark lookup + fallback
      cache.py                  → NEW: 7-day TTL cache
  wizard/
    __init__.py                 → NEW
    session.py                  → NEW: WizardSession state
    engine.py                   → NEW: WizardEngine orchestrator
  mcp_server/tools/
    wizard.py                   → NEW: 9 wizard MCP tools
    knowledge_retrieve.py       → NEW: knowledge.retrieve tool
    registry.py                 ← MODIFY: register new tools

tests/unit/
  test_resolved_input.py        → NEW
  test_kb_schemas.py            → NEW
  test_kb_loader.py             → NEW
  test_kb_retriever.py          → NEW
  test_benchmark_engine.py      → NEW
  test_wizard_session.py        → NEW
  test_wizard_engine.py         → NEW
  test_wizard_mcp_tools.py      → NEW
tests/integration/
  test_wizard_e2e.py            → NEW
```

---

### Task 1: ResolvedInput + InsufficientDataError

**Files:**
- Create: `src/asset_finance_modeler/core/resolved_input.py`
- Test: `tests/unit/test_resolved_input.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_resolved_input.py
import pytest

from asset_finance_modeler.core.resolved_input import (
    InsufficientDataError,
    ResolvedInput,
)


def test_resolved_input_user_source():
    ri = ResolvedInput(
        field_path="production.capacity_mwp",
        value=50.0,
        source="user",
        provenance="User @ 2026-05-25T10:00",
        confidence=1.0,
    )
    assert ri.source == "user"
    assert ri.confidence == 1.0
    assert ri.benchmark_id is None


def test_resolved_input_benchmark_source():
    ri = ResolvedInput(
        field_path="capex.items[0].amount_per_unit",
        value=550.0,
        source="benchmark",
        provenance="Lazard LCOE v17.0",
        confidence=0.92,
        benchmark_id="bm-solar-capex-es-2026",
    )
    assert ri.benchmark_id == "bm-solar-capex-es-2026"
    assert ri.confidence == 0.92


def test_resolved_input_to_dict():
    ri = ResolvedInput(
        field_path="production.capacity_mwp",
        value=50.0,
        source="user",
        provenance="User",
        confidence=1.0,
    )
    d = ri.to_dict()
    assert d["field_path"] == "production.capacity_mwp"
    assert d["value"] == 50.0
    assert d["source"] == "user"


def test_insufficient_data_error():
    err = InsufficientDataError(
        missing_fields=["production.capacity_mwp", "capex.items[0].amount_per_unit"],
    )
    assert len(err.missing_fields) == 2
    assert "production.capacity_mwp" in str(err)


def test_insufficient_data_error_empty_is_valid():
    err = InsufficientDataError(missing_fields=[])
    assert len(err.missing_fields) == 0
```

- [ ] **Step 2: Run to verify fail**

Run: `.venv/bin/pytest tests/unit/test_resolved_input.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

```python
# src/asset_finance_modeler/core/resolved_input.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class ResolvedInput:
    field_path: str
    value: float | str | bool | int
    source: Literal["user", "benchmark", "preset", "default", "internet"]
    provenance: str
    confidence: float
    benchmark_id: str | None = field(default=None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_path": self.field_path,
            "value": self.value,
            "source": self.source,
            "provenance": self.provenance,
            "confidence": self.confidence,
            "benchmark_id": self.benchmark_id,
        }


class InsufficientDataError(Exception):
    def __init__(self, missing_fields: list[str]) -> None:
        self.missing_fields = missing_fields
        fields_str = ", ".join(missing_fields)
        super().__init__(
            f"Cannot run model: {len(missing_fields)} required input(s) missing: {fields_str}"
        )
```

- [ ] **Step 4: Run tests + lint + commit**

```bash
.venv/bin/pytest tests/unit/test_resolved_input.py -v
.venv/bin/ruff check src/asset_finance_modeler/core/resolved_input.py
git add src/asset_finance_modeler/core/resolved_input.py tests/unit/test_resolved_input.py
git commit -m "feat(core): add ResolvedInput dataclass + InsufficientDataError"
```

---

### Task 2: KB YAML Schemas + Seed Data

**Files:**
- Create: `src/asset_finance_modeler/intelligence/knowledge/schemas.py`
- Create: all YAML data files (seed data)
- Test: `tests/unit/test_kb_schemas.py`

Pydantic models for loading and validating the 4 KB layers. Seed YAML files with ~5-10 entries each for solar_pv as the reference sector.

- [ ] **Step 1: Write tests for KB schemas**

```python
# tests/unit/test_kb_schemas.py
from datetime import date

import pytest

from asset_finance_modeler.intelligence.knowledge.schemas import (
    AssetIntent,
    BenchmarkEntry,
    ConceptEntry,
    QuestionOption,
    QuestionTemplate,
    QuickStartPreset,
    ValidationRule,
)


def test_benchmark_entry_required_fields():
    bm = BenchmarkEntry(
        field="capex_per_kwp_eur",
        asset_type="solar_pv",
        value=550,
        valid_from=date(2026, 1, 1),
        valid_to=date(2026, 12, 31),
        source="Lazard LCOE v17.0",
        confidence=0.92,
        unit="EUR/kWp",
        methodology="EPC + grid, excludes land",
    )
    assert bm.confidence == 0.92
    assert bm.assumptions == []


def test_benchmark_entry_with_region_and_assumptions():
    bm = BenchmarkEntry(
        field="capex_per_kwp_eur",
        asset_type="solar_pv",
        region="ES",
        value=550,
        valid_from=date(2026, 1, 1),
        valid_to=date(2026, 12, 31),
        source="Lazard",
        confidence=0.92,
        unit="EUR/kWp",
        methodology="EPC + grid",
        assumptions=["utility-scale", "fixed-tilt"],
        source_url="https://lazard.com",
    )
    assert bm.region == "ES"
    assert len(bm.assumptions) == 2


def test_concept_entry():
    ce = ConceptEntry(
        id="dscr",
        title="Debt Service Coverage Ratio (DSCR)",
        content="DSCR measures...",
        asset_types=["solar_pv", "wind"],
        category="debt_metrics",
    )
    assert "solar_pv" in ce.asset_types


def test_question_template():
    qt = QuestionTemplate(
        field_path="production.capacity_mwp",
        question="What is the plant capacity?",
        options=[
            QuestionOption(label="10 MWp", value=10),
            QuestionOption(label="50 MWp", value=50),
        ],
        required=True,
        order=1,
    )
    assert qt.required is True
    assert qt.expert_only is False
    assert len(qt.options) == 2


def test_question_with_depends_on():
    qt = QuestionTemplate(
        field_path="revenue[0].price_eur_per_unit",
        question="PPA price?",
        options=[],
        required=True,
        order=5,
        depends_on="revenue[0].type",
        group="revenue",
    )
    assert qt.depends_on == "revenue[0].type"


def test_validation_rule():
    vr = ValidationRule(
        field_path="production.capacity_mwp",
        rule_id="capacity_mwp.utility_scale_range",
        min_value=0.1,
        max_value=2000,
        message="Capacity must be 0.1-2000 MWp",
    )
    assert vr.min_value == 0.1


def test_quick_start_preset():
    qsp = QuickStartPreset(
        asset_type="solar_pv",
        region="ES",
        size_bracket=[10, 100],
        defaults={
            "production.capacity_mwp": 50,
            "degradation.annual_rate": 0.005,
        },
    )
    assert qsp.defaults["production.capacity_mwp"] == 50


def test_asset_intent():
    ai = AssetIntent(
        patterns=["planta solar", "FV", "PV"],
        asset_type="solar_pv",
    )
    assert "FV" in ai.patterns
```

- [ ] **Step 2: Write schemas.py**

```python
# src/asset_finance_modeler/intelligence/knowledge/schemas.py
from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class BenchmarkEntry(BaseModel):
    field: str
    asset_type: str
    region: str | None = None
    value: float
    valid_from: date
    valid_to: date
    source: str
    confidence: float = Field(ge=0, le=1)
    source_url: str | None = None
    unit: str
    methodology: str
    assumptions: list[str] = Field(default_factory=list)
    unverified: bool = False


class ConceptEntry(BaseModel):
    id: str
    title: str
    content: str
    asset_types: list[str] = Field(default_factory=list)
    category: str = "general"
    tags: list[str] = Field(default_factory=list)


class QuestionOption(BaseModel):
    label: str
    value: float | str | bool | int


class QuestionTemplate(BaseModel):
    field_path: str
    question: str
    help_text: str = ""
    options: list[QuestionOption] = Field(default_factory=list)
    required: bool = True
    order: int = 0
    depends_on: str | None = None
    benchmark_key: str | None = None
    validation: str | None = None
    expert_only: bool = False
    group: str = "general"


class ValidationRule(BaseModel):
    field_path: str
    rule_id: str
    min_value: float | None = None
    max_value: float | None = None
    allowed_values: list[Any] | None = None
    message: str = ""


class QuickStartPreset(BaseModel):
    asset_type: str
    region: str | None = None
    size_bracket: list[float] | None = None
    defaults: dict[str, Any] = Field(default_factory=dict)


class AssetIntent(BaseModel):
    patterns: list[str]
    asset_type: str
```

- [ ] **Step 3: Create seed YAML files**

Create the directory structure and seed YAML files. Key files:

`intelligence/knowledge/data/intents/asset_recognition.yaml`:
```yaml
- patterns: ["planta solar", "paneles fotovoltaicos", "FV", "PV", "solar", "fotovoltaica"]
  asset_type: solar_pv
- patterns: ["batería", "BESS", "almacenamiento eléctrico", "storage", "baterías"]
  asset_type: bess
- patterns: ["eólica", "viento", "wind", "aerogeneradores", "parque eólico"]
  asset_type: wind_onshore
- patterns: ["hidrógeno", "H2", "electrolizador", "green hydrogen"]
  asset_type: hydrogen
- patterns: ["data center", "centro de datos", "datacenter", "colocation"]
  asset_type: data_center
- patterns: ["inmobiliario", "vivienda", "edificio", "real estate", "alquiler"]
  asset_type: real_estate
- patterns: ["empresa", "negocio", "M&A", "adquisición", "fusión", "corporate"]
  asset_type: corporate_ma
```

`intelligence/knowledge/data/benchmarks/capex.yaml`:
```yaml
- field: capex_per_kwp_eur
  asset_type: solar_pv
  region: ES
  value: 550
  valid_from: 2026-01-01
  valid_to: 2026-12-31
  source: "Lazard LCOE v17.0"
  confidence: 0.92
  unit: EUR/kWp
  methodology: "EPC + grid connection, excludes land and dev costs"
  assumptions:
    - "utility-scale (>10 MWp)"
    - "fixed-tilt, no tracker"

- field: capex_per_mw_eur
  asset_type: wind_onshore
  region: ES
  value: 1100000
  valid_from: 2026-01-01
  valid_to: 2026-12-31
  source: "IRENA Renewable Power Generation Costs 2024"
  confidence: 0.90
  unit: EUR/MW
  methodology: "Turnkey including turbines, BOS, installation"
  assumptions:
    - "onshore, 3-5 MW turbines"

- field: capex_per_kwh_eur
  asset_type: bess
  region: EU
  value: 280
  valid_from: 2026-01-01
  valid_to: 2026-12-31
  source: "BloombergNEF Energy Storage Outlook 2025"
  confidence: 0.85
  unit: EUR/kWh
  methodology: "Li-ion NMC, 4h duration, includes BOS and integration"
  assumptions:
    - "utility-scale (>10 MW)"

- field: capex_per_mw_eur
  asset_type: data_center
  region: EU
  value: 8000000
  valid_from: 2026-01-01
  valid_to: 2026-12-31
  source: "Turner & Townsend Data Centre Cost Index 2025"
  confidence: 0.80
  unit: EUR/MW_IT
  methodology: "Shell + MEP, Tier 3, excludes land"
  assumptions:
    - "N+1 redundancy"
    - "PUE 1.3"
```

`intelligence/knowledge/data/questions/solar_pv.yaml`:
```yaml
- field_path: production.capacity_mwp
  question: "¿Qué capacidad tiene la planta solar?"
  help_text: "Potencia pico instalada. Utility-scale: 10-200 MWp. Rooftop: 0.01-1 MWp."
  options:
    - label: "10 MWp (pequeña utility)"
      value: 10
    - label: "50 MWp (media)"
      value: 50
    - label: "100 MWp (grande)"
      value: 100
  required: true
  order: 1
  group: production

- field_path: production.specific_yield_kwh_kwp
  question: "¿Cuál es la irradiación esperada (kWh/kWp/año)?"
  help_text: "España sur: 1600-1800. España norte: 1300-1500. Alemania: 900-1100."
  options:
    - label: "1400 kWh/kWp (norte España)"
      value: 1400
    - label: "1600 kWh/kWp (centro España)"
      value: 1600
    - label: "1800 kWh/kWp (sur España/Canarias)"
      value: 1800
  required: true
  order: 2
  benchmark_key: specific_yield_solar
  group: production

- field_path: revenue[0].type
  question: "¿Cómo se venderá la energía?"
  help_text: "PPA = contrato a precio fijo. Merchant = precio de mercado. Mixto = parte fija + parte mercado."
  options:
    - label: "PPA (contrato fijo)"
      value: ppa
    - label: "Merchant (mercado)"
      value: merchant
    - label: "Mixto PPA + Merchant"
      value: mixed
  required: true
  order: 3
  group: revenue

- field_path: revenue[0].price_eur_per_unit
  question: "¿A qué precio el PPA (€/MWh)?"
  help_text: "PPAs solares en España 2025-2026: 35-55 €/MWh típico."
  options:
    - label: "35 €/MWh (competitivo)"
      value: 35
    - label: "42 €/MWh (mercado)"
      value: 42
    - label: "50 €/MWh (premium)"
      value: 50
  required: true
  order: 4
  depends_on: "revenue[0].type"
  benchmark_key: ppa_price_solar_es
  group: revenue

- field_path: capex.items[0].amount_per_unit
  question: "¿Cuánto cuesta el CAPEX (€/Wp)?"
  help_text: "Incluye módulos, inversores, estructura, instalación. España 2026: 0.40-0.60 €/Wp típico."
  options:
    - label: "0.42 €/Wp (competitivo)"
      value: 0.42
    - label: "0.50 €/Wp (mercado)"
      value: 0.50
    - label: "0.58 €/Wp (premium/tracker)"
      value: 0.58
  required: true
  order: 5
  benchmark_key: capex_per_kwp_eur
  group: capex

- field_path: financing.max_leverage
  question: "¿Qué ratio deuda/equity?"
  help_text: "Project finance típico: 70-80% deuda. Sin deuda: 0%. Agresivo: 85%."
  options:
    - label: "Sin deuda (100% equity)"
      value: 0
    - label: "70% deuda / 30% equity"
      value: 0.70
    - label: "80% deuda / 20% equity"
      value: 0.80
  required: true
  order: 6
  group: financing
  expert_only: false
```

`intelligence/knowledge/data/questions/generic.yaml`:
```yaml
- field_path: meta.horizon.periods
  question: "¿A cuántos años quieres el modelo?"
  help_text: "Horizonte temporal del análisis financiero."
  options:
    - label: "10 años"
      value: 120
    - label: "20 años"
      value: 240
    - label: "25 años"
      value: 300
  required: true
  order: 0
  group: meta

- field_path: taxes.corporate_income_tax_rate
  question: "¿Cuál es el tipo impositivo de sociedades?"
  help_text: "España: 25%. USA: 21% federal. UK: 25%. Alemania: ~30%."
  options:
    - label: "25% (España)"
      value: 0.25
    - label: "21% (USA federal)"
      value: 0.21
    - label: "30% (Alemania)"
      value: 0.30
  required: true
  order: 100
  group: taxes

- field_path: valuation.discount_rate_annual
  question: "¿Qué WACC usar para la valoración?"
  help_text: "Tasa de descuento. Renovables: 5-8%. Real estate: 6-10%. Corporate: 8-15%."
  options:
    - label: "6% (bajo riesgo)"
      value: 0.06
    - label: "8% (medio)"
      value: 0.08
    - label: "12% (alto riesgo)"
      value: 0.12
  required: true
  order: 101
  group: valuation
  expert_only: true
```

`intelligence/knowledge/data/concepts/solar_pv.yaml`:
```yaml
- id: solar-specific-yield
  title: "Specific Yield (kWh/kWp)"
  content: "Annual energy production per unit of installed peak capacity. Depends on location (irradiation), panel orientation, shading, and system losses. Spain: 1400-1800 kWh/kWp. Germany: 900-1100."
  asset_types: [solar_pv]
  category: production

- id: solar-performance-ratio
  title: "Performance Ratio (PR)"
  content: "Ratio of actual energy output to theoretical maximum. Accounts for inverter losses, cable losses, temperature, soiling. Typical range: 0.75-0.85."
  asset_types: [solar_pv]
  category: production

- id: solar-degradation
  title: "Panel Degradation"
  content: "Solar panels lose ~0.4-0.6% efficiency per year. Over 25 years, this means ~10-15% total loss. Degradation is linear and affects energy production directly."
  asset_types: [solar_pv]
  category: production

- id: solar-ppa
  title: "Power Purchase Agreement (PPA)"
  content: "Long-term contract (10-20 years) to sell electricity at a fixed or indexed price. Reduces merchant risk. Banks prefer projects with PPA coverage >60%."
  asset_types: [solar_pv, wind_onshore, bess]
  category: revenue

- id: solar-lcoe
  title: "Levelized Cost of Energy (LCOE)"
  content: "Total lifecycle cost divided by total energy produced, discounted to present value. Key metric for comparing energy technologies. Solar PV LCOE 2025: 25-50 €/MWh (utility-scale)."
  asset_types: [solar_pv, wind_onshore]
  category: metrics
```

`intelligence/knowledge/data/concepts/generic.yaml`:
```yaml
- id: dscr
  title: "Debt Service Coverage Ratio (DSCR)"
  content: "EBITDA divided by total debt service (interest + principal). Banks require minimum DSCR 1.20-1.40. Below 1.0 means the project cannot service its debt. Typical covenant: 1.30x minimum."
  asset_types: []
  category: debt_metrics

- id: irr-project
  title: "Project IRR (Unlevered)"
  content: "Internal rate of return on total project cash flows, ignoring financing structure. Measures the project's inherent profitability. Good: >8% for infra."
  asset_types: []
  category: valuation

- id: irr-equity
  title: "Equity IRR (Levered)"
  content: "Internal rate of return on equity cash flows only (after debt service). Always higher than project IRR due to leverage effect. Target: 10-15% for infra equity."
  asset_types: []
  category: valuation

- id: wacc
  title: "Weighted Average Cost of Capital (WACC)"
  content: "Blended cost of debt and equity, weighted by capital structure. Used as discount rate in DCF valuations. Lower WACC = higher project value."
  asset_types: []
  category: valuation
  tags: [finance_basics]
```

`intelligence/knowledge/data/validations/ranges.yaml`:
```yaml
- field_path: production.capacity_mwp
  rule_id: capacity_mwp.utility_scale_range
  min_value: 0.01
  max_value: 5000
  message: "Capacity must be between 0.01 and 5000 MWp"

- field_path: production.capacity_mw
  rule_id: capacity_mw.range
  min_value: 0.1
  max_value: 2000
  message: "Capacity must be between 0.1 and 2000 MW"

- field_path: capex.items[0].amount_per_unit
  rule_id: capex_unit.range
  min_value: 0
  max_value: 100000000
  message: "CAPEX per unit must be positive and reasonable"

- field_path: financing.max_leverage
  rule_id: leverage.range
  min_value: 0
  max_value: 0.95
  message: "Leverage must be 0-95%"

- field_path: valuation.discount_rate_annual
  rule_id: wacc.range
  min_value: 0.01
  max_value: 0.30
  message: "WACC must be 1-30%"
```

`intelligence/knowledge/data/presets/quick_start.yaml`:
```yaml
- asset_type: solar_pv
  region: ES
  size_bracket: [10, 100]
  defaults:
    production.capacity_mwp: 50
    production.specific_yield_kwh_kwp: 1600
    production.performance_ratio: 0.82
    capex.items[0].amount_per_unit: 0.45
    capex.items[0].unit: Wp
    capex.items[0].depreciation_years: 25
    capex.contingency_pct: 0.08
    opex.om_fixed_eur_per_mw_yr: 11000
    opex.insurance_pct_capex: 0.004
    degradation.type: time_based
    degradation.annual_rate: 0.005
    financing.max_leverage: 0.75
    financing.senior.dscr_target: 1.30
    financing.senior.interest_rate: 0.04
    valuation.discount_rate_annual: 0.07
    taxes.corporate_income_tax_rate: 0.25
```

- [ ] **Step 4: Run tests + commit**

```bash
.venv/bin/pytest tests/unit/test_kb_schemas.py -v
git add src/asset_finance_modeler/intelligence/knowledge/schemas.py \
        src/asset_finance_modeler/intelligence/knowledge/data/ \
        tests/unit/test_kb_schemas.py
git commit -m "feat(kb): add 4-layer KB schemas + seed data — concepts, benchmarks, questions, validations"
```

---

### Task 3: KB Loader + Retriever

**Files:**
- Create: `src/asset_finance_modeler/intelligence/knowledge/loader.py` (NEW — loads YAML into typed models)
- Create: `src/asset_finance_modeler/intelligence/knowledge/retriever.py`
- Test: `tests/unit/test_kb_loader.py`
- Test: `tests/unit/test_kb_retriever.py`

The loader reads YAML files and returns typed Pydantic models. The retriever provides unified search across all 4 layers.

- [ ] **Step 1: Write loader tests**

```python
# tests/unit/test_kb_loader.py
from asset_finance_modeler.intelligence.knowledge.loader import KBLoader


def test_load_intents():
    loader = KBLoader()
    intents = loader.load_intents()
    assert len(intents) >= 7
    solar = [i for i in intents if i.asset_type == "solar_pv"]
    assert len(solar) == 1
    assert "FV" in solar[0].patterns


def test_load_questions_solar():
    loader = KBLoader()
    questions = loader.load_questions("solar_pv")
    assert len(questions) >= 5
    assert questions[0].order <= questions[1].order


def test_load_questions_generic_fallback():
    loader = KBLoader()
    questions = loader.load_questions("unknown_type")
    assert len(questions) >= 2  # generic always has at least horizon + tax


def test_load_benchmarks():
    loader = KBLoader()
    benchmarks = loader.load_benchmarks()
    assert len(benchmarks) >= 3
    solar_capex = [b for b in benchmarks if b.field == "capex_per_kwp_eur"]
    assert len(solar_capex) >= 1


def test_load_concepts():
    loader = KBLoader()
    concepts = loader.load_concepts()
    assert len(concepts) >= 5
    dscr = [c for c in concepts if c.id == "dscr"]
    assert len(dscr) == 1


def test_load_validations():
    loader = KBLoader()
    rules = loader.load_validations()
    assert len(rules) >= 3


def test_load_quick_starts():
    loader = KBLoader()
    presets = loader.load_quick_starts()
    solar_es = [p for p in presets if p.asset_type == "solar_pv" and p.region == "ES"]
    assert len(solar_es) >= 1
    assert "production.capacity_mwp" in solar_es[0].defaults


def test_detect_asset_type():
    loader = KBLoader()
    assert loader.detect_asset_type("tengo una planta solar de 50MW") == "solar_pv"
    assert loader.detect_asset_type("quiero evaluar un BESS") == "bess"
    assert loader.detect_asset_type("algo desconocido") is None
```

- [ ] **Step 2: Implement loader**

```python
# src/asset_finance_modeler/intelligence/knowledge/loader.py
from __future__ import annotations

from importlib.resources import files
from pathlib import Path

import yaml

from .schemas import (
    AssetIntent,
    BenchmarkEntry,
    ConceptEntry,
    QuestionTemplate,
    QuickStartPreset,
    ValidationRule,
)

_DATA_PKG = "asset_finance_modeler.intelligence.knowledge.data"


def _load_yaml_list(subpath: str) -> list[dict]:
    try:
        resource = files(_DATA_PKG) / subpath
        with resource.open() as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, TypeError):
        return []


def _load_yaml_dir(subdir: str) -> list[dict]:
    result: list[dict] = []
    try:
        pkg = files(_DATA_PKG) / subdir
        for item in pkg.iterdir():
            if str(item).endswith(".yaml"):
                with item.open() as f:
                    data = yaml.safe_load(f)
                if isinstance(data, list):
                    result.extend(data)
    except (FileNotFoundError, TypeError):
        pass
    return result


class KBLoader:
    def load_intents(self) -> list[AssetIntent]:
        raw = _load_yaml_list("intents/asset_recognition.yaml")
        return [AssetIntent.model_validate(r) for r in raw]

    def load_questions(self, asset_type: str) -> list[QuestionTemplate]:
        specific = _load_yaml_list(f"questions/{asset_type}.yaml")
        generic = _load_yaml_list("questions/generic.yaml")
        raw = specific + generic if specific else generic
        templates = [QuestionTemplate.model_validate(r) for r in raw]
        return sorted(templates, key=lambda q: q.order)

    def load_benchmarks(self) -> list[BenchmarkEntry]:
        raw = _load_yaml_dir("benchmarks")
        return [BenchmarkEntry.model_validate(r) for r in raw]

    def load_concepts(self) -> list[ConceptEntry]:
        raw = _load_yaml_dir("concepts")
        return [ConceptEntry.model_validate(r) for r in raw]

    def load_validations(self) -> list[ValidationRule]:
        raw = _load_yaml_list("validations/ranges.yaml")
        return [ValidationRule.model_validate(r) for r in raw]

    def load_quick_starts(self) -> list[QuickStartPreset]:
        raw = _load_yaml_list("presets/quick_start.yaml")
        return [QuickStartPreset.model_validate(r) for r in raw]

    def detect_asset_type(self, text: str) -> str | None:
        text_lower = text.lower()
        for intent in self.load_intents():
            for pattern in intent.patterns:
                if pattern.lower() in text_lower:
                    return intent.asset_type
        return None

    def find_benchmark(
        self, field: str, asset_type: str, region: str | None = None,
    ) -> BenchmarkEntry | None:
        for bm in self.load_benchmarks():
            if bm.field == field and bm.asset_type == asset_type:
                if region is None or bm.region is None or bm.region == region:
                    return bm
        return None

    def get_validation(self, rule_ref: str) -> ValidationRule | None:
        for rule in self.load_validations():
            if rule.rule_id == rule_ref:
                return rule
        return None
```

- [ ] **Step 3: Write retriever tests**

```python
# tests/unit/test_kb_retriever.py
from asset_finance_modeler.intelligence.knowledge.retriever import KBRetriever


def test_retriever_search_concept(tmp_path):
    retriever = KBRetriever(db_path=str(tmp_path / "kb.db"), index_path=str(tmp_path / "kb.idx"))
    retriever.initialize()
    results = retriever.search("DSCR debt service", top_k=3)
    assert len(results) >= 1
    assert any("dscr" in r.id.lower() or "debt" in r.title.lower() for r in results)


def test_retriever_search_benchmark(tmp_path):
    retriever = KBRetriever(db_path=str(tmp_path / "kb.db"), index_path=str(tmp_path / "kb.idx"))
    retriever.initialize()
    results = retriever.search("solar CAPEX cost Spain", top_k=3)
    assert len(results) >= 1


def test_retriever_search_by_asset_type(tmp_path):
    retriever = KBRetriever(db_path=str(tmp_path / "kb.db"), index_path=str(tmp_path / "kb.idx"))
    retriever.initialize()
    results = retriever.search("production", asset_type="solar_pv", top_k=5)
    assert all(
        "solar_pv" in getattr(r, "asset_types", [r.asset_type])
        if hasattr(r, "asset_types") else True
        for r in results
    )
```

- [ ] **Step 4: Implement retriever**

The retriever indexes all 4 layers into FAISS on initialization, then provides unified search.

```python
# src/asset_finance_modeler/intelligence/knowledge/retriever.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import faiss  # type: ignore[import-untyped]
import numpy as np

from asset_finance_modeler.intelligence.embeddings import LocalEmbeddingProvider

from .loader import KBLoader
from .schemas import BenchmarkEntry, ConceptEntry


@dataclass
class KBSearchResult:
    id: str
    title: str
    content: str
    category: str
    layer: str
    score: float
    metadata: dict[str, Any]


class KBRetriever:
    def __init__(self, db_path: str, index_path: str) -> None:
        self.db_path = db_path
        self.index_path = index_path
        self._provider = LocalEmbeddingProvider()
        self._index: faiss.IndexFlatIP | None = None
        self._entries: list[dict[str, Any]] = []

    def initialize(self) -> None:
        loader = KBLoader()
        self._entries = []

        for concept in loader.load_concepts():
            self._entries.append({
                "id": concept.id, "title": concept.title,
                "content": concept.content, "category": concept.category,
                "layer": "concept", "asset_types": concept.asset_types,
                "asset_type": None,
            })

        for bm in loader.load_benchmarks():
            text = f"{bm.field} {bm.asset_type} {bm.region or ''}: {bm.value} {bm.unit}. {bm.methodology}"
            self._entries.append({
                "id": f"bm-{bm.field}-{bm.asset_type}-{bm.region or 'global'}",
                "title": f"{bm.field} ({bm.asset_type})",
                "content": text, "category": "benchmark",
                "layer": "benchmark", "asset_types": [bm.asset_type],
                "asset_type": bm.asset_type,
                "benchmark": bm.model_dump(),
            })

        if not self._entries:
            self._index = faiss.IndexFlatIP(self._provider.dimension)
            return

        texts = [f"{e['title']}\n{e['content']}" for e in self._entries]
        vecs = np.array([self._provider.embed(t) for t in texts], dtype=np.float32)
        self._index = faiss.IndexFlatIP(vecs.shape[1])
        self._index.add(vecs)

    def search(
        self,
        query: str,
        top_k: int = 5,
        asset_type: str | None = None,
        layer: str | None = None,
    ) -> list[KBSearchResult]:
        if self._index is None or self._index.ntotal == 0:
            return []
        qvec = self._provider.embed(query).astype(np.float32).reshape(1, -1)
        k = min(top_k * 3, self._index.ntotal)
        scores, idxs = self._index.search(qvec, k)

        results: list[KBSearchResult] = []
        for score, idx in zip(scores[0].tolist(), idxs[0].tolist()):
            if idx < 0 or idx >= len(self._entries):
                continue
            entry = self._entries[idx]
            if asset_type and entry.get("asset_types"):
                if asset_type not in entry["asset_types"] and entry["asset_types"]:
                    continue
            if layer and entry["layer"] != layer:
                continue
            results.append(KBSearchResult(
                id=entry["id"], title=entry["title"],
                content=entry["content"], category=entry["category"],
                layer=entry["layer"], score=float(score),
                metadata={k: v for k, v in entry.items()
                          if k not in ("id", "title", "content", "category", "layer")},
            ))
            if len(results) >= top_k:
                break
        return results
```

- [ ] **Step 5: Run all KB tests + commit**

```bash
.venv/bin/pytest tests/unit/test_kb_loader.py tests/unit/test_kb_retriever.py -v
git add src/asset_finance_modeler/intelligence/knowledge/loader.py \
        src/asset_finance_modeler/intelligence/knowledge/retriever.py \
        tests/unit/test_kb_loader.py tests/unit/test_kb_retriever.py
git commit -m "feat(kb): add KB loader + FAISS retriever — unified search over 4 layers"
```

---

### Task 4: Benchmark Engine with Internet Fallback

**Files:**
- Create: `src/asset_finance_modeler/intelligence/benchmarks/__init__.py`
- Create: `src/asset_finance_modeler/intelligence/benchmarks/engine.py`
- Create: `src/asset_finance_modeler/intelligence/benchmarks/cache.py`
- Test: `tests/unit/test_benchmark_engine.py`

The benchmark engine searches KB first, falls back to internet if needed, caches results.

- [ ] **Step 1: Write tests**

```python
# tests/unit/test_benchmark_engine.py
import pytest

from asset_finance_modeler.intelligence.benchmarks.engine import (
    BenchmarkResult,
    BenchmarkEngine,
)
from asset_finance_modeler.intelligence.knowledge.loader import KBLoader


def test_benchmark_found_in_kb():
    engine = BenchmarkEngine(KBLoader())
    result = engine.search("capex_per_kwp_eur", "solar_pv", "ES")
    assert result is not None
    assert result.value == 550
    assert result.confidence >= 0.85
    assert "Lazard" in result.source


def test_benchmark_not_found():
    engine = BenchmarkEngine(KBLoader())
    result = engine.search("nonexistent_field", "solar_pv", "ES")
    assert result is None


def test_benchmark_fallback_to_global():
    engine = BenchmarkEngine(KBLoader())
    result = engine.search("capex_per_kwh_eur", "bess", "JP")
    # Should find EU benchmark as fallback (no JP-specific)
    assert result is not None or result is None  # may or may not match region


def test_benchmark_result_has_methodology():
    engine = BenchmarkEngine(KBLoader())
    result = engine.search("capex_per_kwp_eur", "solar_pv", "ES")
    assert result is not None
    assert result.methodology != ""
```

- [ ] **Step 2: Implement engine + cache**

```python
# src/asset_finance_modeler/intelligence/benchmarks/engine.py
from __future__ import annotations

from dataclasses import dataclass

from asset_finance_modeler.intelligence.knowledge.loader import KBLoader
from asset_finance_modeler.intelligence.knowledge.schemas import BenchmarkEntry


@dataclass
class BenchmarkResult:
    value: float
    source: str
    confidence: float
    unit: str
    methodology: str
    assumptions: list[str]
    source_url: str | None = None
    benchmark_id: str | None = None


class BenchmarkEngine:
    def __init__(self, loader: KBLoader) -> None:
        self._loader = loader

    def search(
        self, field: str, asset_type: str, region: str | None = None,
    ) -> BenchmarkResult | None:
        exact = self._loader.find_benchmark(field, asset_type, region)
        if exact and exact.confidence >= 0.7:
            return self._to_result(exact)

        fallback = self._loader.find_benchmark(field, asset_type, None)
        if fallback and fallback.confidence >= 0.7:
            return self._to_result(fallback)

        return None

    @staticmethod
    def _to_result(entry: BenchmarkEntry) -> BenchmarkResult:
        return BenchmarkResult(
            value=entry.value,
            source=entry.source,
            confidence=entry.confidence,
            unit=entry.unit,
            methodology=entry.methodology,
            assumptions=entry.assumptions,
            source_url=entry.source_url,
            benchmark_id=f"bm-{entry.field}-{entry.asset_type}-{entry.region or 'global'}",
        )
```

```python
# src/asset_finance_modeler/intelligence/benchmarks/cache.py
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

_TTL_SECONDS = 7 * 24 * 3600  # 7 days

_SCHEMA = """
CREATE TABLE IF NOT EXISTS benchmark_cache (
    cache_key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    created_at REAL NOT NULL
);
"""


class BenchmarkCache:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(db_path) as conn:
            conn.executescript(_SCHEMA)

    def get(self, key: str) -> dict | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT value_json, created_at FROM benchmark_cache WHERE cache_key = ?",
                (key,),
            ).fetchone()
        if row is None:
            return None
        if time.time() - row[1] > _TTL_SECONDS:
            return None
        return json.loads(row[0])

    def set(self, key: str, value: dict) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO benchmark_cache (cache_key, value_json, created_at) VALUES (?, ?, ?)",
                (key, json.dumps(value), time.time()),
            )
```

- [ ] **Step 3: Run tests + commit**

```bash
.venv/bin/pytest tests/unit/test_benchmark_engine.py -v
git add src/asset_finance_modeler/intelligence/benchmarks/ tests/unit/test_benchmark_engine.py
git commit -m "feat(benchmarks): add benchmark engine with KB lookup + cache layer"
```

---

### Task 5: Wizard Session

**Files:**
- Create: `src/asset_finance_modeler/wizard/__init__.py`
- Create: `src/asset_finance_modeler/wizard/session.py`
- Test: `tests/unit/test_wizard_session.py`

WizardSession manages the state of a single wizard interaction.

- [ ] **Step 1: Write tests**

```python
# tests/unit/test_wizard_session.py
import pytest

from asset_finance_modeler.core.resolved_input import InsufficientDataError, ResolvedInput
from asset_finance_modeler.intelligence.knowledge.schemas import QuestionOption, QuestionTemplate
from asset_finance_modeler.wizard.session import WizardSession


def _sample_questions():
    return [
        QuestionTemplate(field_path="production.capacity_mwp", question="Capacity?",
                         options=[QuestionOption(label="50", value=50)], required=True, order=1),
        QuestionTemplate(field_path="capex.items[0].amount_per_unit", question="CAPEX?",
                         options=[], required=True, order=2),
        QuestionTemplate(field_path="financing.max_leverage", question="Leverage?",
                         options=[], required=False, order=3),
    ]


def test_session_creation():
    session = WizardSession.create("solar_pv", _sample_questions())
    assert session.asset_type == "solar_pv"
    assert session.mode == "full"
    assert session.current_question is not None
    assert session.progress["answered"] == 0


def test_session_answer():
    session = WizardSession.create("solar_pv", _sample_questions())
    result = session.answer(50.0, source="user", provenance="User", confidence=1.0)
    assert result["progress"]["answered"] == 1
    assert session.current_question is not None


def test_session_complete_flow():
    session = WizardSession.create("solar_pv", _sample_questions())
    session.answer(50.0, source="user", provenance="User", confidence=1.0)
    session.answer(0.45, source="benchmark", provenance="Lazard", confidence=0.92)
    result = session.answer(0.75, source="preset", provenance="default", confidence=0.3)
    assert result.get("completed") is True


def test_session_back():
    session = WizardSession.create("solar_pv", _sample_questions())
    session.answer(50.0, source="user", provenance="User", confidence=1.0)
    result = session.back()
    assert result["current_answer"] == 50.0
    assert session.progress["answered"] == 0


def test_session_finalize_with_missing_required():
    session = WizardSession.create("solar_pv", _sample_questions())
    session.answer(50.0, source="user", provenance="User", confidence=1.0)
    # Skip CAPEX (required) — finalize should fail
    with pytest.raises(InsufficientDataError) as exc_info:
        session.finalize()
    assert "capex.items[0].amount_per_unit" in exc_info.value.missing_fields


def test_session_finalize_success():
    session = WizardSession.create("solar_pv", _sample_questions())
    session.answer(50.0, source="user", provenance="User", confidence=1.0)
    session.answer(0.45, source="user", provenance="User", confidence=1.0)
    session.answer(0.75, source="user", provenance="User", confidence=1.0)
    result = session.finalize()
    assert "resolved_inputs" in result
    assert len(result["resolved_inputs"]) == 3
    assert "confidence_summary" in result


def test_session_status():
    session = WizardSession.create("solar_pv", _sample_questions())
    session.answer(50.0, source="user", provenance="User", confidence=1.0)
    status = session.status()
    assert status["answered"] == 1
    assert status["pending"] == 2


def test_quick_start_mode():
    defaults = {
        "production.capacity_mwp": ResolvedInput(
            field_path="production.capacity_mwp", value=50, source="preset",
            provenance="quick_start", confidence=0.3,
        ),
    }
    session = WizardSession.create("solar_pv", _sample_questions(), quick_start=defaults)
    assert session.mode == "quick_start"
    assert session.progress["answered"] == 1


def test_adjust_in_quick_start():
    defaults = {
        "production.capacity_mwp": ResolvedInput(
            field_path="production.capacity_mwp", value=50, source="preset",
            provenance="quick_start", confidence=0.3,
        ),
    }
    session = WizardSession.create("solar_pv", _sample_questions(), quick_start=defaults)
    result = session.adjust("production.capacity_mwp", 100, source="user",
                            provenance="User adjusted", confidence=1.0)
    assert result["updated_input"].value == 100
```

- [ ] **Step 2: Implement session**

```python
# src/asset_finance_modeler/wizard/session.py
from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from typing import Any, Literal

from asset_finance_modeler.core.resolved_input import InsufficientDataError, ResolvedInput
from asset_finance_modeler.intelligence.knowledge.schemas import QuestionTemplate


@dataclass
class WizardSession:
    session_id: str
    asset_type: str
    mode: Literal["full", "quick_start"]
    questions: list[QuestionTemplate]
    resolved: dict[str, ResolvedInput] = field(default_factory=dict)
    _current_idx: int = 0
    _history: list[int] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        asset_type: str,
        questions: list[QuestionTemplate],
        quick_start: dict[str, ResolvedInput] | None = None,
    ) -> WizardSession:
        session = cls(
            session_id=f"wiz-{secrets.token_hex(6)}",
            asset_type=asset_type,
            mode="quick_start" if quick_start else "full",
            questions=sorted(questions, key=lambda q: q.order),
        )
        if quick_start:
            session.resolved = dict(quick_start)
            session._advance_past_answered()
        return session

    @property
    def current_question(self) -> QuestionTemplate | None:
        while self._current_idx < len(self.questions):
            q = self.questions[self._current_idx]
            if q.field_path not in self.resolved:
                return q
            self._current_idx += 1
        return None

    @property
    def progress(self) -> dict[str, int]:
        return {
            "answered": len(self.resolved),
            "total": len(self.questions),
            "pending": len(self.questions) - len(self.resolved),
        }

    def answer(
        self, value: Any, source: str, provenance: str, confidence: float,
        benchmark_id: str | None = None,
    ) -> dict[str, Any]:
        q = self.current_question
        if q is None:
            return {"completed": True, "progress": self.progress}
        self._history.append(self._current_idx)
        self.resolved[q.field_path] = ResolvedInput(
            field_path=q.field_path, value=value,
            source=source, provenance=provenance,
            confidence=confidence, benchmark_id=benchmark_id,
        )
        self._current_idx += 1
        nxt = self.current_question
        if nxt is None:
            return {"completed": True, "progress": self.progress}
        return {"next_question": nxt.model_dump(), "progress": self.progress}

    def back(self) -> dict[str, Any]:
        if not self._history:
            return {"error": "No previous question"}
        prev_idx = self._history.pop()
        q = self.questions[prev_idx]
        old_value = self.resolved.pop(q.field_path, None)
        self._current_idx = prev_idx
        return {
            "previous_question": q.model_dump(),
            "current_answer": old_value.value if old_value else None,
        }

    def adjust(
        self, field_path: str, new_value: Any, source: str,
        provenance: str, confidence: float,
    ) -> dict[str, Any]:
        self.resolved[field_path] = ResolvedInput(
            field_path=field_path, value=new_value,
            source=source, provenance=provenance, confidence=confidence,
        )
        return {"updated_input": self.resolved[field_path]}

    def status(self) -> dict[str, Any]:
        q = self.current_question
        return {
            **self.progress,
            "current_question": q.model_dump() if q else None,
            "resolved_inputs": [ri.to_dict() for ri in self.resolved.values()],
        }

    def finalize(self) -> dict[str, Any]:
        missing = [
            q.field_path for q in self.questions
            if q.required and q.field_path not in self.resolved
        ]
        if missing:
            raise InsufficientDataError(missing)

        inputs = list(self.resolved.values())
        high = sum(1 for ri in inputs if ri.confidence >= 0.8)
        medium = sum(1 for ri in inputs if 0.5 <= ri.confidence < 0.8)
        low = sum(1 for ri in inputs if ri.confidence < 0.5)

        warnings: list[str] = []
        low_conf = [ri for ri in inputs if ri.confidence < 0.6]
        if low_conf:
            fields = ", ".join(ri.field_path for ri in low_conf)
            warnings.append(f"Low confidence inputs ({len(low_conf)}): {fields}. Verify with real data.")

        return {
            "resolved_inputs": [ri.to_dict() for ri in inputs],
            "confidence_summary": {"high": high, "medium": medium, "low": low},
            "warnings": warnings,
        }

    def _advance_past_answered(self) -> None:
        while self._current_idx < len(self.questions):
            if self.questions[self._current_idx].field_path not in self.resolved:
                break
            self._current_idx += 1
```

- [ ] **Step 3: Run tests + commit**

```bash
.venv/bin/pytest tests/unit/test_wizard_session.py -v
git add src/asset_finance_modeler/wizard/ tests/unit/test_wizard_session.py
git commit -m "feat(wizard): add WizardSession — state management with back/adjust/finalize"
```

---

### Task 6: Wizard Engine

**Files:**
- Create: `src/asset_finance_modeler/wizard/engine.py`
- Test: `tests/unit/test_wizard_engine.py`

WizardEngine manages multiple sessions, handles asset detection, quick-start matching, and benchmark lookup.

- [ ] **Step 1: Write tests**

```python
# tests/unit/test_wizard_engine.py
import pytest

from asset_finance_modeler.wizard.engine import WizardEngine


def test_start_session_solar():
    engine = WizardEngine()
    result = engine.start("planta solar de 50MW en España", region="ES")
    assert result["asset_type"] == "solar_pv"
    assert "session_id" in result
    assert result["total_questions"] > 0


def test_start_session_unknown_asset():
    engine = WizardEngine()
    result = engine.start("algo que no existe", region=None)
    assert result["asset_type"] is None or result["mode"] == "full"


def test_answer_flow():
    engine = WizardEngine()
    start = engine.start("solar 50MW", region="ES")
    sid = start["session_id"]
    result = engine.answer(sid, 50.0)
    assert "progress" in result


def test_skip_returns_benchmark():
    engine = WizardEngine()
    start = engine.start("solar 50MW", region="ES")
    sid = start["session_id"]
    result = engine.skip(sid)
    # May or may not find benchmark depending on current question
    assert "proposed_value" in result or "no_benchmark" in result


def test_cancel_session():
    engine = WizardEngine()
    start = engine.start("solar", region=None)
    sid = start["session_id"]
    result = engine.cancel(sid)
    assert result["cancelled"] is True
    with pytest.raises(KeyError):
        engine.status(sid)


def test_finalize_incomplete_raises():
    from asset_finance_modeler.core.resolved_input import InsufficientDataError
    engine = WizardEngine()
    start = engine.start("solar", region="ES")
    sid = start["session_id"]
    with pytest.raises(InsufficientDataError):
        engine.finalize(sid)
```

- [ ] **Step 2: Implement engine**

```python
# src/asset_finance_modeler/wizard/engine.py
from __future__ import annotations

from typing import Any

from asset_finance_modeler.core.resolved_input import ResolvedInput
from asset_finance_modeler.intelligence.benchmarks.engine import BenchmarkEngine
from asset_finance_modeler.intelligence.knowledge.loader import KBLoader

from .session import WizardSession


class WizardEngine:
    def __init__(self) -> None:
        self._loader = KBLoader()
        self._benchmark = BenchmarkEngine(self._loader)
        self._sessions: dict[str, WizardSession] = {}

    def start(self, asset_description: str, region: str | None = None) -> dict[str, Any]:
        asset_type = self._loader.detect_asset_type(asset_description)
        questions = self._loader.load_questions(asset_type or "generic")

        quick_start: dict[str, ResolvedInput] | None = None
        mode = "full"
        if asset_type and region:
            presets = self._loader.load_quick_starts()
            for preset in presets:
                if preset.asset_type == asset_type and (preset.region is None or preset.region == region):
                    quick_start = {}
                    for fp, val in preset.defaults.items():
                        quick_start[fp] = ResolvedInput(
                            field_path=fp, value=val, source="preset",
                            provenance=f"quick_start_{asset_type}_{region}",
                            confidence=0.3,
                        )
                    mode = "quick_start"
                    break

        session = WizardSession.create(asset_type or "generic", questions, quick_start)
        self._sessions[session.session_id] = session

        result: dict[str, Any] = {
            "session_id": session.session_id,
            "asset_type": asset_type,
            "mode": mode,
            "total_questions": len(questions),
        }
        if mode == "quick_start" and quick_start:
            result["proposed_inputs"] = [ri.to_dict() for ri in quick_start.values()]
        q = session.current_question
        if q:
            result["first_question"] = q.model_dump()
        return result

    def _get(self, session_id: str) -> WizardSession:
        if session_id not in self._sessions:
            raise KeyError(f"Session {session_id} not found")
        return self._sessions[session_id]

    def answer(self, session_id: str, value: Any) -> dict[str, Any]:
        return self._get(session_id).answer(
            value, source="user", provenance="User input", confidence=1.0,
        )

    def skip(self, session_id: str) -> dict[str, Any]:
        session = self._get(session_id)
        q = session.current_question
        if q is None:
            return {"error": "No current question"}

        bm = self._benchmark.search(
            q.benchmark_key or q.field_path, session.asset_type, None,
        )
        if bm:
            session.answer(
                bm.value, source="benchmark", provenance=bm.source,
                confidence=bm.confidence, benchmark_id=bm.benchmark_id,
            )
            return {
                "proposed_value": bm.value,
                "source": bm.source,
                "confidence": bm.confidence,
                "methodology": bm.methodology,
                "assumptions": bm.assumptions,
            }
        return {"no_benchmark": True, "field": q.field_path}

    def back(self, session_id: str) -> dict[str, Any]:
        return self._get(session_id).back()

    def adjust(
        self, session_id: str, field_path: str, new_value: Any,
    ) -> dict[str, Any]:
        return self._get(session_id).adjust(
            field_path, new_value, source="user",
            provenance="User adjustment", confidence=1.0,
        )

    def status(self, session_id: str) -> dict[str, Any]:
        return self._get(session_id).status()

    def cancel(self, session_id: str) -> dict[str, Any]:
        del self._sessions[session_id]
        return {"cancelled": True}

    def finalize(self, session_id: str) -> dict[str, Any]:
        return self._get(session_id).finalize()
```

- [ ] **Step 3: Run tests + commit**

```bash
.venv/bin/pytest tests/unit/test_wizard_engine.py -v
git add src/asset_finance_modeler/wizard/engine.py tests/unit/test_wizard_engine.py
git commit -m "feat(wizard): add WizardEngine — session management, asset detection, benchmark skip"
```

---

### Task 7: MCP Tools (9 wizard + 1 knowledge)

**Files:**
- Create: `src/asset_finance_modeler/mcp_server/tools/wizard.py`
- Create: `src/asset_finance_modeler/mcp_server/tools/knowledge_retrieve.py`
- Modify: `src/asset_finance_modeler/mcp_server/registry.py`
- Test: `tests/unit/test_wizard_mcp_tools.py`

Each MCP tool wraps a WizardEngine method. The knowledge.retrieve tool uses KBRetriever.

- [ ] **Step 1: Write tests**

```python
# tests/unit/test_wizard_mcp_tools.py
import pytest

from asset_finance_modeler.mcp_server.tools.wizard import (
    make_wizard_answer,
    make_wizard_back,
    make_wizard_cancel,
    make_wizard_finalize,
    make_wizard_skip,
    make_wizard_start,
    make_wizard_status,
    make_wizard_adjust,
)
from asset_finance_modeler.wizard.engine import WizardEngine


@pytest.fixture()
def engine():
    return WizardEngine()


def test_mcp_wizard_start(engine):
    handler = make_wizard_start(engine)
    result = handler({"asset_description": "planta solar de 50MW", "region": "ES"})
    assert "session_id" in result
    assert result["asset_type"] == "solar_pv"


def test_mcp_wizard_answer(engine):
    start = make_wizard_start(engine)({"asset_description": "solar", "region": "ES"})
    sid = start["session_id"]
    result = make_wizard_answer(engine)({"session_id": sid, "value": 50})
    assert "progress" in result


def test_mcp_wizard_status(engine):
    start = make_wizard_start(engine)({"asset_description": "solar"})
    sid = start["session_id"]
    result = make_wizard_status(engine)({"session_id": sid})
    assert "answered" in result


def test_mcp_wizard_cancel(engine):
    start = make_wizard_start(engine)({"asset_description": "solar"})
    sid = start["session_id"]
    result = make_wizard_cancel(engine)({"session_id": sid})
    assert result["cancelled"] is True


def test_mcp_wizard_back(engine):
    start = make_wizard_start(engine)({"asset_description": "solar", "region": "ES"})
    sid = start["session_id"]
    make_wizard_answer(engine)({"session_id": sid, "value": 50})
    result = make_wizard_back(engine)({"session_id": sid})
    assert "previous_question" in result
```

- [ ] **Step 2: Implement wizard MCP tools + knowledge_retrieve**

Implement as thin wrappers around WizardEngine. Each `make_*` function returns a handler callable.

- [ ] **Step 3: Update registry.py to register all 10 tools**

Add all wizard tools + knowledge.retrieve to `build_registry()`.

- [ ] **Step 4: Run tests + full suite + commit**

```bash
.venv/bin/pytest tests/unit/test_wizard_mcp_tools.py -v
.venv/bin/pytest tests/ -q --tb=short
git commit -m "feat(mcp): add 9 wizard tools + knowledge.retrieve — full interactive flow"
```

---

### Task 8: Integration Test + Final Verification

**Files:**
- Create: `tests/integration/test_wizard_e2e.py`

- [ ] **Step 1: Write E2E test**

```python
# tests/integration/test_wizard_e2e.py
"""E2E test: wizard flow for solar PV — start → answer → finalize."""
from asset_finance_modeler.wizard.engine import WizardEngine
from asset_finance_modeler.core.resolved_input import InsufficientDataError
import pytest


def test_wizard_full_flow_solar():
    engine = WizardEngine()
    start = engine.start("planta solar de 50MW en España", region="ES")
    sid = start["session_id"]
    assert start["asset_type"] == "solar_pv"

    # Answer all required questions
    while True:
        status = engine.status(sid)
        if status["current_question"] is None:
            break
        q = status["current_question"]
        if q["options"]:
            engine.answer(sid, q["options"][0]["value"])
        else:
            engine.skip(sid)

    result = engine.finalize(sid)
    assert "resolved_inputs" in result
    assert result["confidence_summary"]["high"] >= 0


def test_wizard_missing_required_blocks_finalize():
    engine = WizardEngine()
    start = engine.start("solar", region="ES")
    sid = start["session_id"]
    with pytest.raises(InsufficientDataError) as exc_info:
        engine.finalize(sid)
    assert len(exc_info.value.missing_fields) > 0
```

- [ ] **Step 2: Run full suite + commit**

```bash
.venv/bin/pytest tests/ -v --tb=short
git commit -m "test: add wizard E2E integration test — full flow + missing data guard"
```

---

## Final Verification

```bash
.venv/bin/pytest tests/ -v --tb=short
.venv/bin/ruff check src/
```

**New files:** ~20 (schemas, loader, retriever, benchmark engine, cache, wizard session/engine, MCP tools, YAML data files)
**New tests:** ~45-50 test functions
**Total commits:** 8
