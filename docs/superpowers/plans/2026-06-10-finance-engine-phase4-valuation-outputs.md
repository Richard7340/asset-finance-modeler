# Motor financiero — Fase 4: Outputs de valoración (E5) — Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Exponer en los KPIs, de forma limpia y etiquetada: **NPV de equity a Ke** (coste de equity, distinto del WACC de proyecto), **MOIC** del prestamista subordinado (cash recibido / principal) y **recovery going-concern** (PV de la caja futura / principal pendiente — el colateral). El NPV de proyecto@WACC, IRR proyecto/equity y DSCR por tramo YA existen. General para cualquier deal.

**Architecture:** Dos funciones puras en `core/valuation.py` (`compute_moic`, `compute_recovery_multiple`). Un campo `cost_of_equity_annual` en el config de valoración (default = `discount_rate_annual`). En `_compute_kpis`: `npv_equity = compute_dcf(equity_cf, Ke)`; `moic_subordinated`/`recovery_going_concern` cuando hay tramo subordinado. Reutiliza `compute_dcf`/`compute_irr` existentes y `equity_cf`/`sub_ds` ya construidos. Backward compatible (campos KPI nuevos con defaults).

**Tech Stack:** Python 3.12, Pydantic v2, pytest, ruff PL, mypy strict.

**Repo/rama:** `/Users/rikyizquierdo/Documents/New project/asset-finance-modeler`, rama `feat/finance-engine-general-deals`.

**VERIFICAR ANTES:** firma de `compute_dcf` en `core/valuation.py` (es `compute_dcf(cashflows, wacc_annual, periods_per_year, terminal_growth=..., terminal_method=...)` — confirmar args y si terminal value se puede desactivar/poner a 0 para una valoración simple de la serie de equity). El config de valoración (`cfg.valuation`, con `discount_rate_annual`; confirmar el nombre real de la clase y añadir `cost_of_equity_annual`). `ProjectKPIs` en `core/protocols.py` (añadir campos con defaults). Cómo se construye `equity_cf` y `sub_ds` en `_compute_kpis` (ya existen). Solo correr `tests/core tests/unit tests/golden`.

---

## Task 1: Funciones puras `compute_moic` + `compute_recovery_multiple`

**Files:**
- Modify: `src/asset_finance_modeler/core/valuation.py` (añadir 2 funciones)
- Test: `tests/core/test_valuation_outputs.py`

- [ ] **Step 1 — Failing test:**
```python
from asset_finance_modeler.core.valuation import compute_moic, compute_recovery_multiple


def test_moic_basic():
    # presta 1000, recibe 7 cuotas de 200 = 1400 -> MOIC 1.4
    assert abs(compute_moic([200.0] * 7, 1000.0) - 1.4) < 1e-9


def test_moic_zero_principal():
    assert compute_moic([100.0], 0.0) == 0.0


def test_recovery_multiple_pv_over_principal():
    # CFADS 100/año durante 5 años a partir del periodo 5; tasa 0% -> PV=500; principal 250 -> 2.0
    cfads = [0.0] * 5 + [100.0] * 5
    rec = compute_recovery_multiple(cfads, from_period=5, discount_rate_annual=0.0,
                                    periods_per_year=1, outstanding_principal=250.0)
    assert abs(rec - 2.0) < 1e-9


def test_recovery_discounted_and_zero_principal():
    cfads = [100.0, 100.0]
    rec = compute_recovery_multiple(cfads, 0, 0.10, 1, 100.0)
    # PV = 100 + 100/1.1 = 190.909... -> /100
    assert abs(rec - (100 + 100 / 1.1) / 100) < 1e-6
    assert compute_recovery_multiple([100.0], 0, 0.0, 1, 0.0) == float("inf")
```

- [ ] **Step 2 — Run, verify FAIL** (ImportError):
`PYTHONPATH=src .venv/bin/pytest tests/core/test_valuation_outputs.py -v`

