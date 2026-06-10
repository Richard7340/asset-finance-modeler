# Motor financiero — Fase 6: Modelo SVJ + validación (E1 acoplamiento + cierre) — Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Construir el deal real SVJ (FV + BESS híbrido) con el motor extendido y validarlo contra los KPIs ya validados en el Excel (tolerancia razonable, documentando reconciliaciones). Esto ejercita TODAS las extensiones (curvas, deuda multi-tramo, repowering, valoración, consolidación) en un caso real y cierra el back-end.

**Architecture:** Dos presets SVJ (`svj_fv_cordoba.yaml`, `svj_bess_cordoba.yaml`) con los inputs reales del deal. Extensión de `HybridProject` para **deuda consolidada**: tramo senior (FV) + subordinado (inversor) sobre el **CFADS consolidado** (EBITDA híbrido), reusando `compute_waterfall_dscr` (F2), `compute_moic`+`compute_recovery_multiple` (F4). Acoplamiento físico FV→BESS capturado calibrando `cycles_per_day` del BESS al excedente FV barato (~0,9 cycles/día → throughput ≈ 50% prod FV) y el spread neto (`spread_da_es` ya = venta−carga, carga ~0). Un test de validación que corre el SVJ y compara con los objetivos.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, ruff PL, mypy strict.

**Repo/rama:** `/Users/rikyizquierdo/Documents/New project/asset-finance-modeler`, rama `feat/finance-engine-general-deals`.

**INPUTS REALES DEL DEAL** (de `/Users/rikyizquierdo/Hybridisation/_aurora_sizing_engine.py` y `_aurora_deal_engine_v2.py`):
- BESS: 4,7 MW · 3h · 14,1 MWh · DoD 0,80 · RTE 0,85 · 330 ciclos/año (≈0,9/día) · CAPEX 130,6 €/kWh (€1.841k) · repowering yr15 60 €/kWh (€846k) · spread €82 curva `spread_da_es` · capture 0,80 · ancillary €74k/MW curva `ancillary_afrr_es` · carga FV ~€0.
- FV: 4,76 MWp · 7.530 MWh/año · yield ~1.582 · PR 0,86 · degr 0,6%/año · PPA €43 (vol a BESS ~0,5) + merchant captura solar ~€36 · CAPEX €4.44M (0,93 €/Wp) · senior 50% @3,2% 10a.
- Deuda inversor (subordinada): €1.841k · 8,5% · 7a francesa. WACC híbrido 5,37% · Ke FV 7,5% / BESS 8,5% · IS 25% (+ eléctrico 7%) · vida 30a.
- **OBJETIVOS (tolerancia ±5-10%, documentar gaps):** NPV híbrido +€1.644k · FV proy −€1.220k · BESS proy +€2.172k · DSCR sub 1,14-1,31× · MOIC 1,37× · recovery ~1,4×.

**VERIFICAR ANTES:** estructura exacta de los presets (ya leída: meta/production/revenue/capex/opex/degradation/timeline/financing/taxes/valuation/capex_events). Confirmar nombres de campos al adaptar. Solo correr `tests/core tests/unit tests/golden`.

---

## Task 1: Presets SVJ (FV + BESS)

**Files:**
- Create: `src/asset_finance_modeler/assets/infrastructure/presets/svj_fv_cordoba.yaml`
- Create: `src/asset_finance_modeler/assets/infrastructure/presets/svj_bess_cordoba.yaml`
- Test: `tests/unit/test_svj_presets.py`

