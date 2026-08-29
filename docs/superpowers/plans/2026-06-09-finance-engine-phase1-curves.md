# Motor financiero — Fase 1: Subsistema de Curvas (E2) — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir al motor un subsistema de curvas general — un objeto `Curve` atachable a cualquier parámetro (precio, spread, ancillary, demanda, coste…), con fuentes librería/fases/puntos/crecimiento — y cablear los streams `arbitrage` y `ancillary` para que acepten curvas por fases. Base reutilizable para todos los deals (renovable o industrial).

**Architecture:** Reutiliza `core/drivers.py` (`GrowthCurve`, `expand_growth`). Añade `build_phased_curve` (fases de crecimiento compuesto) en `drivers.py`, un objeto `Curve` de primera clase en `core/curves.py`, una librería de curvas bancables citadas en `data/curves/*.yaml` con loader, y extiende `ArbitrageStream`/`AncillaryStream` + `engines/revenue.py` para usar curvas. Sin romper los ≥193 tests existentes (campos nuevos opcionales con defaults).

**Tech Stack:** Python 3.12, Pydantic v2 (schema), PyYAML (librería), pytest, ruff, mypy.

**Repo/rama:** `/Users/rikyizquierdo/Documents/New project/asset-finance-modeler`, rama `feat/finance-engine-general-deals`.

---

## File Structure

- `src/asset_finance_modeler/core/drivers.py` — **Modify**: añadir `CurvePhase` + `build_phased_curve`.
- `src/asset_finance_modeler/core/curves.py` — **Create**: objeto `Curve` (from_points/from_phases/from_growth/from_library, at/to_list).
- `src/asset_finance_modeler/core/curve_library.py` — **Create**: `load_curve(name)` que lee `data/curves/*.yaml`.
- `src/asset_finance_modeler/data/curves/*.yaml` — **Create**: curvas bancables citadas (spread DA ES, ancillary aFRR ES, captura solar ES).
- `src/asset_finance_modeler/assets/infrastructure/schema.py` — **Modify**: campos opcionales de curva en `ArbitrageStream` y `AncillaryStream`.
- `src/asset_finance_modeler/assets/infrastructure/engines/revenue.py` — **Modify**: `_arbitrage` y `_ancillary` usan curva si está presente.
- `tests/core/test_curves.py` — **Create**.
- `tests/core/test_curve_library.py` — **Create**.
- `tests/assets/infrastructure/test_revenue_curves.py` — **Create**.

---

## Task 1: `build_phased_curve` y `CurvePhase` en drivers.py

**Files:**
- Modify: `src/asset_finance_modeler/core/drivers.py` (añadir al final, tras `expand_growth`)
- Test: `tests/core/test_curves.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_curves.py
from asset_finance_modeler.core.drivers import CurvePhase, build_phased_curve


def test_build_phased_curve_three_phases():
    # hybrid consolidated spread: base 82, +2%/yr (y1-7), 0% (y8-15), -2%/yr (y16-30)
    phases = [CurvePhase(7, 0.02), CurvePhase(8, 0.0), CurvePhase(15, -0.02)]
    vals = build_phased_curve(82.0, phases, 30)
    assert len(vals) == 30
    assert vals[0] == 82.0                       # year 1 = base
    assert abs(vals[1] - 82.0 * 1.02) < 1e-9     # year 2 grows 2%
    assert abs(vals[6] - 82.0 * 1.02**6) < 1e-9  # year 7
    assert abs(vals[7] - vals[6]) < 1e-9         # year 8 flat (phase 2)
    assert vals[29] < vals[14]                   # year 30 below plateau (decay)


def test_build_phased_curve_pads_when_phases_short():
    vals = build_phased_curve(100.0, [CurvePhase(2, 0.10)], 5)
    assert len(vals) == 5
    assert abs(vals[4] - 100.0 * 1.10**4) < 1e-6  # last phase growth continues
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "/Users/rikyizquierdo/Documents/New project/asset-finance-modeler" && PYTHONPATH=src .venv/bin/pytest tests/core/test_curves.py -v`
Expected: FAIL — `ImportError: cannot import name 'CurvePhase'`.

- [ ] **Step 3: Write minimal implementation**

