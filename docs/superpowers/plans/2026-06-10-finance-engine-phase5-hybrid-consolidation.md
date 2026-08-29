# Motor financiero — Fase 5: Consolidación híbrida / portfolio (E1, núcleo) — Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Permitir modelar un GRUPO de activos (portfolio / híbrido) consolidando sus flujos de caja reales y calculando KPIs consolidados (NPV, IRR, capex total, DSCR peor). Núcleo general de "cualquiera modela su portfolio con su agente". El acoplamiento físico fino (un activo carga a otro, p.ej. FV→BESS) se trata en F6 (modelo hybrid consolidated) donde se concreta contra números objetivo — aquí construimos la consolidación general y bien acotada.

**Architecture:** Helpers puros en `core/portfolio.py` (`consolidate_series`, `consolidate_outputs`) que suman las series por periodo de varios `FinancialOutput`. Un `HybridProject` (nuevo `assets/hybrid/model.py`) que corre N `InfrastructureModelConfig`, consolida, y calcula NPV (suma descontada del FCF consolidado con outlay en yr0 — MISMA convención que `npv_equity`, SIN terminal value Gordon) + IRR + capex total. Reutiliza `InfrastructureModel`, `compute_irr`. Aditivo, no toca el modelo existente.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, ruff PL, mypy strict.

**Repo/rama:** `/Users/rikyizquierdo/Documents/New project/asset-finance-modeler`, rama `feat/finance-engine-general-deals`.

**VERIFICAR ANTES:** las CLAVES reales de `FinancialOutput.pnl` y `.cashflow` (dicts de series) — `grep -n "pnl\[\|cashflow\[\|\"revenue\"\|\"ebitda\"\|\"fcf\"\|\"cfi\"" src/asset_finance_modeler/assets/infrastructure/model.py`. Y `summary["total_capex"]`. Confirmar cómo `InfrastructureModel(cfg).run()` devuelve y cómo obtener el FCF de proyecto anual por activo (el mismo `fcf_annual`/`project_cf` que usa `_compute_kpis`, o reconstruirlo desde `cashflow`). Solo correr `tests/core tests/unit tests/golden`.

---

## Task 1: Helpers puros de consolidación

**Files:**
- Modify: `src/asset_finance_modeler/core/portfolio.py` (añadir 2 funciones; NO tocar `analyze_portfolio`)
- Test: `tests/core/test_consolidation.py`

- [ ] **Step 1 — Failing test:**
```python
from asset_finance_modeler.core.portfolio import consolidate_series, consolidate_npv


def test_consolidate_series_sums_aligned_and_pads():
    a = [10.0, 10.0, 10.0]
    b = [5.0, 5.0]               # más corta -> se trata como 0 en el periodo que falta
    assert consolidate_series([a, b]) == [15.0, 15.0, 10.0]


def test_consolidate_series_empty():
    assert consolidate_series([]) == []


def test_consolidate_npv_plain_discounted_with_year0():
    # FCF consolidado: -100 (yr0) + 60 + 60; al 0% -> 20 ; al 10% -> -100+60/1.1+60/1.21
    fcf = [-100.0, 60.0, 60.0]
    assert abs(consolidate_npv(fcf, 0.0) - 20.0) < 1e-9
    assert abs(consolidate_npv(fcf, 0.10) - (-100 + 60 / 1.1 + 60 / 1.21)) < 1e-6
```

- [ ] **Step 2 — Run, verify FAIL** (ImportError):
`PYTHONPATH=src .venv/bin/pytest tests/core/test_consolidation.py -v`

- [ ] **Step 3 — Implement** (append to `core/portfolio.py`):
```python
def consolidate_series(series_list: list[list[float]]) -> list[float]:
    """Sum several per-period series element-wise. Shorter series are treated
    as 0 in the periods they don't cover (ramp-up/different horizons)."""
    n = max((len(s) for s in series_list), default=0)
    return [sum(s[t] for s in series_list if t < len(s)) for t in range(n)]


def consolidate_npv(fcf: list[float], discount_rate_annual: float) -> float:
    """NPV of a consolidated annual FCF series with the year-0 outlay at t=0
    (plain discounted sum, no terminal value). Convention matches equity NPV."""
    return sum(cf / ((1.0 + discount_rate_annual) ** t) for t, cf in enumerate(fcf))
```

- [ ] **Step 4 — Run, verify PASS** (3 passed). `tests/core -q` green. ruff+mypy clean.

- [ ] **Step 5 — Commit:**
```bash
git add src/asset_finance_modeler/core/portfolio.py tests/core/test_consolidation.py
git commit -m "feat(core): consolidate_series + consolidate_npv (consolidacion de portfolio)"
```

---

## Task 2: `HybridProject` — corre N activos y consolida

**Files:**
- Create: `src/asset_finance_modeler/assets/hybrid/__init__.py`
- Create: `src/asset_finance_modeler/assets/hybrid/model.py`
- Test: `tests/unit/test_hybrid_project.py`

**VERIFY FIRST:** how to get each asset's annual project FCF series from `InfrastructureModel(cfg).run()`. The model's `_compute_kpis` builds `project_cf = list(fcf_annual)` (annual). Find how `fcf_annual` is produced (likely from `cashflow["fcf"]` aggregated to annual, or directly available). If a clean annual project-FCF series isn't directly on the output, reconstruct it: annual FCF = annual operating cash flow minus annual capex spend (from `cashflow`/`summary`); confirm the real keys and use them. Also get per-asset `total_capex` (`summary["total_capex"]`) and annual revenue (`pnl["revenue"]` aggregated to annual). Report exactly what you used.