**Build by CLONING the structure of `solar_pv_50mw_spain.yaml` / `bess_20mw_4h.yaml` (read them) and substituting SVJ inputs.** Key adaptations:
- FV: `production.capacity_mwp: 4.76`, `specific_yield_kwh_kwp: 1582`, `performance_ratio: 0.86`; revenue ppa €43 vol 0.50 + merchant base 36 capture 0.85; capex item `amount_per_unit: 0.93 unit: Wp`; degradation time_based 0.006; horizon 360 M (30y); financing.senior {interest_rate 0.032, tenor_years 10, max_leverage 0.50, auto_size false → use max_leverage as fixed 50%} (confirm how to force 50% debt: the model uses `total_capex*max_leverage` when `auto_size: false`); valuation.discount_rate_annual 0.0537 (hybrid WACC, for consistency) + cost_of_equity_annual 0.075.
- BESS: `production` bess power_mw 4.7, duration_hours 3, round_trip_efficiency 0.85, depth_of_discharge 0.80, cycles_per_day 0.9; revenue arbitrage {`spread_curve_name: spread_da_es`, cycles_per_day 0.9, spread_capture_ratio 0.80} + ancillary {`afrr_eur_mw_yr: 74000`, `curve_points: <ancillary_afrr_es values / 74000 as multipliers, 30 entries>`}; capex item `amount_per_unit: 130.6 unit: kWh`; `capex_events: [{year: 15, amount: 846000, resets_degradation: true, label: repowering}]`; degradation cycle_based (as preset); horizon 360 M; financing.subordinated {principal 1841000, interest_rate 0.085, tenor_years 7, amortization french} (NO senior on the BESS itself — senior lives on the FV; the consolidated waterfall in Task 2 handles subordination); valuation.discount_rate_annual 0.0537 + cost_of_equity_annual 0.085.

- [ ] **Step 1 — Failing test:**
```python
from asset_finance_modeler.assets.infrastructure.loader import load_preset
from asset_finance_modeler.assets.infrastructure.model import InfrastructureModel


def test_svj_presets_load_and_run():
    for name in ("svj_fv_cordoba", "svj_bess_cordoba"):
        cfg = load_preset(name)
        out = InfrastructureModel(cfg).run()
        assert out.summary["total_capex"] > 0
    fv = InfrastructureModel(load_preset("svj_fv_cordoba")).run()
    bess = InfrastructureModel(load_preset("svj_bess_cordoba")).run()
    # FV capex ~4.44M, BESS capex ~1.84M (±15%)
    assert 3.6e6 < fv.summary["total_capex"] < 5.2e6
    assert 1.5e6 < bess.summary["total_capex"] < 2.2e6
```

- [ ] **Step 2 — Run, verify FAIL** (preset not found).
- [ ] **Step 3 — Create the two YAMLs** (clone structure + SVJ inputs above). Compute the 30 ancillary `curve_points` multipliers = `ancillary_afrr_es` points / 74000.
- [ ] **Step 4 — Run, verify PASS.** Print both assets' KPIs (`npv_equity`, `irr_project`, `total_capex`, `dscr_min`) for inspection. ruff/yaml valid; presets load.
- [ ] **Step 5 — Commit:**
```bash
git add src/asset_finance_modeler/assets/infrastructure/presets/svj_fv_cordoba.yaml src/asset_finance_modeler/assets/infrastructure/presets/svj_bess_cordoba.yaml tests/unit/test_svj_presets.py
git commit -m "feat(presets): SVJ FV + BESS Cordoba (inputs reales del deal)"
```

---

## Task 2: `HybridProject` con deuda consolidada (senior + subordinado)

**Files:**
- Modify: `src/asset_finance_modeler/assets/hybrid/model.py`
- Test: `tests/unit/test_hybrid_consolidated_debt.py`

**Intent:** extender `HybridProject`/`HybridResult` para, opcionalmente, modelar deuda a nivel consolidado: un senior y un subordinado (cada uno `SubordinatedDebtConfig`-like o reusando `SeniorDebtConfig`/`SubordinatedDebtConfig`) servidos sobre el **CFADS consolidado** (= EBITDA consolidado, suma de `pnl["ebitda"]` anual de los activos). Calcular, con las funciones ya existentes:
- `consolidated_ebitda` (suma anual de EBITDA de los activos).
- `senior_ds`/`sub_ds` (series de servicio anual vía `AmortizationSchedule(...).rows()` `total_payment`).
- `dscr_senior`, `dscr_subordinated` vía `compute_waterfall_dscr(consolidated_ebitda, [senior_ds, sub_ds])` → min/avg.
- `moic_subordinated = compute_moic(sub_ds, sub_principal)`.
- `recovery_going_concern = compute_recovery_multiple(consolidated_ebitda, from_period=sub_tenor, discount_rate, ppy=1, outstanding_principal=sub_principal)`.
Añadir estos a `HybridResult` (con defaults). API: `HybridProject(configs, discount_rate_annual, senior=None, subordinated=None)`.

**VERIFY FIRST:** cómo obtener el EBITDA anual por activo del `FinancialOutput` (`pnl["ebitda"]` per-period → anual con el mismo `_to_annual`). Reusar `compute_waterfall_dscr`/`compute_moic`/`compute_recovery_multiple` (imports). `SeniorDebtConfig`/`SubordinatedDebtConfig` desde el schema (el senior aquí puede pasarse como principal fijo o auto-size sobre EBITDA consolidado — para SVJ, senior FV ≈ €2,22M; usar principal fijo para control).

