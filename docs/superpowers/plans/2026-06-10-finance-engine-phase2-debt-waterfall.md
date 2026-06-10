# Motor financiero — Fase 2: Deuda multi-tramo + waterfall (E3) — Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Permitir estructuras de capital con varios tramos ordenados por prelación (senior + subordinado) y calcular el **DSCR por tramo en cascada** (el subordinado neto del servicio de deuda senior). Base para deals como SVJ (senior FV + subordinada inversor, DSCR sub 1,14-1,31×).

**Architecture:** Función pura `compute_waterfall_dscr` en `core/financing.py` (cfads + lista ordenada de series de debt-service por tramo → DSCR por tramo). Nuevo `SubordinatedDebtConfig` + campo en `FinancingConfig`. El modelo `_compute_debt` construye los dos tramos (el subordinado se dimensiona sobre el CFADS neto del senior) y expone `dscr_senior_*`/`dscr_subordinated_*` en los KPIs. Reutiliza `DebtEngine`/`AmortizationSchedule`/`size_debt` existentes. Backward compatible (subordinado opcional, default None).

**Tech Stack:** Python 3.12, Pydantic v2, pytest, ruff PL, mypy strict.

**Repo/rama:** `/Users/rikyizquierdo/Documents/New project/asset-finance-modeler`, rama `feat/finance-engine-general-deals`.

**VERIFICAR ANTES DE CODIFICAR (cada task):** firmas reales de `compute_debt_metrics`, `FinancingConfig` (campos: tiene `senior`, `max_leverage`, ¿`mezzanine`?), `SeniorDebtConfig`, `ProjectKPIs`/`FinancialOutput` (cómo se añaden campos KPI), y `_compute_debt`/`_compute_kpis`. Adaptar a la realidad observada (como en Fase 1 Task 4). Solo correr `tests/core`, `tests/unit`, `tests/golden` (NO el dir `tests/` completo — cuelga con torch/embeddings sin red).

---

## Task 1: `compute_waterfall_dscr` (función pura)

**Files:**
- Modify: `src/asset_finance_modeler/core/financing.py` (añadir función al final)
- Test: `tests/core/test_waterfall_dscr.py` (create)

- [ ] **Step 1 — Failing test:**
```python
from asset_finance_modeler.core.financing import compute_waterfall_dscr


def test_waterfall_two_tranches():
    cfads = [200.0, 200.0]
    senior_ds = [100.0, 100.0]
    sub_ds = [50.0, 50.0]
    senior_dscr, sub_dscr = compute_waterfall_dscr(cfads, [senior_ds, sub_ds])
    assert senior_dscr == [2.0, 2.0]                 # 200/100
    assert sub_dscr == [2.0, 2.0]                    # (200-100)/50


def test_waterfall_sub_is_thinner_than_senior():
    # subordinado ve menos caja (neto del senior) -> DSCR menor
    cfads = [150.0]
    s, sub = compute_waterfall_dscr([cfads[0]], [[100.0], [40.0]])
    assert s == [1.5]
    assert sub == [1.25]                              # (150-100)/40


def test_waterfall_zero_service_is_inf_and_negative_avail_is_zero():
    s, sub = compute_waterfall_dscr([90.0], [[100.0], [0.0]])
    assert sub == [float("inf")]                      # sub no tiene servicio ese periodo
    assert s == [0.9]
    s2, sub2 = compute_waterfall_dscr([90.0], [[100.0], [50.0]])
    assert sub2 == [0.0]                              # avail = 90-100 < 0 -> 0
```

- [ ] **Step 2 — Run, verify FAIL** (ImportError compute_waterfall_dscr):
`PYTHONPATH=src .venv/bin/pytest tests/core/test_waterfall_dscr.py -v`