- [ ] **Step 3 — Implement** (append to `core/valuation.py`):
```python
def compute_moic(debt_service: list[float], principal: float) -> float:
    """Money-on-invested-capital for a lender: total cash received / principal."""
    if principal <= 0:
        return 0.0
    return sum(debt_service) / principal


def compute_recovery_multiple(
    cfads: list[float],
    from_period: int,
    discount_rate_annual: float,
    periods_per_year: int,
    outstanding_principal: float,
) -> float:
    """Going-concern recovery: PV of CFADS from `from_period` onwards
    (discounted to from_period) divided by outstanding principal. Represents
    how much a lender could recover by operating the asset from that point."""
    if outstanding_principal <= 0:
        return float("inf")
    period_rate = (1.0 + discount_rate_annual) ** (1.0 / periods_per_year) - 1.0
    pv = 0.0
    for i, t in enumerate(range(from_period, len(cfads))):
        pv += cfads[t] / (1.0 + period_rate) ** i
    return pv / outstanding_principal
```

- [ ] **Step 4 — Run, verify PASS** (4 passed). `tests/core -q` green. ruff+mypy clean.

- [ ] **Step 5 — Commit:**
```bash
git add src/asset_finance_modeler/core/valuation.py tests/core/test_valuation_outputs.py
git commit -m "feat(core): compute_moic + compute_recovery_multiple"
```

---

## Task 2: `cost_of_equity_annual` + `npv_equity` KPI

**Files:**
- Modify: `src/asset_finance_modeler/assets/infrastructure/schema.py` (valuation config)
- Modify: `src/asset_finance_modeler/core/protocols.py` (`ProjectKPIs`: add `npv_equity`)
- Modify: `src/asset_finance_modeler/assets/infrastructure/model.py` (`_compute_kpis`)
- Test: `tests/unit/test_npv_equity.py`

**VERIFY FIRST:** the valuation config class + that it has `discount_rate_annual`. Add `cost_of_equity_annual: float | None = None` (None → fall back to `discount_rate_annual` at compute time). Confirm `compute_dcf` signature; to value the equity series without an asset terminal value, call it the same way `npv` (project) is currently computed but with the equity series and Ke, OR if `compute_dcf` forces a terminal value that distorts a levered equity series, compute a plain discounted sum (reuse the period-rate pattern) — pick the approach that matches how project `npv` is already produced and is correct for a levered equity cashflow; note your choice.

- [ ] **Step 1 — Failing test:**
```python
from asset_finance_modeler.assets.infrastructure.loader import load_preset
from asset_finance_modeler.assets.infrastructure.model import InfrastructureModel


def test_npv_equity_present_and_ke_lower_than_wacc_reduces_it():
    cfg = load_preset("solar_pv_50mw_spain")
    out = InfrastructureModel(cfg).run()
    assert hasattr(out.project_kpis, "npv_equity")
    # con un Ke MAYOR que el WACC, el NPV de equity baja
    cfg2 = load_preset("solar_pv_50mw_spain")
    cfg2.valuation.cost_of_equity_annual = cfg2.valuation.discount_rate_annual + 0.03
    out2 = InfrastructureModel(cfg2).run()
    assert out2.project_kpis.npv_equity < out.project_kpis.npv_equity
```
(Adapt `out.project_kpis.npv_equity` and the valuation field path to reality. If solar preset has no debt, equity_cf == project_cf and npv_equity is still well-defined — fine.)

- [ ] **Step 2 — Run, verify FAIL** (AttributeError npv_equity / field missing).

- [ ] **Step 3 — Implement:** add `cost_of_equity_annual: float | None = None` to valuation config; add `npv_equity: float = 0.0` to `ProjectKPIs`; in `_compute_kpis` compute `ke = cfg.valuation.cost_of_equity_annual or cfg.valuation.discount_rate_annual` and `npv_equity` by discounting `equity_cf` at `ke` (mirroring how project `npv` is computed). Populate the field.

- [ ] **Step 4 — Run, verify PASS.** Regression `tests/core tests/unit tests/golden -q`. ruff+mypy clean (no new errors).

