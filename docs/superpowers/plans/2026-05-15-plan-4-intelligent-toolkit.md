# Plan 4 — Intelligent Toolkit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add a layer of **structured intelligence** to the modeler so any consuming agent (Ian/Gestnova, Aurora, future agents) can leverage financial expertise without embedding it in its own prompt. Three new capabilities, all deterministic (NO additional LLM in the cascade):

1. **Knowledge base** — FAISS-indexed financial concepts, formulas, frameworks, sector benchmarks. Searchable.
2. **Declarative workflows** — YAML-defined sequences of tool calls for common analysis patterns. Agent invokes one workflow id → modeler runs the recipe.
3. **Contextual memory** — Per-tenant persistent memory of conversations, decisions, simulations. Semantically searchable so agents can recall "what did we discuss last time about pricing?".

**Multi-tenancy** is introduced for the new components (knowledge/workflows/context) via optional `tenant_id` parameter, defaulting to `"default"`. This makes the modeler ready for multi-company usage when the platform scales.

**Architecture invariant:** The modeler still does NOT make LLM calls. All "intelligence" is retrieval + workflow execution. The consuming agent (Ian) is the only LLM in the chain — it just gets much better tools to work with.

**Tech stack additions:** `sentence-transformers>=2.6` for embeddings (model: `paraphrase-multilingual-MiniLM-L12-v2`, supports Spanish + English, ~120MB, fast on CPU), `faiss-cpu>=1.8` for vector index, `jinja2>=3` for workflow templating.

**Spec reference:** `docs/superpowers/specs/2026-05-14-asset-finance-modeler-design.md` Section 10 (Future scope — V2/V3).

**Prerequisites:** Plans 1+2+3 merged. 162 tests passing. MCP server live with 21 tools.

---

### Task 1: Embeddings provider abstraction + local implementation

**Files:**
- Modify: `pyproject.toml` (add deps)
- Create: `src/asset_finance_modeler/intelligence/__init__.py`
- Create: `src/asset_finance_modeler/intelligence/embeddings.py`
- Create: `tests/unit/test_embeddings.py`

- [ ] **Step 1: Add deps to pyproject.toml**

In `dependencies = [...]`, add:
```toml
    "sentence-transformers>=2.6",
    "faiss-cpu>=1.8",
    "jinja2>=3",
```