```python
# Append to src/asset_finance_modeler/core/drivers.py

@dataclass(frozen=True)
class CurvePhase:
    """A growth phase: `years` periods at `growth_pct` per-period compounding."""
    years: int
    growth_pct: float


def build_phased_curve(base: float, phases: list["CurvePhase"], periods: int) -> list[float]:
    """Build a value series from a base and phased compounding growth.

    Year 1 (index 0) = base. For each later period t, the value steps from the
    previous period by the growth rate of the active phase. Phases are consumed
    in order by their `years` span; if they run out before `periods`, the last
    phase's growth continues (ramp-then-hold semantics).
    """
    growth_by_period: list[float] = []
    for ph in phases:
        growth_by_period.extend([ph.growth_pct] * ph.years)
    if not growth_by_period:
        growth_by_period = [0.0]
    values: list[float] = []
    current = base
    for t in range(periods):
        if t > 0:
            g = growth_by_period[t - 1] if (t - 1) < len(growth_by_period) else growth_by_period[-1]
            current = current * (1.0 + g)
        values.append(current)
    return values
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src .venv/bin/pytest tests/core/test_curves.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/asset_finance_modeler/core/drivers.py tests/core/test_curves.py
git commit -m "feat(core): build_phased_curve + CurvePhase para curvas por fases"
```

---

## Task 2: Objeto `Curve` de primera clase

**Files:**
- Create: `src/asset_finance_modeler/core/curves.py`
- Test: `tests/core/test_curves.py` (añadir)

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/core/test_curves.py
from asset_finance_modeler.core.curves import Curve


def test_curve_from_points_and_at():
    c = Curve.from_points([10, 20, 30], name="x", source="test")
    assert c.at(0) == 10
    assert c.at(1) == 20
    assert c.at(5) == 30          # clamps to last
    assert c.to_list(4) == [10, 20, 30, 30]


def test_curve_from_phases():
    c = Curve.from_phases(82.0, [CurvePhase(7, 0.02), CurvePhase(23, 0.0)], 30)
    assert len(c.to_list(30)) == 30
    assert c.at(0) == 82.0


def test_curve_from_growth():
    c = Curve.from_growth(100.0, 0.05, 3)
    assert abs(c.at(2) - 100.0 * 1.05**2) < 1e-9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src .venv/bin/pytest tests/core/test_curves.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'asset_finance_modeler.core.curves'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/asset_finance_modeler/core/curves.py
from __future__ import annotations

from dataclasses import dataclass

from asset_finance_modeler.core.drivers import CurvePhase, build_phased_curve