- [ ] **Step 1 — Failing test:**
```python
from asset_finance_modeler.assets.hybrid.model import HybridProject
from asset_finance_modeler.assets.infrastructure.loader import load_preset


def test_hybrid_consolidates_two_assets():
    fv = load_preset("solar_pv_50mw_spain")
    bess = load_preset("bess_20mw_4h")
    hp = HybridProject([fv, bess], discount_rate_annual=0.06)
    res = hp.run()
    # capex total = suma de los dos
    assert abs(res.total_capex - (res.asset_total_capex[0] + res.asset_total_capex[1])) < 1.0
    # NPV consolidado = NPV del FCF consolidado (suma de FCF por activo)
    assert res.npv == res.npv            # finito
    assert len(res.consolidated_fcf) >= 2
    assert isinstance(res.irr, float)
```

- [ ] **Step 2 — Run, verify FAIL** (ModuleNotFoundError hybrid.model).

- [ ] **Step 3 — Implement** (`assets/hybrid/model.py`):
```python
from __future__ import annotations

from dataclasses import dataclass, field

from asset_finance_modeler.assets.infrastructure.model import InfrastructureModel
from asset_finance_modeler.assets.infrastructure.schema import InfrastructureModelConfig
from asset_finance_modeler.core.portfolio import consolidate_series, consolidate_npv
from asset_finance_modeler.core.valuation import compute_irr


@dataclass
class HybridResult:
    consolidated_fcf: list[float]
    consolidated_revenue: list[float]
    total_capex: float
    asset_total_capex: list[float]
    npv: float
    irr: float


class HybridProject:
    """Runs several infrastructure assets and consolidates their cash flows
    into a single hybrid/portfolio result (summed FCF, combined NPV/IRR)."""

    def __init__(
        self,
        configs: list[InfrastructureModelConfig],
        discount_rate_annual: float = 0.06,
    ) -> None:
        self.configs = configs
        self.discount_rate_annual = discount_rate_annual

    def run(self) -> HybridResult:
        fcfs: list[list[float]] = []
        revs: list[list[float]] = []
        capexes: list[float] = []
        for cfg in self.configs:
            out = InfrastructureModel(cfg).run()
            fcfs.append(self._annual_project_fcf(out))
            revs.append(self._annual_revenue(out))
            capexes.append(float(out.summary["total_capex"]))
        cons_fcf = consolidate_series(fcfs)
        cons_rev = consolidate_series(revs)
        return HybridResult(
            consolidated_fcf=cons_fcf,
            consolidated_revenue=cons_rev,
            total_capex=sum(capexes),
            asset_total_capex=capexes,
            npv=consolidate_npv(cons_fcf, self.discount_rate_annual),
            irr=compute_irr(cons_fcf, 1),
        )

    @staticmethod
    def _annual_project_fcf(out: object) -> list[float]:
        ...  # VERIFY: derive the annual project FCF series from the real output

    @staticmethod
    def _annual_revenue(out: object) -> list[float]:
        ...  # VERIFY: annual revenue series from out.pnl["revenue"]
```
Implement the two `...` helpers against the REAL `FinancialOutput` structure you confirmed (annual project FCF and annual revenue). They must return annual series aligned to model years. Keep types clean for mypy (the `out` param can be typed as `FinancialOutput`).

- [ ] **Step 4 — Run, verify PASS.** Sanity print: `PYTHONPATH=src .venv/bin/python -c "from asset_finance_modeler.assets.hybrid.model import HybridProject; from asset_finance_modeler.assets.infrastructure.loader import load_preset; r=HybridProject([load_preset('solar_pv_50mw_spain'),load_preset('bess_20mw_4h')],0.06).run(); print('capex', round(r.total_capex), 'npv', round(r.npv), 'irr', round(r.irr,3))"`. Regression `tests/core tests/unit tests/golden -q`. ruff+mypy clean.

- [ ] **Step 5 — Commit:**
```bash
git add src/asset_finance_modeler/assets/hybrid/__init__.py src/asset_finance_modeler/assets/hybrid/model.py tests/unit/test_hybrid_project.py
git commit -m "feat(hybrid): HybridProject consolida N activos (FCF/NPV/IRR consolidados)"
```

---

## Self-Review
- **Spec coverage (E1 núcleo):** consolidación de caja de N activos + KPIs consolidados (Tasks 1+2) → capacidad "modelar un portfolio". El acoplamiento físico de energía (FV carga BESS, conexión compartida) se hace en F6 contra los números hybrid consolidated. ✅ (acotado a propósito)
- **Placeholders:** los `...` de Task 2 son explícitamente "verify-and-implement contra la estructura real" (como Fase 1 Task 4 / Fase 2 Task 3, que funcionó); el resto está codificado.
- **Type consistency:** `consolidate_series`, `consolidate_npv`, `HybridProject`, `HybridResult` coherentes.
- **NPV convention:** suma descontada con outlay yr0 (sin terminal Gordon) — coherente con `npv_equity` y con la validación hybrid consolidated de F6.

## Fases siguientes: F6 modelo hybrid consolidated (incl. acoplamiento físico FV→BESS) + validación nº a nº · F7 Excel-foto.