- [ ] **Step 5 — Commit:**
```bash
git add src/asset_finance_modeler/assets/infrastructure/schema.py src/asset_finance_modeler/core/protocols.py src/asset_finance_modeler/assets/infrastructure/model.py tests/unit/test_npv_equity.py
git commit -m "feat(infra): NPV de equity a Ke (cost_of_equity_annual)"
```

---

## Task 3: `moic_subordinated` + `recovery_going_concern` KPIs

**Files:**
- Modify: `src/asset_finance_modeler/core/protocols.py` (`ProjectKPIs`)
- Modify: `src/asset_finance_modeler/assets/infrastructure/model.py` (`_compute_kpis`)
- Test: `tests/unit/test_moic_recovery.py`

- [ ] **Step 1 — Failing test:**
```python
from asset_finance_modeler.assets.infrastructure.loader import load_preset
from asset_finance_modeler.assets.infrastructure.schema import SubordinatedDebtConfig
from asset_finance_modeler.assets.infrastructure.model import InfrastructureModel


def test_moic_and_recovery_for_subordinated():
    cfg = load_preset("bess_20mw_4h")
    cfg.financing.subordinated = SubordinatedDebtConfig(
        principal=4_000_000.0, interest_rate=0.085, tenor_years=7, amortization="french"
    )
    out = InfrastructureModel(cfg).run()
    k = out.project_kpis
    assert k.moic_subordinated > 1.0          # a french-amortized 8.5% loan repays > principal
    assert k.recovery_going_concern > 0.0     # asset has post-tenor cash backing the principal


def test_moic_recovery_zero_without_subordinated():
    out = InfrastructureModel(load_preset("bess_20mw_4h")).run()
    assert out.project_kpis.moic_subordinated == 0.0
    assert out.project_kpis.recovery_going_concern == 0.0
```
(Adapt attribute paths + the `principal` to a feasible value as in Phase 2 Task 3.)

- [ ] **Step 2 — Run, verify FAIL** (AttributeError).

- [ ] **Step 3 — Implement:** add `moic_subordinated: float = 0.0` and `recovery_going_concern: float = 0.0` to `ProjectKPIs`. In `_compute_kpis`, when `cfg.financing.subordinated` is set:
  - `moic_subordinated = compute_moic(sub_ds, cfg.financing.subordinated.principal)`.
  - `recovery_going_concern = compute_recovery_multiple(cfads, from_period=tenor_periods, discount_rate_annual=<a recovery rate: reuse Ke or discount_rate>, periods_per_year=ppy, outstanding_principal=cfg.financing.subordinated.principal)` where `tenor_periods = subordinated.tenor_years*ppy` (PV of CFADS AFTER the sub is repaid, vs principal — going-concern coverage). Document the recovery discount rate chosen.
  Leave both at 0.0 when no subordinated tranche.

- [ ] **Step 4 — Run, verify PASS.** Full regression green. ruff+mypy clean.

- [ ] **Step 5 — Commit:**
```bash
git add src/asset_finance_modeler/core/protocols.py src/asset_finance_modeler/assets/infrastructure/model.py tests/unit/test_moic_recovery.py
git commit -m "feat(infra): MOIC subordinado + recovery going-concern en KPIs"
```

---

## Self-Review
- **Spec coverage (E5):** NPV equity@Ke (Task 2), MOIC prestamista (Task 1+3), recovery going-concern (Task 1+3). NPV proyecto@WACC + IRR + DSCR por tramo ya existían. ✅
- **Placeholders:** ninguno; funciones puras codificadas; wiring con verify-first.
- **Type consistency:** `compute_moic`, `compute_recovery_multiple`, `cost_of_equity_annual`, `npv_equity`, `moic_subordinated`, `recovery_going_concern` coherentes.
- **Backward compat:** KPIs nuevos con defaults; Ke default = WACC; sin subordinado → MOIC/recovery 0.

## Fases siguientes: F5 E1 híbrido acoplado · F6 SVJ + validación · F7 Excel-foto.