- [ ] **Step 3 — Implement** (append to `core/financing.py`):
```python
def compute_waterfall_dscr(
    cfads: list[float],
    tranche_debt_service: list[list[float]],
) -> list[list[float]]:
    """Per-tranche DSCR in seniority order (most senior first).

    Each tranche's DSCR uses CFADS net of ALL more-senior tranches' debt
    service: DSCR_k[t] = (cfads[t] - sum(ds_j[t] for j<k)) / ds_k[t].
    Zero service -> inf (no obligation that period); non-positive available
    cash with positive service -> 0.0.
    """
    n = len(cfads)
    results: list[list[float]] = []
    for idx, ds in enumerate(tranche_debt_service):
        dscr: list[float] = []
        for t in range(n):
            senior_ds = sum(tranche_debt_service[j][t] for j in range(idx))
            available = cfads[t] - senior_ds
            service = ds[t]
            if service <= 0:
                dscr.append(float("inf"))
            elif available <= 0:
                dscr.append(0.0)
            else:
                dscr.append(available / service)
        results.append(dscr)
    return results
```

- [ ] **Step 4 — Run, verify PASS** (3 passed). `tests/core -q` green. ruff+mypy clean on financing.py.

- [ ] **Step 5 — Commit:**
```bash
git add src/asset_finance_modeler/core/financing.py tests/core/test_waterfall_dscr.py
git commit -m "feat(core): compute_waterfall_dscr (DSCR por tramo en cascada)"
```

---

## Task 2: `SubordinatedDebtConfig` + campo en `FinancingConfig`

**Files:**
- Modify: `src/asset_finance_modeler/assets/infrastructure/schema.py`
- Test: `tests/unit/test_financing_subordinated.py` (create; if `tests/unit` is the real infra test dir — confirm with `find tests -name 'test_infra_schema.py'`)

**VERIFY FIRST:** read the real `SeniorDebtConfig` and `FinancingConfig` bodies (around line 300-340 of schema.py). `SeniorDebtConfig` fields are: `tenor_years, interest_rate, grace_period_months, amortization (Literal french/bullet/linear), dscr_target, dscr_mode (Literal min/avg), auto_size`. There is also a `MezzanineDebtConfig` — read it; if it already fits "subordinated" semantics you MAY reuse/extend it instead of creating a new class (report which you chose). `FinancingConfig` has `senior: SeniorDebtConfig | None` and `max_leverage`.

- [ ] **Step 1 — Failing test:**
```python
from asset_finance_modeler.assets.infrastructure.schema import FinancingConfig, SubordinatedDebtConfig


def test_financing_accepts_subordinated_optional():
    f = FinancingConfig()
    assert f.subordinated is None                       # backward compatible
    sub = SubordinatedDebtConfig(principal=1841.0, interest_rate=0.085, tenor_years=7)
    f2 = FinancingConfig(subordinated=sub)
    assert f2.subordinated.interest_rate == 0.085
    assert f2.subordinated.amortization == "french"     # sensible default
```

- [ ] **Step 2 — Run, verify FAIL** (ImportError SubordinatedDebtConfig).

- [ ] **Step 3 — Implement** (in schema.py, near SeniorDebtConfig):
```python
class SubordinatedDebtConfig(BaseModel):
    principal: float                                    # fixed ticket (e.g. investor)
    interest_rate: float = 0.085
    tenor_years: int = 7
    grace_period_months: int = 0
    amortization: Literal["french", "bullet", "linear"] = "french"
    drawdown_period: int = 0
```
Add to `FinancingConfig`: `subordinated: SubordinatedDebtConfig | None = None`.

- [ ] **Step 4 — Run, verify PASS.** Confirm existing presets still load: `PYTHONPATH=src .venv/bin/python -c "from asset_finance_modeler.assets.infrastructure.loader import load_preset; [load_preset(p) for p in ['solar_pv_50mw_spain','bess_20mw_4h']]; print('presets OK')"`. ruff+mypy clean.

- [ ] **Step 5 — Commit:**
```bash
git add src/asset_finance_modeler/assets/infrastructure/schema.py tests/unit/test_financing_subordinated.py
git commit -m "feat(infra): SubordinatedDebtConfig + campo subordinated en FinancingConfig"
```

---

## Task 3: Modelo construye ambos tramos + expone DSCR por tramo

**Files:**
- Modify: `src/asset_finance_modeler/assets/infrastructure/model.py` (`_compute_debt` + `_compute_kpis`)
- Modify: `src/asset_finance_modeler/core/protocols.py` (o donde viva `ProjectKPIs`) para añadir campos DSCR por tramo
- Test: `tests/unit/test_subordinated_dscr_model.py` (create)