@dataclass(frozen=True)
class Curve:
    """A projected value series attachable to any parameter (price, spread,
    ancillary, demand, cost…). Built from points, phases, growth, or library."""

    values: tuple[float, ...]
    name: str = ""
    source: str = ""

    @classmethod
    def from_points(cls, values: list[float], name: str = "", source: str = "") -> "Curve":
        return cls(tuple(float(v) for v in values), name, source)

    @classmethod
    def from_phases(
        cls, base: float, phases: list[CurvePhase], periods: int,
        name: str = "", source: str = "",
    ) -> "Curve":
        return cls(tuple(build_phased_curve(base, phases, periods)), name, source)

    @classmethod
    def from_growth(
        cls, base: float, rate: float, periods: int, name: str = "", source: str = "",
    ) -> "Curve":
        return cls(tuple(base * (1.0 + rate) ** i for i in range(periods)), name, source)

    @classmethod
    def from_library(cls, name: str) -> "Curve":
        from asset_finance_modeler.core.curve_library import load_curve
        return load_curve(name)

    def at(self, period_index: int) -> float:
        if not self.values:
            return 0.0
        return self.values[min(period_index, len(self.values) - 1)]

    def to_list(self, periods: int) -> list[float]:
        return [self.at(i) for i in range(periods)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src .venv/bin/pytest tests/core/test_curves.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/asset_finance_modeler/core/curves.py tests/core/test_curves.py
git commit -m "feat(core): objeto Curve (from_points/from_phases/from_growth/from_library)"
```

---

## Task 3: Librería de curvas bancables + loader

**Files:**
- Create: `src/asset_finance_modeler/data/curves/spread_da_es.yaml`
- Create: `src/asset_finance_modeler/core/curve_library.py`
- Test: `tests/core/test_curve_library.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_curve_library.py
import pytest

from asset_finance_modeler.core.curve_library import load_curve, list_curves


def test_list_curves_includes_seed():
    names = list_curves()
    assert "spread_da_es" in names


def test_load_curve_spread_da_es():
    c = load_curve("spread_da_es")
    assert c.name == "spread_da_es"
    assert "Agere" in c.source or "Modo" in c.source
    assert len(c.to_list(30)) == 30
    assert c.at(0) > 0


def test_load_unknown_curve_raises():
    with pytest.raises(KeyError):
        load_curve("does_not_exist_xyz")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src .venv/bin/pytest tests/core/test_curve_library.py -v`
Expected: FAIL — `ModuleNotFoundError: ...curve_library`.

- [ ] **Step 3a: Create the seed curve YAML**

```yaml
# src/asset_finance_modeler/data/curves/spread_da_es.yaml
name: spread_da_es
asset_type: bess
parameter: spread_eur_mwh
source: "Agere TB2 España (67/93/87 €/MWh 2024/25/H1-26) + Modo Energy abr-2026; base conservadora"
bankable: true
build: phases
base: 82.0
periods: 30
phases:
  - {years: 7, growth_pct: 0.02}
  - {years: 8, growth_pct: 0.0}
  - {years: 15, growth_pct: -0.02}
```

- [ ] **Step 3b: Write the loader**

```python
# src/asset_finance_modeler/core/curve_library.py
from __future__ import annotations

from pathlib import Path

import yaml

from asset_finance_modeler.core.curves import Curve
from asset_finance_modeler.core.drivers import CurvePhase

_CURVES_DIR = Path(__file__).resolve().parent.parent / "data" / "curves"


def list_curves() -> list[str]:
    if not _CURVES_DIR.is_dir():
        return []
    return sorted(p.stem for p in _CURVES_DIR.glob("*.yaml"))


def load_curve(name: str) -> Curve:
    path = _CURVES_DIR / f"{name}.yaml"
    if not path.is_file():
        raise KeyError(f"Curve '{name}' not found in {_CURVES_DIR}")
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    source = str(spec.get("source", ""))
    build = spec.get("build", "points")
    if build == "phases":
        phases = [CurvePhase(int(p["years"]), float(p["growth_pct"])) for p in spec["phases"]]
        return Curve.from_phases(float(spec["base"]), phases, int(spec["periods"]), name, source)
    if build == "growth":
        return Curve.from_growth(float(spec["base"]), float(spec["rate"]), int(spec["periods"]), name, source)
    return Curve.from_points([float(v) for v in spec["points"]], name, source)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src .venv/bin/pytest tests/core/test_curve_library.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Verify YAML ships in package & commit**

Run: `grep -n "data" "/Users/rikyizquierdo/Documents/New project/asset-finance-modeler/pyproject.toml" || echo "check package-data includes data/curves/*.yaml"`
(If package-data globs exclude yaml under data/, add `"data/curves/*.yaml"` to `[tool.setuptools.package-data]`.)

```bash
git add src/asset_finance_modeler/core/curve_library.py src/asset_finance_modeler/data/curves/spread_da_es.yaml tests/core/test_curve_library.py
git commit -m "feat(core): librería de curvas bancables + loader (seed spread_da_es)"
```

---

## Task 4: Cablear `arbitrage`/`ancillary` para usar curvas

**Files:**
- Modify: `src/asset_finance_modeler/assets/infrastructure/schema.py` (ArbitrageStream, AncillaryStream)
- Modify: `src/asset_finance_modeler/assets/infrastructure/engines/revenue.py` (`_arbitrage`, `_ancillary`)
- Test: `tests/assets/infrastructure/test_revenue_curves.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/assets/infrastructure/test_revenue_curves.py
from asset_finance_modeler.assets.infrastructure.schema import ArbitrageStream


def test_arbitrage_stream_accepts_curve_fields():
    s = ArbitrageStream(avg_spread_eur_mwh=82, spread_curve_name="spread_da_es")
    assert s.spread_curve_name == "spread_da_es"
    s2 = ArbitrageStream(avg_spread_eur_mwh=82)
    assert s2.spread_curve_name is None       # backward compatible default
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src .venv/bin/pytest tests/assets/infrastructure/test_revenue_curves.py -v`
Expected: FAIL — `ValidationError: unexpected keyword 'spread_curve_name'` (or AttributeError).

- [ ] **Step 3a: Extend the schema**

```python
# In schema.py, ArbitrageStream — add fields:
class ArbitrageStream(BaseModel):
    type: Literal["arbitrage"] = "arbitrage"
    name: str = "Arbitrage"
    avg_spread_eur_mwh: float = 40
    cycles_per_day: float = 1.5
    spread_capture_ratio: float = 0.75
    spread_curve_name: str | None = None          # library curve (overrides avg_spread)
    spread_points: list[float] | None = None       # explicit per-year spread

# In schema.py, AncillaryStream — add field:
class AncillaryStream(BaseModel):
    type: Literal["ancillary"] = "ancillary"
    name: str = "Ancillary Services"
    fcr_eur_mw_yr: float = 0
    afrr_eur_mw_yr: float = 0
    mfrr_eur_mw_yr: float = 0
    curve_points: list[float] | None = None        # per-year multiplier on base ancillary (1.0 = flat)
```

- [ ] **Step 3b: Use the curve in revenue.py**

In `_arbitrage(cfg, production_output, capacity_mw, periods, ppy)`, resolve a per-period spread before the loop and use it instead of the scalar:

```python
# at top of _arbitrage, after reading cfg:
from asset_finance_modeler.core.curves import Curve  # module-level import preferred

if cfg.spread_curve_name:
    spread_series = Curve.from_library(cfg.spread_curve_name).to_list(_years(periods, ppy))
elif cfg.spread_points:
    spread_series = Curve.from_points(cfg.spread_points).to_list(_years(periods, ppy))
else:
    spread_series = None  # fall back to cfg.avg_spread_eur_mwh

# inside the per-period loop, the spread for period t (year y = t // ppy):
spread_t = cfg.avg_spread_eur_mwh if spread_series is None else spread_series[t // ppy]
# ...use spread_t where avg_spread_eur_mwh was used...
```

(`_years(periods, ppy)` = `(periods + ppy - 1) // ppy`. If a local year helper already exists in revenue.py, reuse it.)
For `_ancillary`, if `cfg.curve_points` is set, multiply the base ancillary €/MW of year y by `Curve.from_points(cfg.curve_points).at(y)`.

- [ ] **Step 4: Add behavioral test + run**

```python
# Append to tests/assets/infrastructure/test_revenue_curves.py
from asset_finance_modeler.assets.infrastructure.engines.revenue import _arbitrage
from asset_finance_modeler.assets.infrastructure.schema import ArbitrageStream


def test_arbitrage_curve_changes_revenue_vs_flat():
    flat = ArbitrageStream(avg_spread_eur_mwh=82, cycles_per_day=0.9, spread_capture_ratio=0.8)
    curved = ArbitrageStream(avg_spread_eur_mwh=82, cycles_per_day=0.9,
                             spread_capture_ratio=0.8, spread_curve_name="spread_da_es")
    rev_flat = _arbitrage(flat, output=14.1, capacity_mw=4.7, periods=30, ppy=1)
    rev_curved = _arbitrage(curved, output=14.1, capacity_mw=4.7, periods=30, ppy=1)
    assert rev_flat[0] == rev_flat[29]                     # flat: constant
    assert rev_curved[6] > rev_curved[0]                   # curve grows then decays
    assert rev_curved[29] != rev_curved[0]
```

(Adjust the `_arbitrage` call signature/keywords to match the real one observed in revenue.py — confirm arg names with `grep -n "def _arbitrage" -A4 src/asset_finance_modeler/assets/infrastructure/engines/revenue.py` before writing the test.)

Run: `PYTHONPATH=src .venv/bin/pytest tests/assets/infrastructure/test_revenue_curves.py -v`
Expected: PASS.

- [ ] **Step 5: Run full suite + lint, then commit**

Run: `PYTHONPATH=src .venv/bin/pytest -q && .venv/bin/ruff check src/ tests/ && .venv/bin/mypy src/`
Expected: all green, ≥193 prior tests still pass.

```bash
git add src/asset_finance_modeler/assets/infrastructure/schema.py src/asset_finance_modeler/assets/infrastructure/engines/revenue.py tests/assets/infrastructure/test_revenue_curves.py
git commit -m "feat(infra): arbitrage/ancillary aceptan curvas (librería o puntos)"
```

---

## Task 5: Sembrar la librería (ancillary ES + captura solar ES)

**Files:**
- Create: `src/asset_finance_modeler/data/curves/ancillary_afrr_es.yaml`
- Create: `src/asset_finance_modeler/data/curves/solar_capture_es.yaml`
- Test: `tests/core/test_curve_library.py` (añadir)

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/core/test_curve_library.py
def test_seed_curves_present():
    names = list_curves()
    for n in ("spread_da_es", "ancillary_afrr_es", "solar_capture_es"):
        assert n in names
    anc = load_curve("ancillary_afrr_es")
    assert anc.to_list(10)[2] < anc.to_list(10)[0]   # comprime tras yr1 (Agere)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src .venv/bin/pytest tests/core/test_curve_library.py::test_seed_curves_present -v`
Expected: FAIL — assertion (curvas no existen).

- [ ] **Step 3: Create the YAMLs**

```yaml
# src/asset_finance_modeler/data/curves/ancillary_afrr_es.yaml
name: ancillary_afrr_es
asset_type: bess
parameter: ancillary_eur_mw_yr
source: "Agere: aFRR/mFRR España, canibalización 2028-29; base €74k/MW yr1 comprime a suelo ~€21k"
bankable: true
build: points
points: [74000, 65000, 60000, 55000, 48000, 42000, 36000, 31000, 27000, 24000, 22000, 21000, 21000, 21000, 21000, 21000, 21000, 21000, 21000, 21000, 21000, 21000, 21000, 21000, 21000, 21000, 21000, 21000, 21000, 21000]
```

```yaml
# src/asset_finance_modeler/data/curves/solar_capture_es.yaml
name: solar_capture_es
asset_type: solar_pv
parameter: capture_price_eur_mwh
source: "Agere captura solar España ~€36/MWh 2025, apuntamiento creciente decae a ~€29; conservadora"
bankable: true
build: phases
base: 36.0
periods: 30
phases:
  - {years: 10, growth_pct: -0.01}
  - {years: 20, growth_pct: -0.005}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src .venv/bin/pytest tests/core/test_curve_library.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/asset_finance_modeler/data/curves/ancillary_afrr_es.yaml src/asset_finance_modeler/data/curves/solar_capture_es.yaml tests/core/test_curve_library.py
git commit -m "feat(data): curvas seed ancillary_afrr_es + solar_capture_es (citadas)"
```

---

## Self-Review

- **Spec coverage (E2):** ✅ objeto `Curve` (Task 2), fuentes from_points/from_phases/from_growth/from_library (Tasks 1-3), librería bancable citada (Tasks 3+5), cableado en streams (Task 4). Fuentes dinámicas (búsqueda agente/custom usuario) = interfaz `from_points`/`from_library` lista; ejecución del wizard es Torre (fuera de fase).
- **Placeholders:** ninguno — todo el código está escrito.
- **Type consistency:** `Curve`, `CurvePhase`, `build_phased_curve`, `load_curve`, `list_curves`, `spread_curve_name`/`spread_points`/`curve_points` coherentes entre tasks.
- **Nota de verificación previa al código:** confirmar la firma real de `_arbitrage`/`_ancillary` (`grep -n "def _arbitrage" -A6 revenue.py`) antes de escribir el test de Task 4, y ajustar nombres de args si difieren.

## Notas para fases siguientes (NO implementar aquí)
- Fase 2 (E3 deuda multi-tramo + waterfall), Fase 3 (E4 eventos capex/repowering), Fase 4 (E5 outputs valoración), Fase 5 (E1 híbrido acoplado), Fase 6 (modelo hybrid consolidated + validación), Fase 7 (Excel-foto). Cada una tendrá su propio plan.