- [ ] **Step 1 — Failing test:** dos activos + senior fijo + subordinado fijo → `dscr_subordinated_min` finito y < `dscr_senior_min`; `moic_subordinated` > 1; `recovery_going_concern` > 0. (Usa los presets SVJ con senior €2,22M y sub €1,841M; o presets genéricos con números feasibles.)
- [ ] **Step 2 — Run, verify FAIL.**
- [ ] **Step 3 — Implement** la deuda consolidada en `HybridProject.run()` (cuando `senior`/`subordinated` se pasan). Mantener el comportamiento sin deuda intacto.
- [ ] **Step 4 — Run, verify PASS.** Regression `tests/core tests/unit tests/golden -q`. ruff+mypy clean.
- [ ] **Step 5 — Commit:**
```bash
git add src/asset_finance_modeler/assets/hybrid/model.py tests/unit/test_hybrid_consolidated_debt.py
git commit -m "feat(hybrid): deuda consolidada (senior+subordinado) + DSCR/MOIC/recovery a nivel hibrido"
```

---

## Task 3: Modelo SVJ completo + validación vs objetivos

**Files:**
- Create: `tests/unit/test_svj_validation.py`
- Create: `docs/superpowers/svj_validation_report.md` (tabla actual vs objetivo + reconciliaciones)

- [ ] **Step 1 — Build & run** el SVJ híbrido: `HybridProject([load_preset("svj_fv_cordoba"), load_preset("svj_bess_cordoba")], discount_rate_annual=0.0537, senior=<FV senior €2,22M @3,2%/10a>, subordinated=<inversor €1,841M @8,5%/7a francesa>)`. Run.
- [ ] **Step 2 — Validation test** (`tests/unit/test_svj_validation.py`): asserts en rangos razonables (NO exactos — documentar):
```python
def test_svj_hybrid_in_expected_ranges():
    res = <run SVJ hybrid as above>
    # NPV hibrido en el entorno de +1.6M (rango amplio ±40% mientras calibramos)
    assert 0.8e6 < res.npv < 2.6e6
    # DSCR subordinado y MOIC en rango bancable
    assert 0.9 < res.dscr_subordinated_min < 1.6
    assert 1.1 < res.moic_subordinated < 1.6
    assert res.recovery_going_concern > 1.0
```
- [ ] **Step 3 — Reconciliation report:** calcular los KPIs reales y escribir `docs/superpowers/svj_validation_report.md` con tabla **actual vs objetivo** (NPV híbrido vs 1.644, FV proy vs −1.220, BESS proy vs +2.172, DSCR sub vs 1,14-1,31, MOIC vs 1,37, recovery vs ~1,4) y, para cada gap >10%, la causa probable y el input a calibrar (spread/capture/cycles/ancillary/tax/charge). Si algún KPI está lejos, ajustar el input más probable (documentando) e iterar 1-2 veces; NO forzar coincidencia falsa — la honestidad de la reconciliación es el entregable.
- [ ] **Step 4 — Run, verify PASS** (rangos). Regression completa. ruff+mypy clean.
- [ ] **Step 5 — Commit:**
```bash
git add tests/unit/test_svj_validation.py docs/superpowers/svj_validation_report.md
git commit -m "feat(svj): modelo SVJ hibrido + validacion vs objetivos (con reconciliacion)"
```

---

## Self-Review
- **Spec coverage:** presets SVJ reales (T1), deuda consolidada senior+sub a nivel híbrido (T2, cierra el gap arquitectónico del waterfall cross-asset), validación + reconciliación documentada (T3). ✅
- **Honestidad:** los asserts son RANGOS amplios mientras calibramos; el entregable real es el reporte de reconciliación actual-vs-objetivo, no un match forzado. El acoplamiento físico se captura vía cycles_per_day calibrado + spread neto.
- **Type consistency:** reusa `compute_waterfall_dscr`/`compute_moic`/`compute_recovery_multiple`/`consolidate_*`; `HybridResult` extendido con defaults.

## Fase siguiente: F7 Excel-foto (pulir `store/exports.py::to_xlsx` a grado-inversor desde el resultado del motor).
