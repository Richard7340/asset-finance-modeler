# Motor financiero — Fase 3: Eventos de capex / repowering (E4) — Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Permitir eventos de capex en mitad de la vida del activo (repowering, augmentation, overhaul): inyectar un coste en el año N y, opcionalmente, **resetear la degradación** (la capacidad vuelve a ~100% y vuelve a degradar). General para cualquier activo. En SVJ: repowering del BESS en yr15 → vida 30 años.

**Architecture:** Dos funciones puras en `core/capex_events.py` (`apply_capex_events` añade importes al spend en su periodo; `apply_degradation_resets` reinicia la curva de degradación en los periodos de reset). Un schema `CapexEvent` + campo `capex_events` (opcional, default []) en el config del activo. El modelo añade los eventos al `capex_spend` y aplica los resets a la curva de degradación. Reutiliza `core/degradation.py` y `engines/capex.py`. Backward compatible (lista vacía = comportamiento actual).

**Tech Stack:** Python 3.12, Pydantic v2, pytest, ruff PL, mypy strict.

**Repo/rama:** `/Users/rikyizquierdo/Documents/New project/asset-finance-modeler`, rama `feat/finance-engine-general-deals`.

**VERIFICAR ANTES DE CODIFICAR:** estructura real de `InfrastructureModelConfig` (tiene `capex: CAPEXBreakdown`, `opex`, `degradation: DegradationCurve`); cómo `engines/capex.py::compute_capex` produce `capex_spend` (hoy `[total_capex]+[0]*(n-1)`); cómo el modelo (`model.py`) obtiene la curva de degradación (qué función de `core/degradation.py` llama y dónde la multiplica por la producción). Solo correr `tests/core tests/unit tests/golden`.

---

## Task 1: Funciones puras `apply_capex_events` + `apply_degradation_resets`

**Files:**
- Create: `src/asset_finance_modeler/core/capex_events.py`
- Test: `tests/core/test_capex_events.py`

- [ ] **Step 1 — Failing test:**
```python
from asset_finance_modeler.core.capex_events import (
    apply_capex_events,
    apply_degradation_resets,
)


def test_apply_capex_events_adds_amount_at_period():
    spend = [1000.0] + [0.0] * 29     # capex año 0
    # evento: 200 en año 15 (ppy=1 -> periodo 15)
    out = apply_capex_events(spend, events=[(15, 200.0)], periods_per_year=1)
    assert out[0] == 1000.0
    assert out[15] == 200.0
    assert sum(out) == 1200.0
    assert spend[15] == 0.0           # no muta el input


def test_apply_capex_events_monthly_ppy():
    spend = [0.0] * 360               # 30 años mensual
    out = apply_capex_events(spend, events=[(15, 500.0)], periods_per_year=12)
    assert out[180] == 500.0          # año 15 -> periodo 180


def test_apply_degradation_resets_restores_capacity():
    # curva base que decae linealmente: 1.0, 0.9, 0.8, ... (sin reset)
    base = [1.0 - 0.02 * t for t in range(30)]
    out = apply_degradation_resets(base, reset_periods=[15])
    assert out[14] == base[14]        # antes del reset, igual
    assert out[15] == base[0]         # en el reset vuelve a 1.0 (base[0])
    assert out[16] == base[1]         # y re-degrada desde ahí
    assert out[29] == base[29 - 15]
    assert base[15] == 1.0 - 0.30     # no muta el input


def test_apply_degradation_resets_empty_is_identity():
    base = [1.0, 0.9, 0.8]
    assert apply_degradation_resets(base, reset_periods=[]) == base
```

- [ ] **Step 2 — Run, verify FAIL** (ModuleNotFoundError capex_events):
`PYTHONPATH=src .venv/bin/pytest tests/core/test_capex_events.py -v`

- [ ] **Step 3 — Implement** (`src/asset_finance_modeler/core/capex_events.py`):
```python
from __future__ import annotations


def apply_capex_events(
    capex_spend: list[float],
    events: list[tuple[int, float]],
    periods_per_year: int,
) -> list[float]:
    """Return a copy of capex_spend with each event's amount added at its
    period. Each event is (year, amount); period = year * periods_per_year.
    Events whose period falls outside the horizon are ignored."""
    out = list(capex_spend)
    n = len(out)
    for year, amount in events:
        t = year * periods_per_year
        if 0 <= t < n:
            out[t] += amount
    return out


def apply_degradation_resets(
    base_curve: list[float],
    reset_periods: list[int],
) -> list[float]:
    """Return a copy of base_curve where, at each reset period r, capacity
    returns to base_curve[0] and follows the same degradation shape again:
    for t >= r (until the next reset), multiplier = base_curve[t - r].
    """
    out = list(base_curve)
    n = len(base_curve)
    for r in sorted(reset_periods):
        if r < 0 or r >= n:
            continue
        for t in range(r, n):
            offset = t - r
            out[t] = base_curve[offset] if offset < n else base_curve[-1]
    return out
```

- [ ] **Step 4 — Run, verify PASS** (4 passed). `tests/core -q` green. ruff+mypy clean.

- [ ] **Step 5 — Commit:**
```bash
git add src/asset_finance_modeler/core/capex_events.py tests/core/test_capex_events.py
git commit -m "feat(core): apply_capex_events + apply_degradation_resets (eventos capex/repowering)"
```

---

## Task 2: `CapexEvent` schema + campo `capex_events`

**Files:**
- Modify: `src/asset_finance_modeler/assets/infrastructure/schema.py`
- Test: `tests/unit/test_capex_events_schema.py`