Then `pip install -e ".[dev]"` (it will download ~120MB embedding model on first use, that's fine).

- [ ] **Step 2: Write failing tests**

`tests/unit/test_embeddings.py`:
```python
import numpy as np
import pytest

from asset_finance_modeler.intelligence.embeddings import (
    EmbeddingProvider,
    LocalEmbeddingProvider,
)


@pytest.fixture(scope="module")
def provider() -> LocalEmbeddingProvider:
    return LocalEmbeddingProvider()


def test_provider_is_subclass_of_abstract():
    assert issubclass(LocalEmbeddingProvider, EmbeddingProvider)


def test_embed_single_returns_vector(provider):
    vec = provider.embed("test query")
    assert isinstance(vec, np.ndarray)
    assert vec.ndim == 1
    assert vec.shape[0] == provider.dimension


def test_embed_batch_returns_matrix(provider):
    matrix = provider.embed_batch(["hello", "world", "test"])
    assert matrix.shape == (3, provider.dimension)


def test_similar_texts_have_higher_cosine_similarity(provider):
    revenue = provider.embed("monthly recurring revenue")
    arr = provider.embed("MRR")
    unrelated = provider.embed("today is a sunny day")

    def cos(a, b):
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    assert cos(revenue, arr) > cos(revenue, unrelated)


def test_spanish_text_works(provider):
    vec = provider.embed("ingresos recurrentes mensuales")
    assert vec.shape[0] == provider.dimension
```

- [ ] **Step 3: Run tests, verify fail**

```bash
cd "/Users/rikyizquierdo/Documents/New project/asset-finance-modeler"
source .venv/bin/activate
pytest tests/unit/test_embeddings.py -v
```

Expected: ImportError.

- [ ] **Step 4: Implement embeddings module**

`src/asset_finance_modeler/intelligence/__init__.py`: empty file.

`src/asset_finance_modeler/intelligence/embeddings.py`:
```python
from __future__ import annotations

from abc import ABC, abstractmethod
from functools import lru_cache

import numpy as np


class EmbeddingProvider(ABC):
    @property
    @abstractmethod
    def dimension(self) -> int: ...

    @abstractmethod
    def embed(self, text: str) -> np.ndarray: ...

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> np.ndarray: ...


DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


@lru_cache(maxsize=1)
def _load_model(model_name: str):  # type: ignore[no-untyped-def]
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(model_name)


class LocalEmbeddingProvider(EmbeddingProvider):
    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self._model_name = model_name
        self._dim: int | None = None

    @property
    def dimension(self) -> int:
        if self._dim is None:
            self._dim = _load_model(self._model_name).get_sentence_embedding_dimension()
        return int(self._dim)

    def embed(self, text: str) -> np.ndarray:
        model = _load_model(self._model_name)
        arr = model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
        return np.asarray(arr, dtype=np.float32)

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        model = _load_model(self._model_name)
        arr = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
        return np.asarray(arr, dtype=np.float32)
```

- [ ] **Step 5: Run tests, verify pass**

First run downloads the model (~120MB, takes 30-60s). Subsequent runs are cached.

```bash
pytest tests/unit/test_embeddings.py -v
```

Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/asset_finance_modeler/intelligence/__init__.py src/asset_finance_modeler/intelligence/embeddings.py tests/unit/test_embeddings.py
git commit -m "feat(intelligence): EmbeddingProvider + LocalEmbeddingProvider (multilingual MiniLM)"
```

---

### Task 2: KnowledgeBase class + FAISS index + SQLite metadata

**Files:**
- Create: `src/asset_finance_modeler/intelligence/knowledge/__init__.py`
- Create: `src/asset_finance_modeler/intelligence/knowledge/base.py`
- Create: `tests/unit/test_knowledge_base.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_knowledge_base.py`:
```python
import pytest

from asset_finance_modeler.intelligence.embeddings import LocalEmbeddingProvider
from asset_finance_modeler.intelligence.knowledge.base import KnowledgeBase, KnowledgeEntry


@pytest.fixture
def kb(tmp_path):
    base = KnowledgeBase(
        db_path=str(tmp_path / "kb.db"),
        index_path=str(tmp_path / "kb.faiss"),
        embedding_provider=LocalEmbeddingProvider(),
    )
    base.initialize()
    return base


def test_add_and_get(kb):
    entry_id = kb.add(KnowledgeEntry(
        title="LTV definition",
        content="Lifetime Value (LTV) is the total revenue a customer generates during their relationship with the business.",
        category="unit_economics",
        tags=["ltv", "metric"],
    ))
    fetched = kb.get(entry_id)
    assert fetched is not None
    assert fetched.title == "LTV definition"
    assert "ltv" in fetched.tags


def test_search_semantic(kb):
    kb.add(KnowledgeEntry(
        title="CAC",
        content="Customer Acquisition Cost: total marketing + sales spend / new customers acquired.",
        category="unit_economics",
    ))
    kb.add(KnowledgeEntry(
        title="DCF",
        content="Discounted Cash Flow valuation method discounts future free cash flows to present value.",
        category="valuation",
    ))
    kb.add(KnowledgeEntry(
        title="Stock photography",
        content="Stock photography refers to professional photographs of common places, landmarks, nature, etc.",
        category="unrelated",
    ))

    results = kb.search("how much does it cost to acquire a new customer?", top_k=2)
    assert len(results) == 2
    # CAC should rank first
    assert results[0].entry.title == "CAC"


def test_search_with_category_filter(kb):
    kb.add(KnowledgeEntry(title="LTV", content="LTV is...", category="unit_economics"))
    kb.add(KnowledgeEntry(title="DCF", content="DCF method...", category="valuation"))

    results = kb.search("valuation method", top_k=5, category="valuation")
    titles = {r.entry.title for r in results}
    assert "DCF" in titles
    assert "LTV" not in titles


def test_list_categories(kb):
    kb.add(KnowledgeEntry(title="A", content="a", category="cat1"))
    kb.add(KnowledgeEntry(title="B", content="b", category="cat2"))
    kb.add(KnowledgeEntry(title="C", content="c", category="cat1"))
    cats = kb.list_categories()
    assert {"cat1", "cat2"} == set(c["name"] for c in cats)
    counts = {c["name"]: c["count"] for c in cats}
    assert counts["cat1"] == 2


def test_multi_tenant_isolation(kb):
    kb.add(KnowledgeEntry(title="Tenant A info", content="proprietary A", tenant_id="company-a"))
    kb.add(KnowledgeEntry(title="Tenant B info", content="proprietary B", tenant_id="company-b"))
    kb.add(KnowledgeEntry(title="Global info", content="shared", tenant_id=None))

    results_a = kb.search("proprietary", top_k=10, tenant_id="company-a")
    titles_a = {r.entry.title for r in results_a}
    assert "Tenant A info" in titles_a
    assert "Tenant B info" not in titles_a
    # Global entries visible to all tenants
    assert "Global info" in titles_a
```

- [ ] **Step 2: Run tests, verify fail**

```bash
pytest tests/unit/test_knowledge_base.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement KnowledgeBase**

`src/asset_finance_modeler/intelligence/knowledge/__init__.py`: empty file.

`src/asset_finance_modeler/intelligence/knowledge/base.py`:
```python
from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import faiss
import numpy as np

from asset_finance_modeler.intelligence.embeddings import EmbeddingProvider

_SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge_entries (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    category TEXT NOT NULL,
    tags_json TEXT NOT NULL DEFAULT '[]',
    tenant_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    vector_offset INTEGER
);
CREATE INDEX IF NOT EXISTS idx_kb_category ON knowledge_entries(category);
CREATE INDEX IF NOT EXISTS idx_kb_tenant ON knowledge_entries(tenant_id);
"""


@dataclass
class KnowledgeEntry:
    title: str
    content: str
    category: str = "general"
    tags: list[str] = field(default_factory=list)
    tenant_id: str | None = None
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            self.id = f"kn-{uuid.uuid4().hex[:8]}"


@dataclass
class SearchResult:
    entry: KnowledgeEntry
    score: float


class KnowledgeBase:
    def __init__(
        self,
        db_path: str,
        index_path: str,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self.db_path = db_path
        self.index_path = index_path
        self.provider = embedding_provider
        self._index: faiss.IndexFlatIP | None = None
        self._id_map: list[str] = []  # offset → entry id

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(_SCHEMA)
        self._load_index()

    def _load_index(self) -> None:
        index_file = Path(self.index_path)
        if index_file.exists():
            self._index = faiss.read_index(str(index_file))
            with self._conn() as conn:
                rows = conn.execute(
                    "SELECT id FROM knowledge_entries WHERE vector_offset IS NOT NULL ORDER BY vector_offset"
                ).fetchall()
            self._id_map = [r["id"] for r in rows]
        else:
            self._index = faiss.IndexFlatIP(self.provider.dimension)
            self._id_map = []

    def _save_index(self) -> None:
        if self._index is not None:
            Path(self.index_path).parent.mkdir(parents=True, exist_ok=True)
            faiss.write_index(self._index, self.index_path)

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> KnowledgeEntry:
        return KnowledgeEntry(
            id=row["id"],
            title=row["title"],
            content=row["content"],
            category=row["category"],
            tags=json.loads(row["tags_json"]),
            tenant_id=row["tenant_id"],
        )

    def add(self, entry: KnowledgeEntry) -> str:
        # Embed
        text = f"{entry.title}\n{entry.content}"
        vec = self.provider.embed(text).astype(np.float32).reshape(1, -1)
        assert self._index is not None
        offset = self._index.ntotal
        self._index.add(vec)
        self._id_map.append(entry.id)
        self._save_index()

        with self._conn() as conn:
            conn.execute(
                """INSERT INTO knowledge_entries
                   (id, title, content, category, tags_json, tenant_id, vector_offset)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (entry.id, entry.title, entry.content, entry.category,
                 json.dumps(entry.tags), entry.tenant_id, offset),
            )
        return entry.id

    def get(self, entry_id: str) -> KnowledgeEntry | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM knowledge_entries WHERE id = ?", (entry_id,)
            ).fetchone()
        return self._row_to_entry(row) if row else None

    def search(
        self,
        query: str,
        top_k: int = 5,
        category: str | None = None,
        tenant_id: str | None = None,
    ) -> list[SearchResult]:
        assert self._index is not None
        if self._index.ntotal == 0:
            return []
        qvec = self.provider.embed(query).astype(np.float32).reshape(1, -1)
        # Search a wider neighborhood to allow post-filtering
        k_search = min(top_k * 5, self._index.ntotal)
        scores, idxs = self._index.search(qvec, k_search)

        results: list[SearchResult] = []
        for score, idx in zip(scores[0].tolist(), idxs[0].tolist()):
            if idx < 0 or idx >= len(self._id_map):
                continue
            entry = self.get(self._id_map[idx])
            if entry is None:
                continue
            if category is not None and entry.category != category:
                continue
            if tenant_id is not None and entry.tenant_id not in (None, tenant_id):
                continue
            results.append(SearchResult(entry=entry, score=float(score)))
            if len(results) >= top_k:
                break
        return results

    def list_categories(self) -> list[dict[str, object]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT category, COUNT(*) as cnt FROM knowledge_entries GROUP BY category ORDER BY category"
            ).fetchall()
        return [{"name": r["category"], "count": int(r["cnt"])} for r in rows]
```

- [ ] **Step 4: Run tests, verify pass**

```bash
pytest tests/unit/test_knowledge_base.py -v
```

Expected: 5 passed (may take 30s on first run due to model load).

- [ ] **Step 5: Commit**

```bash
git add src/asset_finance_modeler/intelligence/knowledge/ tests/unit/test_knowledge_base.py
git commit -m "feat(intelligence): KnowledgeBase with FAISS index + SQLite metadata + multi-tenant filter"
```

---

### Task 3: Seed initial financial knowledge

**Files:**
- Create: `src/asset_finance_modeler/intelligence/knowledge/data/__init__.py`
- Create: `src/asset_finance_modeler/intelligence/knowledge/data/seed.yaml`
- Create: `src/asset_finance_modeler/intelligence/knowledge/seed.py`
- Create: `tests/unit/test_knowledge_seed.py`

- [ ] **Step 1: Create seed data file**

`src/asset_finance_modeler/intelligence/knowledge/data/__init__.py`: empty file.

`src/asset_finance_modeler/intelligence/knowledge/data/seed.yaml`:
```yaml
- category: unit_economics
  title: "CAC — Customer Acquisition Cost"
  content: |
    El CAC es el coste total de adquirir un nuevo cliente: gasto comercial + marketing dividido por el número de nuevos clientes captados en el periodo.
    Fórmula: CAC = (sales + marketing spend) / new customers.
    Benchmark SaaS B2B 2024: payback CAC < 12 meses se considera sano.
  tags: [cac, sales, marketing, saas]

- category: unit_economics
  title: "LTV — Lifetime Value"
  content: |
    El LTV es el revenue total que un cliente generará durante toda su relación con la empresa.
    Fórmula simple SaaS: LTV = ARPU * gross_margin / monthly_churn_rate.
    Regla de oro: LTV/CAC >= 3 es sano. LTV/CAC < 1 = no rentable.
  tags: [ltv, retention, saas]

- category: unit_economics
  title: "Payback CAC"
  content: |
    Meses necesarios para recuperar el coste de adquisición de un cliente con su margen bruto recurrente.
    Fórmula: payback_months = CAC / (ARPU * gross_margin).
    SaaS B2B típico: 12-18 meses payback. Más de 24 meses = problemático.
  tags: [payback, cac, saas]

- category: unit_economics
  title: "Rule of 40"
  content: |
    Indicador SaaS: revenue_growth_yoy + ebitda_margin >= 40% indica negocio sano.
    Cumplirlo es bandera verde para inversores en growth-stage SaaS.
  tags: [rule_of_40, growth, ebitda]

- category: unit_economics
  title: "Magic Number"
  content: |
    Mide eficiencia comercial: (Δ ARR trimestral × 4) / gasto sales+marketing trimestre anterior.
    > 1 = invertir más en ventas. < 0.5 = ventas no eficientes.
  tags: [magic_number, sales_efficiency]

- category: valuation
  title: "DCF — Discounted Cash Flow"
  content: |
    Método de valoración: descuenta flujos de caja libres futuros (FCF) a su valor presente usando WACC.
    Enterprise Value = Σ FCF_t / (1+WACC)^t + Terminal Value / (1+WACC)^n.
    Terminal Value Gordon: FCF_terminal * (1+g) / (WACC - g) — requiere WACC > g.
  tags: [dcf, valuation, npv, wacc]

- category: valuation
  title: "WACC — Weighted Average Cost of Capital"
  content: |
    Tasa de descuento que refleja el coste mixto de financiar la empresa con deuda y equity.
    Para early-stage startup SaaS: 18-25%. Empresa establecida: 8-12%. Real estate: 6-10%.
  tags: [wacc, discount_rate]

- category: valuation
  title: "Exit Multiple Valuation"
  content: |
    Alternativa a Gordon: terminal value = ARR_terminal × multiple.
    Múltiplos típicos SaaS B2B 2024: 4-8x ARR (depende de growth y rule of 40).
  tags: [exit_multiple, arr, saas]

- category: valuation
  title: "NPV — Net Present Value"
  content: |
    Valor presente neto de una serie de flujos descontados a una tasa dada.
    Si NPV > 0 con WACC apropiado, el proyecto crea valor.
  tags: [npv, valuation]

- category: valuation
  title: "IRR — Internal Rate of Return"
  content: |
    Tasa de descuento a la cual el NPV = 0. Representa la rentabilidad anual implícita.
    En real estate proyectos: IRR > 12-15% se considera atractivo en mercado estabilizado.
  tags: [irr, returns]

- category: cash_flow
  title: "FCF — Free Cash Flow"
  content: |
    Caja libre: CFO - CapEx. Es la métrica más importante para valoración.
    Indica caja disponible para pagar deuda, dividendos, o reinvertir.
  tags: [fcf, cashflow]

- category: cash_flow
  title: "Runway"
  content: |
    Meses hasta que la caja llegue a cero al ritmo actual de quema.
    Cálculo: cash_actual / monthly_burn_rate.
    Recomendado: > 18 meses para startups en growth, > 24 meses pre-Serie A.
  tags: [runway, burn_rate, cash]

- category: cash_flow
  title: "Working Capital"
  content: |
    Necesidades de circulante: AR + inventory - AP. Día a día.
    DSO (días cobro) y DPO (días pago) son inputs clave. SaaS típico: DSO 30-45 días.
  tags: [working_capital, dso, dpo]

- category: debt
  title: "DSCR — Debt Service Coverage Ratio"
  content: |
    EBITDA / (intereses + principal de deuda). Mide capacidad de servicio de deuda.
    Bancos exigen DSCR > 1.2-1.5 para project finance. < 1 = no puedes pagar la deuda.
  tags: [dscr, debt, banking]

- category: debt
  title: "ICR — Interest Coverage Ratio"
  content: |
    EBIT / Intereses. Cuántas veces el beneficio operativo cubre los intereses.
    > 3 sano. < 1.5 zona de riesgo.
  tags: [icr, interest, debt]

- category: debt
  title: "LTV — Loan to Value (real estate)"
  content: |
    Loan to Value en inmobiliario: principal_deuda / valor_activo.
    Banca europea hipotecas residenciales: 70-80%. Comercial: 60-70%. CARE: distinto al LTV de SaaS.
  tags: [ltv, real_estate, mortgage]

- category: debt
  title: "Amortización francesa"
  content: |
    Cuota fija constante donde el componente de intereses decrece y el de principal crece.
    Estándar en hipotecas residenciales en España y Europa.
  tags: [amortization, french, mortgage]

- category: pnl
  title: "EBITDA"
  content: |
    Earnings Before Interest, Taxes, Depreciation, Amortization.
    Métrica de rentabilidad operativa "core" — ignora financiación y contabilidad CapEx.
    Margen EBITDA SaaS maduro: 20-40%. Real estate operativo: 60-80%.
  tags: [ebitda, profitability]

- category: pnl
  title: "Gross Margin"
  content: |
    (Revenue - COGS) / Revenue. Para SaaS típico: 70-85%. Servicios: 30-50%.
    Por debajo del benchmark de sector indica problema de pricing o de costes variables.
  tags: [gross_margin, cogs]

- category: pnl
  title: "Tax loss carryforward"
  content: |
    Pérdidas fiscales pueden compensar beneficios futuros. En España hay límite del 70% de base imponible positiva.
    Importante en modelos de startups: años de pérdida reducen tax bill cuando hay ganancias.
  tags: [tax, carryforward, spain]

- category: capex
  title: "Depreciación lineal"
  content: |
    CapEx se reparte uniformemente durante la vida útil del activo (años).
    Ordenadores: 4 años. Mobiliario: 10 años. Edificios: 33 años.
    Reduce el beneficio fiscal pero no afecta a caja después de la compra inicial.
  tags: [depreciation, capex]

- category: capex
  title: "Maintenance vs Growth CapEx"
  content: |
    Maintenance CapEx mantiene la capacidad actual. Growth CapEx expande.
    Buffett: FCF "owner earnings" = NI + D&A - maintenance CapEx (más conservador que FCF estándar).
  tags: [capex, maintenance, growth]

- category: saas
  title: "Cohort Retention"
  content: |
    Análisis de churn por cohorte de adquisición. Cada mes se mira qué % de la cohorte original sigue activa.
    SaaS B2B sano: 90-95% retención a 12 meses. < 80% indica problema de fit/producto.
  tags: [cohort, churn, retention, saas]

- category: saas
  title: "ARR — Annual Recurring Revenue"
  content: |
    Revenue recurrente anualizado: MRR × 12.
    Métrica north star SaaS. Múltiplos de valoración se aplican sobre ARR.
  tags: [arr, mrr, saas]

- category: saas
  title: "Net Revenue Retention (NRR)"
  content: |
    (Revenue de cohorte hoy / Revenue inicial de cohorte) - incluye expansion - churn.
    SaaS top quartile: NRR > 110%. > 130% es world-class.
  tags: [nrr, expansion, retention]

- category: framework
  title: "Cuándo usar Gordon vs Exit Multiple"
  content: |
    Gordon (perpetuity): adecuado para empresas estables con crecimiento sostenible y bajo riesgo. Requiere WACC > g.
    Exit multiple: adecuado para escenarios donde se contempla venta en horizonte concreto (5-7 años), startups, PE.
    En SaaS early-stage usar exit multiple ARR. En empresa madura usar Gordon.
  tags: [valuation, methodology, framework]

- category: framework
  title: "Interpretar LTV/CAC"
  content: |
    LTV/CAC < 1: estás perdiendo dinero con cada cliente nuevo.
    LTV/CAC entre 1 y 3: zona gris, hay que mejorar.
    LTV/CAC >= 3: sano. >= 5: very strong unit economics.
    LTV/CAC > 10: posible underinvestment en ventas — podrías acelerar.
  tags: [framework, ltv, cac, decision]

- category: framework
  title: "Diagnosis cuando runway < 12 meses"
  content: |
    Acciones en orden de impacto:
    1. Levantar capital (preferred si fundamentals OK).
    2. Aumentar precio (test A/B en cohortes nuevas).
    3. Reducir CAC: optimizar canales más caros.
    4. Reducir burn fijo: revisar OPEX no esencial.
    5. Cobrar más rápido: bajar DSO, prepayments.
  tags: [framework, runway, diagnosis]

- category: framework
  title: "Cuándo evaluar levantar deuda vs equity"
  content: |
    Deuda apropiada si: DSCR proyectado > 1.5, ICR > 3, asset-backed, cashflow predecible.
    Equity apropiado si: alta incertidumbre, cashflow negativo, ramp largo.
    Mix recomendado growth-stage SaaS: 80% equity / 20% venture debt cuando ARR > €1M.
  tags: [framework, debt, equity, capital_structure]

- category: real_estate
  title: "Cap Rate"
  content: |
    Net Operating Income / Property Value. Yield bruto del activo inmobiliario.
    Madrid prime oficinas 2024: 4.5-5.5%. Residencial: 3-4%. Logística: 5.5-6.5%.
  tags: [cap_rate, real_estate, yield]

- category: real_estate
  title: "Gross Yield vs Net Yield"
  content: |
    Gross: alquiler anual / valor. Net: descuenta IBI, comunidad, seguros, vacancy, mantenimiento (~25-30% del gross).
    Comparar siempre net entre activos para decisión real.
  tags: [yield, real_estate]
```

(30 entries — solid starter knowledge base. Plan 5 can extend per-sector.)

- [ ] **Step 2: Write seed loader + failing tests**

`tests/unit/test_knowledge_seed.py`:
```python
import pytest

from asset_finance_modeler.intelligence.embeddings import LocalEmbeddingProvider
from asset_finance_modeler.intelligence.knowledge.base import KnowledgeBase
from asset_finance_modeler.intelligence.knowledge.seed import seed_default_knowledge


@pytest.fixture
def kb(tmp_path):
    base = KnowledgeBase(
        db_path=str(tmp_path / "kb.db"),
        index_path=str(tmp_path / "kb.faiss"),
        embedding_provider=LocalEmbeddingProvider(),
    )
    base.initialize()
    return base


def test_seed_populates_knowledge_base(kb):
    count = seed_default_knowledge(kb)
    assert count >= 25  # we wrote 30 entries
    cats = {c["name"] for c in kb.list_categories()}
    assert "unit_economics" in cats
    assert "valuation" in cats
    assert "debt" in cats


def test_seeded_kb_search_returns_relevant_result(kb):
    seed_default_knowledge(kb)
    results = kb.search("how much should I pay to get a new SaaS customer?", top_k=3)
    titles = [r.entry.title for r in results]
    assert any("CAC" in t for t in titles)


def test_seeded_kb_search_in_spanish(kb):
    seed_default_knowledge(kb)
    results = kb.search("cuántos meses tarda en recuperarse el coste de un cliente nuevo", top_k=3)
    titles = [r.entry.title for r in results]
    assert any("Payback" in t or "CAC" in t for t in titles)
```

- [ ] **Step 3: Run tests, verify fail**

```bash
pytest tests/unit/test_knowledge_seed.py -v
```

Expected: ImportError on `seed_default_knowledge`.

- [ ] **Step 4: Implement loader**

`src/asset_finance_modeler/intelligence/knowledge/seed.py`:
```python
from importlib.resources import files

import yaml

from .base import KnowledgeBase, KnowledgeEntry


def seed_default_knowledge(kb: KnowledgeBase) -> int:
    """Populate a KnowledgeBase from the bundled seed.yaml. Returns count added."""
    seed_path = files("asset_finance_modeler.intelligence.knowledge.data") / "seed.yaml"
    with seed_path.open() as f:
        entries = yaml.safe_load(f)

    added = 0
    for raw in entries:
        kb.add(KnowledgeEntry(
            title=raw["title"],
            content=raw["content"],
            category=raw.get("category", "general"),
            tags=raw.get("tags", []),
            tenant_id=None,  # global knowledge
        ))
        added += 1
    return added
```

- [ ] **Step 5: Update pyproject.toml package-data**

In `pyproject.toml`, extend `[tool.setuptools.package-data]`:
```toml
[tool.setuptools.package-data]
"asset_finance_modeler.assets.saas.presets" = ["*.yaml"]
"asset_finance_modeler.intelligence.knowledge.data" = ["*.yaml"]
```

Re-install: `pip install -e ".[dev]"`.

- [ ] **Step 6: Run tests, verify pass**

```bash
pytest tests/unit/test_knowledge_seed.py -v
```

Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add src/asset_finance_modeler/intelligence/knowledge/ tests/unit/test_knowledge_seed.py pyproject.toml
git commit -m "feat(intelligence): seed 30 financial knowledge entries (concepts + frameworks + benchmarks)"
```

---

### Task 4: Knowledge MCP tools (search, add, list_categories)

**Files:**
- Create: `src/asset_finance_modeler/mcp_server/tools/knowledge.py`
- Modify: `src/asset_finance_modeler/mcp_server/registry.py`
- Create: `tests/unit/test_mcp_tools_knowledge.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_mcp_tools_knowledge.py`:
```python
import pytest

from asset_finance_modeler.mcp_server.registry import build_registry
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore


@pytest.fixture
def reg(tmp_path):
    store = SQLiteScenarioStore(str(tmp_path / "scn.db"))
    store.initialize()
    return build_registry(store, kb_db_path=str(tmp_path / "kb.db"), kb_index_path=str(tmp_path / "kb.faiss"))


def test_knowledge_search_tool_returns_results(reg):
    add = reg["finance.knowledge.add"].handler
    add({
        "title": "Test concept",
        "content": "Customer Acquisition Cost is fundamental for SaaS",
        "category": "test",
    })
    search = reg["finance.knowledge.search"].handler
    out = search({"query": "how do I measure customer acquisition?", "top_k": 3})
    assert "results" in out
    assert len(out["results"]) >= 1
    assert "score" in out["results"][0]


def test_knowledge_list_categories(reg):
    add = reg["finance.knowledge.add"].handler
    add({"title": "A", "content": "a", "category": "cat1"})
    add({"title": "B", "content": "b", "category": "cat2"})
    list_cats = reg["finance.knowledge.list_categories"].handler
    out = list_cats({})
    names = [c["name"] for c in out["categories"]]
    assert "cat1" in names
    assert "cat2" in names


def test_knowledge_add_returns_id(reg):
    add = reg["finance.knowledge.add"].handler
    out = add({"title": "New entry", "content": "Content here", "category": "test"})
    assert "id" in out
    assert out["id"].startswith("kn-")
```

- [ ] **Step 2: Run tests, verify fail**

```bash
pytest tests/unit/test_mcp_tools_knowledge.py -v
```

Expected: TypeError on `build_registry` (new kwargs) or KeyError on missing tools.

- [ ] **Step 3: Implement knowledge tools**

`src/asset_finance_modeler/mcp_server/tools/knowledge.py`:
```python
from typing import Any

from asset_finance_modeler.intelligence.knowledge.base import KnowledgeBase, KnowledgeEntry


def make_knowledge_search(kb: KnowledgeBase) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        results = kb.search(
            query=args["query"],
            top_k=args.get("top_k", 5),
            category=args.get("category"),
            tenant_id=args.get("tenant_id"),
        )
        return {
            "results": [
                {
                    "id": r.entry.id,
                    "title": r.entry.title,
                    "content": r.entry.content,
                    "category": r.entry.category,
                    "tags": r.entry.tags,
                    "tenant_id": r.entry.tenant_id,
                    "score": r.score,
                }
                for r in results
            ],
        }
    return _handle


def make_knowledge_add(kb: KnowledgeBase) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        entry_id = kb.add(KnowledgeEntry(
            title=args["title"],
            content=args["content"],
            category=args.get("category", "general"),
            tags=args.get("tags", []),
            tenant_id=args.get("tenant_id"),
        ))
        return {"id": entry_id}
    return _handle


def make_knowledge_list_categories(kb: KnowledgeBase) -> Any:
    def _handle(_args: dict[str, Any]) -> dict[str, Any]:
        return {"categories": kb.list_categories()}
    return _handle
```

- [ ] **Step 4: Modify build_registry to accept kb paths**

Edit `src/asset_finance_modeler/mcp_server/registry.py`:

Change the `build_registry` signature:
```python
def build_registry(
    store: SQLiteScenarioStore | None,
    kb_db_path: str | None = None,
    kb_index_path: str | None = None,
) -> dict[str, ToolSpec]:
```

And at the end of the function (just before `return`), wire knowledge tools:
```python
    # Knowledge base (optional)
    if kb_db_path is not None and kb_index_path is not None:
        from asset_finance_modeler.intelligence.embeddings import LocalEmbeddingProvider
        from asset_finance_modeler.intelligence.knowledge.base import KnowledgeBase
        from .tools.knowledge import (
            make_knowledge_add,
            make_knowledge_list_categories,
            make_knowledge_search,
        )

        kb = KnowledgeBase(
            db_path=kb_db_path,
            index_path=kb_index_path,
            embedding_provider=LocalEmbeddingProvider(),
        )
        kb.initialize()

        specs.extend([
            ToolSpec(
                name="finance.knowledge.search",
                description=(
                    "Search the financial knowledge base semantically. "
                    "Returns relevant concepts, formulas, benchmarks, frameworks. "
                    "Use this BEFORE answering technical financial questions."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "top_k": {"type": "integer", "default": 5},
                        "category": {"type": "string"},
                        "tenant_id": {"type": "string"},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                handler=make_knowledge_search(kb),
            ),
            ToolSpec(
                name="finance.knowledge.add",
                description="Add a new knowledge entry. Optional tenant_id for company-specific knowledge.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "content": {"type": "string"},
                        "category": {"type": "string", "default": "general"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "tenant_id": {"type": "string"},
                    },
                    "required": ["title", "content"],
                    "additionalProperties": False,
                },
                handler=make_knowledge_add(kb),
            ),
            ToolSpec(
                name="finance.knowledge.list_categories",
                description="List available knowledge categories with entry counts.",
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                handler=make_knowledge_list_categories(kb),
            ),
        ])

    return {s.name: s for s in specs}
```

Also update `server.py` to pass kb paths from env:

```python
def _build_app() -> tuple[Server, dict[str, ToolSpec]]:
    db_path = _default_db_path()
    store = SQLiteScenarioStore(db_path)
    store.initialize()

    # Knowledge base paths
    kb_dir = Path(db_path).parent
    kb_db_path = str(kb_dir / "knowledge.db")
    kb_index_path = str(kb_dir / "knowledge.faiss")

    registry = build_registry(store, kb_db_path=kb_db_path, kb_index_path=kb_index_path)
    # ... rest unchanged
```

- [ ] **Step 5: Run tests, verify pass**

```bash
pytest tests/unit/test_mcp_tools_knowledge.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add src/asset_finance_modeler/mcp_server/ tests/unit/test_mcp_tools_knowledge.py
git commit -m "feat(mcp): knowledge tools — search, add, list_categories (FAISS-backed)"
```

---

### Task 5: Workflow engine + initial workflows

**Files:**
- Create: `src/asset_finance_modeler/intelligence/workflows/__init__.py`
- Create: `src/asset_finance_modeler/intelligence/workflows/engine.py`
- Create: `src/asset_finance_modeler/intelligence/workflows/loader.py`
- Create: `src/asset_finance_modeler/intelligence/workflows/templates/__init__.py`
- Create: `src/asset_finance_modeler/intelligence/workflows/templates/pricing_impact_analysis.yaml`
- Create: `src/asset_finance_modeler/intelligence/workflows/templates/runway_diagnosis.yaml`
- Create: `src/asset_finance_modeler/intelligence/workflows/templates/unit_econ_review.yaml`
- Create: `src/asset_finance_modeler/intelligence/workflows/templates/valuation_summary.yaml`
- Create: `tests/unit/test_workflow_engine.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_workflow_engine.py`:
```python
import pytest

from asset_finance_modeler.intelligence.workflows.engine import WorkflowEngine
from asset_finance_modeler.intelligence.workflows.loader import (
    list_builtin_workflows,
    load_workflow,
)


def test_list_builtin_workflows_returns_at_least_4():
    workflows = list_builtin_workflows()
    ids = {w["id"] for w in workflows}
    assert "pricing_impact_analysis" in ids
    assert "runway_diagnosis" in ids
    assert "unit_econ_review" in ids
    assert "valuation_summary" in ids


def test_load_workflow_parses_yaml():
    wf = load_workflow("pricing_impact_analysis")
    assert wf["id"] == "pricing_impact_analysis"
    assert "inputs" in wf
    assert "steps" in wf


def test_engine_variable_substitution():
    eng = WorkflowEngine(tool_dispatcher=lambda name, args: {"echo": args})
    workflow = {
        "id": "echo_test",
        "inputs": [{"name": "x", "type": "number"}],
        "steps": [
            {"id": "echo", "tool": "test.echo", "args": {"value": "${x}"}, "capture": "result"},
        ],
        "output": {"got": "${result.echo.value}"},
    }
    out = eng.run(workflow, {"x": 42})
    assert out["got"] == 42


def test_engine_runs_pricing_impact_via_mock_dispatcher():
    called: list[tuple[str, dict]] = []

    def mock(name, args):
        called.append((name, args))
        if name == "finance.simulate.clone_scenario":
            return {"scenario_id": f"clone-{args.get('name', 'x')}", "name": args.get("name", "x")}
        if name == "finance.simulate.run":
            return {"summary": {"revenue_y1": 100000}}
        if name == "finance.simulate.compare":
            return {"table": {"scenarios": ["a", "b", "c"], "metrics": {"revenue_y1": [100, 200, 300]}}}
        return {}

    eng = WorkflowEngine(tool_dispatcher=mock)
    wf = load_workflow("pricing_impact_analysis")
    out = eng.run(wf, {"base_scenario_id": "scn-base", "prices": [200, 300, 400]})
    # 3 clones + 3 runs + 1 compare = 7 tool calls
    assert len(called) >= 7
    tools_called = [c[0] for c in called]
    assert tools_called.count("finance.simulate.clone_scenario") == 3
    assert tools_called.count("finance.simulate.run") == 3
    assert "comparison" in out


def test_engine_required_input_missing_raises():
    eng = WorkflowEngine(tool_dispatcher=lambda n, a: {})
    workflow = {
        "id": "x", "inputs": [{"name": "must_have", "type": "string", "required": True}],
        "steps": [], "output": {},
    }
    with pytest.raises(ValueError, match="required input"):
        eng.run(workflow, {})
```

- [ ] **Step 2: Run tests, verify fail**

```bash
pytest tests/unit/test_workflow_engine.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement engine + loader**

`src/asset_finance_modeler/intelligence/workflows/__init__.py`: empty file.

`src/asset_finance_modeler/intelligence/workflows/templates/__init__.py`: empty file.

`src/asset_finance_modeler/intelligence/workflows/loader.py`:
```python
from importlib.resources import files
from typing import Any

import yaml


def list_builtin_workflows() -> list[dict[str, Any]]:
    """List all built-in workflow templates with id + name + description."""
    out: list[dict[str, Any]] = []
    base = files("asset_finance_modeler.intelligence.workflows.templates")
    for resource in base.iterdir():
        name = resource.name
        if not name.endswith(".yaml"):
            continue
        with resource.open() as f:
            data = yaml.safe_load(f)
        out.append({
            "id": data["id"],
            "name": data.get("name", data["id"]),
            "description": data.get("description", ""),
            "inputs": data.get("inputs", []),
        })
    return out


def load_workflow(workflow_id: str) -> dict[str, Any]:
    """Load a workflow YAML by id."""
    path = files("asset_finance_modeler.intelligence.workflows.templates") / f"{workflow_id}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"workflow {workflow_id!r} not found")
    with path.open() as f:
        return yaml.safe_load(f)
```

`src/asset_finance_modeler/intelligence/workflows/engine.py`:
```python
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

ToolDispatcher = Callable[[str, dict[str, Any]], Any]

_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _resolve_path(context: dict[str, Any], path: str) -> Any:
    """Resolve dotted path against context dict. Supports list indexing [0]."""
    parts = re.split(r"\.|\[|\]", path)
    parts = [p for p in parts if p]
    current: Any = context
    for p in parts:
        if isinstance(current, list):
            current = current[int(p)]
        elif isinstance(current, dict):
            current = current[p]
        else:
            raise KeyError(f"cannot resolve {path!r} (stuck at {type(current).__name__})")
    return current


def _substitute(value: Any, context: dict[str, Any]) -> Any:
    """Recursively substitute ${var.path} in strings within nested structure."""
    if isinstance(value, str):
        # If the entire string is a single variable reference, return the typed value
        m = _VAR_PATTERN.fullmatch(value.strip())
        if m:
            return _resolve_path(context, m.group(1).strip())
        # Otherwise, interpolate as string
        def repl(match: re.Match[str]) -> str:
            return str(_resolve_path(context, match.group(1).strip()))
        return _VAR_PATTERN.sub(repl, value)
    if isinstance(value, dict):
        return {k: _substitute(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute(v, context) for v in value]
    return value


@dataclass
class WorkflowEngine:
    tool_dispatcher: ToolDispatcher

    def run(self, workflow: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
        # Validate inputs
        for spec in workflow.get("inputs", []):
            if spec.get("required", True) and spec["name"] not in inputs:
                raise ValueError(f"required input {spec['name']!r} missing")

        context: dict[str, Any] = dict(inputs)

        for step in workflow.get("steps", []):
            foreach = step.get("foreach")
            if foreach is not None:
                # Run the step once per item in the foreach array
                items = _substitute(foreach, context)
                if not isinstance(items, list):
                    raise ValueError(f"foreach must resolve to a list, got {type(items).__name__}")
                as_var = step.get("as", "item")
                captures: list[Any] = []
                for item in items:
                    iter_context = dict(context, **{as_var: item})
                    resolved_args = _substitute(step.get("args", {}), iter_context)
                    result = self.tool_dispatcher(step["tool"], resolved_args)
                    captures.append(result)
                capture_key = step.get("capture")
                if capture_key:
                    context[capture_key] = captures
            else:
                resolved_args = _substitute(step.get("args", {}), context)
                result = self.tool_dispatcher(step["tool"], resolved_args)
                capture_key = step.get("capture")
                if capture_key:
                    context[capture_key] = result

        # Build output
        output_spec = workflow.get("output", {})
        output = _substitute(output_spec, context)
        return output
```

- [ ] **Step 4: Create workflow templates**

`src/asset_finance_modeler/intelligence/workflows/templates/pricing_impact_analysis.yaml`:
```yaml
id: pricing_impact_analysis
name: "Análisis de impacto de cambio de precio"
description: |
  Clona un scenario baseline a N variantes con diferentes precios, las ejecuta,
  y devuelve una tabla comparativa de métricas clave.
inputs:
  - name: base_scenario_id
    type: string
    required: true
    description: "ID del scenario baseline"
  - name: prices
    type: array
    required: true
    description: "Lista de precios a comparar (€/unidad/periodo)"
steps:
  - id: clone_variants
    foreach: "${prices}"
    as: price
    tool: finance.simulate.clone_scenario
    args:
      scenario_id: "${base_scenario_id}"
      name: "pricing-${price}"
      overrides:
        "revenue.sources[0].pricing.per_unit_per_period": "${price}"
    capture: variants
  - id: run_variants
    foreach: "${variants}"
    as: variant
    tool: finance.simulate.run
    args:
      scenario_id: "${variant.scenario_id}"
    capture: runs
  - id: run_baseline
    tool: finance.simulate.run
    args:
      scenario_id: "${base_scenario_id}"
    capture: baseline_run
  - id: build_compare_ids
    tool: noop.identity
    args:
      ids: "${variants}"
    capture: variant_ids
output:
  baseline: "${baseline_run.summary}"
  variants: "${runs}"
  variant_ids: "${variants}"
  comparison: |
    Run finance.simulate.compare with scenario_ids = [base + each variant.scenario_id] to get the delta table.
```

`src/asset_finance_modeler/intelligence/workflows/templates/runway_diagnosis.yaml`:
```yaml
id: runway_diagnosis
name: "Diagnóstico de runway crítico"
description: |
  Si runway < 12 meses, explora 3 acciones: aumentar precio, reducir CAC, reducir burn fijo.
  Devuelve el escenario más favorable para la caja.
inputs:
  - name: base_scenario_id
    type: string
    required: true
steps:
  - id: baseline_run
    tool: finance.simulate.run
    args:
      scenario_id: "${base_scenario_id}"
    capture: baseline
  - id: higher_price
    tool: finance.simulate.clone_scenario
    args:
      scenario_id: "${base_scenario_id}"
      name: "diag-higher-price"
      overrides:
        "revenue.sources[0].pricing.per_unit_per_period": 350
    capture: hp_scn
  - id: hp_run
    tool: finance.simulate.run
    args:
      scenario_id: "${hp_scn.scenario_id}"
    capture: hp_result
  - id: lower_cac
    tool: finance.simulate.clone_scenario
    args:
      scenario_id: "${base_scenario_id}"
      name: "diag-lower-cac"
      overrides:
        "revenue.sources[0].acquisition.cac_per_customer": 500
    capture: lc_scn
  - id: lc_run
    tool: finance.simulate.run
    args:
      scenario_id: "${lc_scn.scenario_id}"
    capture: lc_result
  - id: lower_burn
    tool: finance.simulate.clone_scenario
    args:
      scenario_id: "${base_scenario_id}"
      name: "diag-lower-burn"
      overrides:
        "operating_expenses.infra_fixed_eur": 800
        "operating_expenses.marketing_eur": 1000
    capture: lb_scn
  - id: lb_run
    tool: finance.simulate.run
    args:
      scenario_id: "${lb_scn.scenario_id}"
    capture: lb_result
output:
  baseline_runway: "${baseline.summary.runway_months}"
  higher_price_runway: "${hp_result.summary.runway_months}"
  lower_cac_runway: "${lc_result.summary.runway_months}"
  lower_burn_runway: "${lb_result.summary.runway_months}"
  scenario_ids:
    baseline: "${base_scenario_id}"
    higher_price: "${hp_scn.scenario_id}"
    lower_cac: "${lc_scn.scenario_id}"
    lower_burn: "${lb_scn.scenario_id}"
```

`src/asset_finance_modeler/intelligence/workflows/templates/unit_econ_review.yaml`:
```yaml
id: unit_econ_review
name: "Revisión de unit economics"
description: |
  Ejecuta scenario y devuelve métricas de unit economics con interpretación.
inputs:
  - name: scenario_id
    type: string
    required: true
steps:
  - id: run
    tool: finance.simulate.run
    args:
      scenario_id: "${scenario_id}"
  - id: fetch
    tool: finance.simulate.get_results
    args:
      scenario_id: "${scenario_id}"
      view: "unit_econ"
    capture: ue
  - id: summary
    tool: finance.simulate.get_results
    args:
      scenario_id: "${scenario_id}"
      view: "summary"
    capture: sum
output:
  arpu_end: "${ue.unit_econ.arpu[-1]}"
  cac_end: "${ue.unit_econ.cac[-1]}"
  ltv_end: "${ue.unit_econ.ltv[-1]}"
  ltv_cac_end: "${sum.summary.ltv_cac_end}"
  payback_months_end: "${ue.unit_econ.payback_months[-1]}"
  gross_margin_end: "${ue.unit_econ.gross_margin[-1]}"
  interpretation_hint: |
    LTV/CAC < 3 => problemático. >= 3 sano. >= 5 muy fuerte.
    Payback > 18 meses => CAC alto o pricing bajo.
    Gross margin < 70% en SaaS => revisar COGS variable.
```

`src/asset_finance_modeler/intelligence/workflows/templates/valuation_summary.yaml`:
```yaml
id: valuation_summary
name: "Resumen de valoración"
description: |
  Devuelve enterprise value + sensitivity grid si está disponible + key drivers.
inputs:
  - name: scenario_id
    type: string
    required: true
steps:
  - id: run
    tool: finance.simulate.run
    args:
      scenario_id: "${scenario_id}"
  - id: fetch_val
    tool: finance.simulate.get_results
    args:
      scenario_id: "${scenario_id}"
      view: "valuation"
    capture: val
  - id: fetch_sum
    tool: finance.simulate.get_results
    args:
      scenario_id: "${scenario_id}"
      view: "summary"
    capture: sum
  - id: fetch_sens
    tool: finance.simulate.get_results
    args:
      scenario_id: "${scenario_id}"
      view: "sensitivity"
    capture: sens
output:
  enterprise_value: "${val.valuation.enterprise_value}"
  pv_explicit: "${val.valuation.pv_explicit}"
  pv_terminal: "${val.valuation.pv_terminal}"
  terminal_value: "${val.valuation.terminal_value}"
  revenue_y1: "${sum.summary.revenue_y1}"
  ebitda_margin_end: "${sum.summary.ebitda_margin_end}"
  sensitivity_grid: "${sens.sensitivity}"
```

- [ ] **Step 5: Update package-data**

In `pyproject.toml`:
```toml
[tool.setuptools.package-data]
"asset_finance_modeler.assets.saas.presets" = ["*.yaml"]
"asset_finance_modeler.intelligence.knowledge.data" = ["*.yaml"]
"asset_finance_modeler.intelligence.workflows.templates" = ["*.yaml"]
```

Re-install: `pip install -e ".[dev]"`.

- [ ] **Step 6: Run tests, verify pass**

```bash
pytest tests/unit/test_workflow_engine.py -v
```

Expected: 5 passed. (The mock dispatcher means the test doesn't need a real model to run.)

- [ ] **Step 7: Commit**

```bash
git add src/asset_finance_modeler/intelligence/workflows/ tests/unit/test_workflow_engine.py pyproject.toml
git commit -m "feat(intelligence): workflow engine + 4 templates (pricing/runway/unit_econ/valuation)"
```

---

### Task 6: Workflow MCP tools (list, describe, run)

**Files:**
- Create: `src/asset_finance_modeler/mcp_server/tools/workflows.py`
- Modify: `src/asset_finance_modeler/mcp_server/registry.py`
- Create: `tests/unit/test_mcp_tools_workflows.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_mcp_tools_workflows.py`:
```python
import pytest

from asset_finance_modeler.mcp_server.registry import build_registry
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore


@pytest.fixture
def reg_with_baseline(tmp_path):
    store = SQLiteScenarioStore(str(tmp_path / "s.db"))
    store.initialize()
    reg = build_registry(store, kb_db_path=str(tmp_path / "kb.db"), kb_index_path=str(tmp_path / "kb.faiss"))
    baseline_id = reg["finance.simulate.load_baseline"].handler(
        {"model": "gestnova", "preset": "gestnova"}
    )["scenario_id"]
    return reg, baseline_id


def test_workflows_list_returns_templates(reg_with_baseline):
    reg, _ = reg_with_baseline
    out = reg["finance.workflows.list"].handler({})
    ids = {w["id"] for w in out["workflows"]}
    assert "pricing_impact_analysis" in ids
    assert "valuation_summary" in ids


def test_workflows_describe(reg_with_baseline):
    reg, _ = reg_with_baseline
    out = reg["finance.workflows.describe"].handler({"workflow_id": "pricing_impact_analysis"})
    assert out["id"] == "pricing_impact_analysis"
    assert "inputs" in out
    input_names = {i["name"] for i in out["inputs"]}
    assert "base_scenario_id" in input_names
    assert "prices" in input_names


def test_workflows_describe_missing(reg_with_baseline):
    reg, _ = reg_with_baseline
    out = reg["finance.workflows.describe"].handler({"workflow_id": "nope"})
    assert "error" in out


def test_workflows_run_valuation_summary(reg_with_baseline):
    reg, baseline_id = reg_with_baseline
    out = reg["finance.workflows.run"].handler({
        "workflow_id": "valuation_summary",
        "inputs": {"scenario_id": baseline_id},
    })
    assert "enterprise_value" in out
    assert out["enterprise_value"] > 0
```

- [ ] **Step 2: Run tests, verify fail**

```bash
pytest tests/unit/test_mcp_tools_workflows.py -v
```

Expected: KeyError on missing tools.

- [ ] **Step 3: Implement workflow tools**

`src/asset_finance_modeler/mcp_server/tools/workflows.py`:
```python
from typing import Any

from asset_finance_modeler.intelligence.workflows.engine import WorkflowEngine
from asset_finance_modeler.intelligence.workflows.loader import (
    list_builtin_workflows,
    load_workflow,
)


def handle_workflows_list(_args: dict[str, Any]) -> dict[str, Any]:
    return {"workflows": list_builtin_workflows()}


def handle_workflows_describe(args: dict[str, Any]) -> dict[str, Any]:
    try:
        wf = load_workflow(args["workflow_id"])
    except FileNotFoundError as exc:
        return {"error": str(exc)}
    return {
        "id": wf["id"],
        "name": wf.get("name", wf["id"]),
        "description": wf.get("description", ""),
        "inputs": wf.get("inputs", []),
        "steps_count": len(wf.get("steps", [])),
    }


def make_workflows_run(registry_provider: Any) -> Any:
    """`registry_provider` is a callable that returns the current registry
    (avoids circular reference at registry-build time)."""
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        try:
            wf = load_workflow(args["workflow_id"])
        except FileNotFoundError as exc:
            return {"error": str(exc)}

        def dispatcher(tool_name: str, tool_args: dict[str, Any]) -> Any:
            if tool_name == "noop.identity":
                return tool_args
            registry = registry_provider()
            spec = registry.get(tool_name)
            if spec is None:
                raise ValueError(f"workflow referenced unknown tool: {tool_name}")
            return spec.handler(tool_args)

        engine = WorkflowEngine(tool_dispatcher=dispatcher)
        try:
            return engine.run(wf, args.get("inputs", {}))
        except ValueError as exc:
            return {"error": str(exc)}

    return _handle
```

- [ ] **Step 4: Wire into registry**

In `registry.py`, after the knowledge block, add (still inside `build_registry`):
```python
    # Workflows
    from .tools.workflows import (
        handle_workflows_describe,
        handle_workflows_list,
        make_workflows_run,
    )

    # Mutable holder for the registry so the dispatcher can resolve tools at run time
    _registry_holder: dict[str, dict] = {}

    def _registry_provider() -> dict:
        return _registry_holder["registry"]

    specs.extend([
        ToolSpec(
            name="finance.workflows.list",
            description="List built-in workflow templates with id+name+description+inputs.",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            handler=handle_workflows_list,
        ),
        ToolSpec(
            name="finance.workflows.describe",
            description="Describe a single workflow: full inputs spec + step count.",
            input_schema={
                "type": "object",
                "properties": {"workflow_id": {"type": "string"}},
                "required": ["workflow_id"],
                "additionalProperties": False,
            },
            handler=handle_workflows_describe,
        ),
        ToolSpec(
            name="finance.workflows.run",
            description=(
                "Execute a workflow by id. Pass inputs as object. "
                "Returns the workflow's defined output."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "workflow_id": {"type": "string"},
                    "inputs": {"type": "object", "additionalProperties": True},
                },
                "required": ["workflow_id"],
                "additionalProperties": False,
            },
            handler=make_workflows_run(_registry_provider),
        ),
    ])

    final_registry = {s.name: s for s in specs}
    _registry_holder["registry"] = final_registry
    return final_registry
```

(Replace the existing `return {s.name: s for s in specs}` line with this final block.)

- [ ] **Step 5: Run tests, verify pass**

```bash
pytest tests/unit/test_mcp_tools_workflows.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add src/asset_finance_modeler/mcp_server/ tests/unit/test_mcp_tools_workflows.py
git commit -m "feat(mcp): workflow tools — list, describe, run (with internal tool dispatcher)"
```

---

### Task 7: ContextMemory + MCP tools

**Files:**
- Create: `src/asset_finance_modeler/intelligence/context/__init__.py`
- Create: `src/asset_finance_modeler/intelligence/context/memory.py`
- Create: `src/asset_finance_modeler/mcp_server/tools/context.py`
- Modify: `src/asset_finance_modeler/mcp_server/registry.py`
- Modify: `src/asset_finance_modeler/mcp_server/server.py`
- Create: `tests/unit/test_context_memory.py`
- Create: `tests/unit/test_mcp_tools_context.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_context_memory.py`:
```python
import pytest

from asset_finance_modeler.intelligence.context.memory import ContextMemory
from asset_finance_modeler.intelligence.embeddings import LocalEmbeddingProvider


@pytest.fixture
def mem(tmp_path):
    m = ContextMemory(
        db_path=str(tmp_path / "ctx.db"),
        embedding_provider=LocalEmbeddingProvider(),
    )
    m.initialize()
    return m


def test_store_and_recent(mem):
    mem.store(tenant_id="t1", key="discussion-1", value="Talked about pricing 250", tags=["pricing"])
    mem.store(tenant_id="t1", key="discussion-2", value="Decided to run sensitivity on churn", tags=["churn"])
    recent = mem.recent(tenant_id="t1", limit=10)
    assert len(recent) == 2
    # most recent first
    assert recent[0].value == "Decided to run sensitivity on churn"


def test_search_semantic(mem):
    mem.store(tenant_id="t1", key="d1", value="The client asked about cash flow runway projections")
    mem.store(tenant_id="t1", key="d2", value="We covered the difference between LTV and CAC")
    mem.store(tenant_id="t1", key="d3", value="Today's weather is sunny")
    results = mem.search(tenant_id="t1", query="how long until we run out of cash?", top_k=2)
    values = [r.entry.value for r in results]
    assert any("runway" in v.lower() for v in values)


def test_multi_tenant_isolation(mem):
    mem.store(tenant_id="a", key="k1", value="company A private")
    mem.store(tenant_id="b", key="k2", value="company B private")
    results = mem.search(tenant_id="a", query="private", top_k=10)
    assert all(r.entry.tenant_id == "a" for r in results)
```

`tests/unit/test_mcp_tools_context.py`:
```python
import pytest

from asset_finance_modeler.mcp_server.registry import build_registry
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore


@pytest.fixture
def reg(tmp_path):
    store = SQLiteScenarioStore(str(tmp_path / "s.db"))
    store.initialize()
    return build_registry(
        store,
        kb_db_path=str(tmp_path / "kb.db"),
        kb_index_path=str(tmp_path / "kb.faiss"),
        ctx_db_path=str(tmp_path / "ctx.db"),
    )


def test_context_store_and_recent(reg):
    store_tool = reg["finance.context.store"].handler
    recent_tool = reg["finance.context.recent"].handler

    store_tool({
        "tenant_id": "gestnova",
        "key": "session-2026-05-15",
        "value": "Cliente Pedro pidió analisis pricing 250",
        "tags": ["pricing", "pedro"],
    })
    out = recent_tool({"tenant_id": "gestnova", "limit": 5})
    assert len(out["entries"]) == 1
    assert out["entries"][0]["value"].startswith("Cliente Pedro")


def test_context_search(reg):
    store_tool = reg["finance.context.store"].handler
    search_tool = reg["finance.context.search"].handler

    store_tool({"tenant_id": "t", "key": "k", "value": "Discussion about reducing customer acquisition cost"})
    out = search_tool({"tenant_id": "t", "query": "how to reduce CAC", "top_k": 1})
    assert len(out["results"]) == 1
```

- [ ] **Step 2: Run tests, verify fail**

```bash
pytest tests/unit/test_context_memory.py tests/unit/test_mcp_tools_context.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement ContextMemory**

`src/asset_finance_modeler/intelligence/context/__init__.py`: empty file.

`src/asset_finance_modeler/intelligence/context/memory.py`:
```python
from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from asset_finance_modeler.intelligence.embeddings import EmbeddingProvider

_SCHEMA = """
CREATE TABLE IF NOT EXISTS context_entries (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    tags_json TEXT NOT NULL DEFAULT '[]',
    embedding_blob BLOB,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ctx_tenant ON context_entries(tenant_id);
CREATE INDEX IF NOT EXISTS idx_ctx_tenant_created ON context_entries(tenant_id, created_at DESC);
"""


@dataclass
class ContextEntry:
    tenant_id: str
    key: str
    value: str
    tags: list[str] = field(default_factory=list)
    id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not self.id:
            self.id = f"ctx-{uuid.uuid4().hex[:8]}"


@dataclass
class ContextSearchResult:
    entry: ContextEntry
    score: float


class ContextMemory:
    def __init__(self, db_path: str, embedding_provider: EmbeddingProvider) -> None:
        self.db_path = db_path
        self.provider = embedding_provider

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    def store(self, tenant_id: str, key: str, value: str, tags: list[str] | None = None) -> str:
        entry = ContextEntry(tenant_id=tenant_id, key=key, value=value, tags=tags or [])
        vec = self.provider.embed(value).astype(np.float32)
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO context_entries
                   (id, tenant_id, key, value, tags_json, embedding_blob, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (entry.id, entry.tenant_id, entry.key, entry.value,
                 json.dumps(entry.tags), vec.tobytes(), entry.created_at.isoformat()),
            )
        return entry.id

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> ContextEntry:
        return ContextEntry(
            id=row["id"],
            tenant_id=row["tenant_id"],
            key=row["key"],
            value=row["value"],
            tags=json.loads(row["tags_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def recent(self, tenant_id: str, limit: int = 10) -> list[ContextEntry]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM context_entries WHERE tenant_id = ? ORDER BY created_at DESC LIMIT ?",
                (tenant_id, limit),
            ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def search(self, tenant_id: str, query: str, top_k: int = 5) -> list[ContextSearchResult]:
        qvec = self.provider.embed(query).astype(np.float32)
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM context_entries WHERE tenant_id = ?", (tenant_id,)
            ).fetchall()
        if not rows:
            return []
        # Compute cosine similarity manually (small N, no need for FAISS here)
        scored: list[ContextSearchResult] = []
        for row in rows:
            stored = np.frombuffer(row["embedding_blob"], dtype=np.float32)
            score = float(np.dot(qvec, stored))  # vectors are already normalized
            scored.append(ContextSearchResult(entry=self._row_to_entry(row), score=score))
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]
```

- [ ] **Step 4: Implement context MCP tools**

`src/asset_finance_modeler/mcp_server/tools/context.py`:
```python
from typing import Any

from asset_finance_modeler.intelligence.context.memory import ContextMemory


def make_context_store(mem: ContextMemory) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        entry_id = mem.store(
            tenant_id=args["tenant_id"],
            key=args["key"],
            value=args["value"],
            tags=args.get("tags", []),
        )
        return {"id": entry_id}
    return _handle


def make_context_search(mem: ContextMemory) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        results = mem.search(
            tenant_id=args["tenant_id"],
            query=args["query"],
            top_k=args.get("top_k", 5),
        )
        return {
            "results": [
                {
                    "id": r.entry.id,
                    "key": r.entry.key,
                    "value": r.entry.value,
                    "tags": r.entry.tags,
                    "tenant_id": r.entry.tenant_id,
                    "created_at": r.entry.created_at.isoformat(),
                    "score": r.score,
                }
                for r in results
            ],
        }
    return _handle


def make_context_recent(mem: ContextMemory) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        entries = mem.recent(tenant_id=args["tenant_id"], limit=args.get("limit", 10))
        return {
            "entries": [
                {
                    "id": e.id,
                    "key": e.key,
                    "value": e.value,
                    "tags": e.tags,
                    "tenant_id": e.tenant_id,
                    "created_at": e.created_at.isoformat(),
                }
                for e in entries
            ],
        }
    return _handle
```

- [ ] **Step 5: Wire into registry**

In `registry.py`, change `build_registry` signature:
```python
def build_registry(
    store: SQLiteScenarioStore | None,
    kb_db_path: str | None = None,
    kb_index_path: str | None = None,
    ctx_db_path: str | None = None,
) -> dict[str, ToolSpec]:
```

After the workflows block but before the final `_registry_holder` assignment, add:
```python
    # Context memory (optional)
    if ctx_db_path is not None:
        from asset_finance_modeler.intelligence.context.memory import ContextMemory
        from asset_finance_modeler.intelligence.embeddings import LocalEmbeddingProvider
        from .tools.context import (
            make_context_recent,
            make_context_search,
            make_context_store,
        )

        ctx_mem = ContextMemory(
            db_path=ctx_db_path,
            embedding_provider=LocalEmbeddingProvider(),
        )
        ctx_mem.initialize()

        specs.extend([
            ToolSpec(
                name="finance.context.store",
                description=(
                    "Store a piece of conversation context for later semantic retrieval. "
                    "Use to remember decisions, supuestos del cliente, follow-ups."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "tenant_id": {"type": "string"},
                        "key": {"type": "string"},
                        "value": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["tenant_id", "key", "value"],
                    "additionalProperties": False,
                },
                handler=make_context_store(ctx_mem),
            ),
            ToolSpec(
                name="finance.context.search",
                description=(
                    "Semantic search over stored context for a given tenant. "
                    "Use to recall previous discussions or decisions."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "tenant_id": {"type": "string"},
                        "query": {"type": "string"},
                        "top_k": {"type": "integer", "default": 5},
                    },
                    "required": ["tenant_id", "query"],
                    "additionalProperties": False,
                },
                handler=make_context_search(ctx_mem),
            ),
            ToolSpec(
                name="finance.context.recent",
                description="Return most recent context entries for a tenant (ordered by created_at desc).",
                input_schema={
                    "type": "object",
                    "properties": {
                        "tenant_id": {"type": "string"},
                        "limit": {"type": "integer", "default": 10},
                    },
                    "required": ["tenant_id"],
                    "additionalProperties": False,
                },
                handler=make_context_recent(ctx_mem),
            ),
        ])
```

Modify `server.py` `_build_app`:
```python
def _build_app() -> tuple[Server, dict[str, ToolSpec]]:
    db_path = _default_db_path()
    store = SQLiteScenarioStore(db_path)
    store.initialize()

    kb_dir = Path(db_path).parent
    registry = build_registry(
        store,
        kb_db_path=str(kb_dir / "knowledge.db"),
        kb_index_path=str(kb_dir / "knowledge.faiss"),
        ctx_db_path=str(kb_dir / "context.db"),
    )
    # ... rest unchanged
```

- [ ] **Step 6: Run tests, verify pass**

```bash
pytest tests/unit/test_context_memory.py tests/unit/test_mcp_tools_context.py -v
```

Expected: 6 passed.

- [ ] **Step 7: Commit**

```bash
git add src/asset_finance_modeler/intelligence/context/ src/asset_finance_modeler/mcp_server/ tests/unit/test_context_memory.py tests/unit/test_mcp_tools_context.py
git commit -m "feat(intelligence+mcp): ContextMemory + context.store/search/recent tools (multi-tenant)"
```

---

### Task 8: End-to-end intelligence smoke test

**Files:**
- Create: `tests/integration/test_intelligence_smoke.py`

- [ ] **Step 1: Write the integration test**

`tests/integration/test_intelligence_smoke.py`:
```python
"""Full intelligent toolkit smoke test:
- Seed knowledge base
- Run a workflow that touches multiple tools
- Store + retrieve context
- All multi-tenant
"""
import pytest

from asset_finance_modeler.intelligence.embeddings import LocalEmbeddingProvider
from asset_finance_modeler.intelligence.knowledge.base import KnowledgeBase
from asset_finance_modeler.intelligence.knowledge.seed import seed_default_knowledge
from asset_finance_modeler.mcp_server.registry import build_registry
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore


def test_intelligence_full_workflow(tmp_path):
    # Set up everything
    scn_store = SQLiteScenarioStore(str(tmp_path / "s.db"))
    scn_store.initialize()

    kb = KnowledgeBase(
        db_path=str(tmp_path / "kb.db"),
        index_path=str(tmp_path / "kb.faiss"),
        embedding_provider=LocalEmbeddingProvider(),
    )
    kb.initialize()
    seed_default_knowledge(kb)

    reg = build_registry(
        scn_store,
        kb_db_path=str(tmp_path / "kb.db"),
        kb_index_path=str(tmp_path / "kb.faiss"),
        ctx_db_path=str(tmp_path / "ctx.db"),
    )

    # 1. Discovery
    baseline_id = reg["finance.simulate.load_baseline"].handler(
        {"model": "gestnova", "preset": "gestnova"}
    )["scenario_id"]

    # 2. Use knowledge base to inform decision
    kb_results = reg["finance.knowledge.search"].handler({
        "query": "qué es un LTV CAC saludable", "top_k": 3,
    })
    assert any("LTV" in r["title"] or "CAC" in r["title"] for r in kb_results["results"])

    # 3. Run a workflow (valuation_summary)
    val_out = reg["finance.workflows.run"].handler({
        "workflow_id": "valuation_summary",
        "inputs": {"scenario_id": baseline_id},
    })
    assert "enterprise_value" in val_out
    assert val_out["enterprise_value"] > 0

    # 4. Run pricing impact workflow (multi-step with foreach)
    pricing_out = reg["finance.workflows.run"].handler({
        "workflow_id": "pricing_impact_analysis",
        "inputs": {"base_scenario_id": baseline_id, "prices": [200, 300, 400]},
    })
    assert "variants" in pricing_out
    assert len(pricing_out["variants"]) == 3

    # 5. Store decision in context memory
    reg["finance.context.store"].handler({
        "tenant_id": "gestnova",
        "key": "decision-pricing-2026-05",
        "value": "Decidimos mantener pricing 300€/agente tras analizar 200/300/400. EV óptimo en 300.",
        "tags": ["pricing", "decision"],
    })

    # 6. Recall context later
    recall = reg["finance.context.search"].handler({
        "tenant_id": "gestnova",
        "query": "qué decidimos sobre el precio",
        "top_k": 3,
    })
    assert len(recall["results"]) >= 1
    assert "300" in recall["results"][0]["value"]

    # 7. Multi-tenant isolation
    reg["finance.context.store"].handler({
        "tenant_id": "otra_empresa",
        "key": "secreto",
        "value": "Información privada de otra empresa",
    })
    leaked = reg["finance.context.search"].handler({
        "tenant_id": "gestnova",
        "query": "información privada",
        "top_k": 5,
    })
    assert all("otra empresa" not in r["value"] for r in leaked["results"])
```

- [ ] **Step 2: Run the test**

```bash
pytest tests/integration/test_intelligence_smoke.py -v
```

Expected: 1 passed (may take 60s — model loading + many operations).

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_intelligence_smoke.py
git commit -m "test(intelligence): end-to-end smoke (knowledge + workflows + context + multi-tenant)"
```

---

### Task 9: Final sanity gates + tool count verification

**Files:** none (verification only). Fix lint/types inline.

- [ ] **Step 1: Run all gates**

```bash
cd "/Users/rikyizquierdo/Documents/New project/asset-finance-modeler"
source .venv/bin/activate
pytest -q 2>&1 | tail -3
ruff check src/ tests/
mypy src/
```

Expected:
- pytest: ≥185 tests passing (162 + ~25 new)
- ruff: clean
- mypy: clean

Fix any errors inline. If FAISS/sentence-transformers have type issues, add `# type: ignore[import-untyped]` only on those imports.

- [ ] **Step 2: Verify total MCP tool count via subprocess**

```bash
(printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"s","version":"0"}}}' \
  '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'; sleep 5) | \
  PYTHONPATH=src ASSET_FINANCE_DB_PATH=/tmp/aft-p4-smoke.db .venv/bin/python -m asset_finance_modeler.mcp_server.server 2>/dev/null > /tmp/p4-resp.txt && \
python3 -c "
import json
with open('/tmp/p4-resp.txt') as f:
    for line in f:
        line = line.strip()
        if not line: continue
        m = json.loads(line)
        if m.get('id') == 2:
            tools = m['result']['tools']
            print(f'Total tools: {len(tools)}')
            for t in tools: print(f'  - {t[\"name\"]}')
"
```

Expected: **30 tools total** = 21 from V1 + 3 knowledge + 3 workflows + 3 context.

- [ ] **Step 3: Update README + INTEGRATION.md**

Update `README.md` to mention the intelligence layer with usage examples.

Update `docs/INTEGRATION.md` to show how Ian uses knowledge/workflows/context tools alongside the simulate tools.

- [ ] **Step 4: Final commit**

```bash
git add README.md docs/INTEGRATION.md
git commit -m "docs: README + INTEGRATION.md updated for Plan 4 intelligence layer"
# If sanity fixes were needed:
git add -u
git commit -m "chore: lint/type fixes after Plan 4 sanity" || true
```

---

## End of Plan 4 — Intelligent Toolkit complete

After this plan, the modeler is:
- **Foundation**: motor financiero completo (V1)
- **Scenarios**: persistencia + comparación + sensitivity (V2)
- **MCP surface**: 21 tools de `simulate.*` + 3 stubs `track.*` (V3)
- **Intelligence**: 9 tools nuevos (`knowledge.*` + `workflows.*` + `context.*`) — **30 tools en total**
- **Multi-tenant**: knowledge + context aislados por `tenant_id` para futuro multi-empresa
- **Listo para "departamento financiero" en producción**: Ian invoca workflows, busca conocimiento, recuerda contexto del cliente — sin LLM extra en la cadena

**Estimated effort:** 8-12 hours of subagent-driven execution. Plan 5+ (más asset types, portfolio aggregation, waterfall distributions) viene después si la demanda lo justifica.