**VERIFY FIRST:** read `ProjectKPIs`/`FinancialOutput` definition (find with `grep -rn "class ProjectKPIs\|dscr_min" src`) to see how to add `dscr_senior_min/avg` and `dscr_subordinated_min/avg` fields (give them safe defaults so existing construction sites don't break). Read how `_compute_debt` returns and how `_compute_kpis` consumes `debt_metrics`.

- [ ] **Step 1 — Failing test** (behavioral): build a config with senior auto-sized + a fixed subordinated tranche, run the model, assert the subordinated DSCR is computed, is finite/positive in early years, and is LOWER than the senior DSCR (subordinate sees cash net of senior):
```python
from asset_finance_modeler.assets.infrastructure.loader import load_preset
from asset_finance_modeler.assets.infrastructure.schema import SubordinatedDebtConfig
from asset_finance_modeler.assets.infrastructure.model import InfrastructureModel


def test_model_exposes_subordinated_dscr_below_senior():
    cfg = load_preset("bess_20mw_4h")
    cfg.financing.subordinated = SubordinatedDebtConfig(
        principal=2000.0, interest_rate=0.085, tenor_years=7, amortization="french"
    )
    out = InfrastructureModel(cfg).run()
    k = out.project_kpis
    assert k.dscr_subordinated_min > 0
    assert k.dscr_subordinated_min < k.dscr_senior_min   # waterfall: sub thinner
```
(Adapt attribute access — `out.project_kpis.dscr_*` — to the real KPI object path you confirmed. Pick a `principal` that is feasible for the preset's cash flows; if 2000 makes sub DSCR 0, choose a smaller principal so the assertion is meaningful, and note it.)

- [ ] **Step 2 — Run, verify FAIL** (AttributeError dscr_subordinated_min, or field missing).

- [ ] **Step 3 — Implement:**
  1. Add KPI fields `dscr_senior_min/avg` and `dscr_subordinated_min/avg` (defaults 0.0 or inf) to the KPIs dataclass.
  2. In `_compute_debt`: after senior, if `cfg.financing.subordinated` is set, build its `DebtInstrument` and schedule. Compute each tranche's per-period total debt-service series (use `AmortizationSchedule(...).rows()` → `total_payment`). Return/stash both series (extend the return or compute DSCR here).
  3. Compute `senior_dscr, sub_dscr = compute_waterfall_dscr(cfads, [senior_ds, sub_ds])` (cfads = the same EBITDA/CFADS used today). Reduce to min/avg over each tranche's tenor (exclude inf), mirroring the existing `dscr_min/avg` logic. Populate the new KPI fields. Keep the existing aggregate `dscr_*` untouched for backward compatibility.

- [ ] **Step 4 — Run, verify PASS.** Full regression: `PYTHONPATH=src .venv/bin/pytest tests/core tests/unit tests/golden -q` (all green, no regression). ruff+mypy clean.

- [ ] **Step 5 — Commit:**
```bash
git add src/asset_finance_modeler/assets/infrastructure/model.py src/asset_finance_modeler/core/protocols.py tests/unit/test_subordinated_dscr_model.py
git commit -m "feat(infra): modelo construye tramo subordinado + DSCR por tramo (waterfall)"
```

---

## Self-Review
- **Spec coverage (E3):** multi-tramo (Task 2), waterfall DSCR neto del senior (Task 1), integración en modelo + KPIs por tramo (Task 3). ✅
- **Placeholders:** ninguno; función pura totalmente codificada. Wiring de Task 3 describe pasos concretos + verify-first (igual que Fase 1 Task 4, que funcionó).
- **Type consistency:** `compute_waterfall_dscr`, `SubordinatedDebtConfig`, `FinancingConfig.subordinated`, `dscr_senior_min/avg`, `dscr_subordinated_min/avg` coherentes entre tasks.
- **Backward compat:** subordinado opcional (None); KPIs nuevos con defaults; agregado existente intacto.

## Fases siguientes (no aquí): F3 E4 capex/repowering · F4 E5 outputs valoración (NPV equity@Ke, MOIC, recovery) · F5 E1 híbrido acoplado · F6 modelo SVJ+validación · F7 Excel-foto.