**VERIFY FIRST:** read `InfrastructureModelConfig` (the top config with `capex/opex/degradation` fields) and `InfraCapexItem`/`CAPEXBreakdown`. Decide where `capex_events` belongs — put it on the TOP config (`InfrastructureModelConfig`) since events affect both capex spend AND degradation (cross-cutting), unless the existing structure clearly suggests otherwise (report your choice).

- [ ] **Step 1 — Failing test:**
```python
from asset_finance_modeler.assets.infrastructure.schema import CapexEvent


def test_capex_event_defaults():
    e = CapexEvent(year=15, amount=200.0)
    assert e.year == 15
    assert e.amount == 200.0
    assert e.resets_degradation is False
    e2 = CapexEvent(year=15, amount=200.0, resets_degradation=True, label="repowering BESS")
    assert e2.resets_degradation is True
```

- [ ] **Step 2 — Run, verify FAIL** (ImportError CapexEvent).

- [ ] **Step 3 — Implement** (in schema.py):
```python
class CapexEvent(BaseModel):
    year: int                         # year of the event (0-based model year)
    amount: float                     # capex injection, same units as CAPEX
    resets_degradation: bool = False  # if True, capacity returns to nameplate
    label: str = ""
```
Add to the top config: `capex_events: list[CapexEvent] = Field(default_factory=list)`.

- [ ] **Step 4 — Run, verify PASS.** Presets still load (`solar_pv_50mw_spain`, `bess_20mw_4h`). ruff+mypy clean.

- [ ] **Step 5 — Commit:**
```bash
git add src/asset_finance_modeler/assets/infrastructure/schema.py tests/unit/test_capex_events_schema.py
git commit -m "feat(infra): CapexEvent + campo capex_events en el config"
```

---

## Task 3: Modelo aplica eventos al capex y resets a la degradación

**Files:**
- Modify: `src/asset_finance_modeler/assets/infrastructure/model.py`
- Test: `tests/unit/test_capex_events_model.py`

**VERIFY FIRST:** in `model.py` find (a) where `capex_spend` from `compute_capex` is used (to add events to it), and (b) where the degradation multiplier curve is obtained and multiplied into production. Apply `apply_capex_events(capex_spend, [(e.year, e.amount) for e in cfg.capex_events], ppy)` and, for degradation, compute `reset_periods = [e.year*ppy for e in cfg.capex_events if e.resets_degradation]` and wrap the base curve with `apply_degradation_resets(base_curve, reset_periods)`.

- [ ] **Step 1 — Failing behavioral test:** a BESS with a repowering event (resets_degradation) in year 15 produces MORE in year 16 than the same model without the event (capacity restored), and total capex is higher (the injection):
```python
from asset_finance_modeler.assets.infrastructure.loader import load_preset
from asset_finance_modeler.assets.infrastructure.schema import CapexEvent
from asset_finance_modeler.assets.infrastructure.model import InfrastructureModel


def test_repowering_event_restores_capacity_and_adds_capex():
    base_cfg = load_preset("bess_20mw_4h")
    base_out = InfrastructureModel(base_cfg).run()

    rep_cfg = load_preset("bess_20mw_4h")
    rep_cfg.capex_events = [CapexEvent(year=15, amount=5000.0, resets_degradation=True, label="repowering")]
    rep_out = InfrastructureModel(rep_cfg).run()

    # total capex higher by the injection
    assert rep_out.capex_summary.total_capex > base_out.capex_summary.total_capex
    # production/revenue in a post-repowering year exceeds the degraded base case
    # (adapt attribute: compare a late-year revenue or production series value)
    assert _late_year_revenue(rep_out) > _late_year_revenue(base_out)
```
Adapt `capex_summary.total_capex` and `_late_year_revenue(...)` to the REAL output structure you confirmed (e.g. a revenue/production list on the output, compared at period ~20*ppy). The assertion must genuinely show (a) capex up by the injection and (b) higher post-reset output. If the preset has no degradation configured (flat 1.0), temporarily set a degradation on the cfg so the reset is observable, and note it.

- [ ] **Step 2 — Run, verify FAIL** (event has no effect yet).

- [ ] **Step 3 — Implement** the wiring described in VERIFY FIRST.

- [ ] **Step 4 — Run, verify PASS.** Full regression `tests/core tests/unit tests/golden -q` (no regression). ruff+mypy clean (ignore the known pre-existing financing.py:99 + model.py baseline mypy items; introduce none new).

- [ ] **Step 5 — Commit:**
```bash
git add src/asset_finance_modeler/assets/infrastructure/model.py tests/unit/test_capex_events_model.py
git commit -m "feat(infra): modelo aplica eventos de capex + reset de degradacion (repowering)"
```

---

## Self-Review
- **Spec coverage (E4):** eventos capex en año N (Task 1+2+3), reset de degradación (Task 1+3), integración modelo (Task 3). ✅
- **Placeholders:** ninguno; funciones puras codificadas; wiring con verify-first.
- **Type consistency:** `apply_capex_events`, `apply_degradation_resets`, `CapexEvent(year, amount, resets_degradation, label)`, `capex_events` coherentes.
- **Backward compat:** `capex_events` default vacío → comportamiento idéntico al actual; sin reset = curva base intacta.

## Fases siguientes: F4 E5 outputs valoración (NPV equity@Ke, MOIC, recovery) · F5 E1 híbrido acoplado · F6 SVJ+validación · F7 Excel-foto.
