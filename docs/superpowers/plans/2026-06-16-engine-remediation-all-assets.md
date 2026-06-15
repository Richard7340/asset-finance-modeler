# Remediación del motor multi-activo — Plan por fases

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. TDD por cada fix (test que falla → arreglo → test verde → commit). Pasos con checkbox `- [ ]`.

**Goal:** Dejar TODOS los tipos de activo del motor (solar, eólica, BESS, datacenter, hidrógeno, biometano, business, real estate, SaaS) correctamente integrados y bien calculados, sin parámetros silenciosamente ignorados ni capacidades muertas, para que cualquier usuario tenga control total y resultados fiables.

**Origen:** auditoría multi-activo 2026-06-16 (3 auditores). Hallazgos con `archivo:línea` referenciados abajo.

**Tech Stack:** Python 3.12 · Pydantic v2 · pytest. Interpreter `.venv/bin/python`. 

**Comando de regresión (NO usar pytest pelado — cuelga en embeddings):**
```
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -m pytest -q tests/core tests/golden tests/web tests/unit/test_business_engines.py tests/unit/test_business_model.py tests/unit/test_business_schema.py tests/unit/test_capex_engine.py tests/unit/test_capex_events_model.py tests/unit/test_capex_events_schema.py tests/unit/test_degradation.py tests/unit/test_depreciation.py tests/unit/test_drivers.py tests/unit/test_financing.py tests/unit/test_financing_subordinated.py tests/unit/test_hybrid_consolidated_debt.py tests/unit/test_hybrid_project.py tests/unit/test_infra_capex.py tests/unit/test_infra_model.py tests/unit/test_infra_opex.py tests/unit/test_infra_production.py tests/unit/test_infra_revenue.py tests/unit/test_infra_schema.py tests/unit/test_portfolio.py tests/unit/test_revenue_curves.py tests/unit/test_run_scenario.py tests/unit/test_scenario.py tests/unit/test_scenario_diff.py tests/unit/test_scenario_genealogy.py tests/unit/test_scenario_lifecycle.py tests/unit/test_scenario_protocol.py tests/unit/test_scenario_store.py tests/unit/test_schema_revenue.py tests/unit/test_svj_presets.py tests/unit/test_svj_validation.py tests/unit/test_valuation.py
```
Baseline actual: **288 passed**. Cada fix añade tests; el total debe subir y mantenerse verde. Firmar cada commit con `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

**Decisiones de modelado tomadas (conservadoras, TDD-defendibles):**
- **Valor terminal en activos de vida finita** (solar/eólica/BESS/datacenter): por defecto **SIN valor terminal** (TV=0) en el KPI de proyecto/EV. Exponer un `salvage_value`/`exit` opcional, pero el default deja de meter una perpetuidad. (Real estate es la excepción: SÍ tiene valor residual — ver P0-T7.)
- **FCF de valoración del BusinessModel:** usar **FCF desapalancado** para el VAN/EV (EBIT·(1−t)+D&A−capex±ΔWC, descontado a WACC) y, aparte, VAN equity con CFF completo a Ke. Coherente con infra.
- **Capacidades muertas (DSRA, cash sweep, mezzanine, perfiles):** preferir **cablearlas**; si una no se cablea en su fase, **ocultarla del schema o avisar** para que nada quede silenciosamente inerte.

---

# FASE P0 — Bugs que producen números claramente erróneos

## Task P0-1: CAPEX `unit: MW` resuelve a qty=1 en datacenter y biometano
**Files:** `src/asset_finance_modeler/assets/infrastructure/engines/capex.py` (`_resolve_quantity`, ~161-196); test `tests/unit/test_infra_capex.py`.
- Bug: para `unit=="MW"` busca `capacity_mw/capacity_mwp/power_mw/electrolyzer_mw` en la production config; `DataCenterProduction` solo tiene `it_capacity_mw`, `BiomethaneProduction` solo `capacity_nm3_h` → cae a `1.0` silenciosamente. Datacenter se construye por €11M en vez de €91,6M.
- [ ] **Test primero:** datacenter preset → `total_capex ≈ €91,6M` (no €11M); y un caso unit=MW de biometano resuelve a su capacidad equivalente, no 1.0. Verlo fallar.
- [ ] **Fix:** que el resolver encuentre la capacidad de cada tech — añadir `it_capacity_mw` (datacenter) y una MW-equivalente de biometano (o que cada production engine exponga un `capacity_mw` canónico que el resolver lea). 
- [ ] Regresión verde. Commit `fix(infra): capex unit=MW resuelve capacidad real en datacenter/biometano (no qty=1)`.

## Task P0-2: Hidrógeno ignora el coste de electricidad
**Files:** `src/asset_finance_modeler/assets/infrastructure/engines/opex.py`, `schema.py:46-54`; test `tests/unit/test_infra_opex.py`.
- Bug: `electricity_cost_eur_mwh` (y `electricity_source`) nunca se leen → falta el coste dominante del H2 verde (€6,66M/año a 20MW·€40/MWh) → IRR 67% irreal.
- [ ] **Test primero:** con un config H2, el OPEX refleja `electricity_cost_eur_mwh × electricidad_consumida (production_mwh)`; subir el coste sube el opex y baja el IRR. Verlo fallar.
- [ ] **Fix:** añadir un término de coste variable de electricidad al OPEX driven por la energía consumida del H2.
- [ ] Regresión verde. Commit `fix(infra): H2 incorpora coste de electricidad en OPEX (era ignorado)`.

## Task P0-3: Valor terminal a perpetuidad en activos de vida finita
**Files:** `src/asset_finance_modeler/assets/infrastructure/model.py` (~210-223, donde llama `compute_dcf(..., terminal_method="gordon")`), `core/valuation.py`; tests `tests/unit/test_valuation.py`, `tests/unit/test_infra_model.py`.
- Bug: perpetuidad Gordon aplicada a solar/eólica/BESS/datacenter (vida finita) → el KPI `npv`/`enterprise_value` está distorsionado (datacenter mete −€10M de terminal).
- [ ] **Test primero:** para un activo de vida finita, el EV/`npv` NO incluye una perpetuidad (TV=0 por defecto); comparar contra el FCF descontado sin terminal. Verlo fallar (hoy incluye la perpetuidad).
- [ ] **Fix:** default `terminal_method="none"` (TV=0) para infra de vida finita; mantener Gordon/exit disponibles como opción explícita. Asegurar que el SVJ híbrido (que ya usa `consolidate_npv` sin TV) no cambia.
- [ ] Regresión verde (actualizar goldens que legítimamente cambien, con comentario). Commit `fix(valuation): sin valor terminal por defecto en activos de vida finita (era perpetuidad Gordon)`.

## Task P0-4: BusinessModel — FCF de valoración mal en deals apalancados
**Files:** `src/asset_finance_modeler/assets/business/model.py` (~88-99); test `tests/unit/test_business_model.py`.
- Bug: `fcf_annual = cfo + cfi`; CFO lleva `net_income` (con interés deducido, apalancado) pero el CFF (drawdown + principal) se descarta → paga interés pero nunca contabiliza el principal de la deuda → EV infravalorado e inconsistente.
- [ ] **Test primero:** para un business apalancado, el FCF de valoración es desapalancado coherente (EBIT·(1−t)+D&A−capex±ΔWC) y el EV no queda artificialmente negativo por ignorar el principal. Verlo fallar.
- [ ] **Fix:** usar FCF desapalancado para VAN/EV (descontado a WACC); equity NPV aparte con CFF completo a Ke. 
- [ ] Regresión verde. Commit `fix(business): FCF de valoracion desapalancado coherente para deals con deuda`.

## Task P0-5: BusinessModel — carryforward de impuestos es stub
**Files:** `src/asset_finance_modeler/assets/business/engines.py` (~85), `model.py`; reusar `core/statements.py::PnLBuilder` (carryforward correcto, 44-57); test `tests/unit/test_business_model.py`.
- Bug: `tax = max(0, ebt)*rate` por año, sin arrastrar pérdidas; el flag `taxes.tax_loss_carryforward` no hace nada.
- [ ] **Test primero:** año-1 pérdida −410k, año-2 EBT 400k → impuesto año-2 = 0 (compensado), no 100k. Verlo fallar.
- [ ] **Fix:** reusar `PnLBuilder` (o replicar su lógica) para honrar el carryforward en el BusinessModel.
- [ ] Regresión verde. Commit `fix(business): aplicar tax loss carryforward (era ignorado)`.

## Task P0-6: BusinessModel — working capital es stub
**Files:** `src/asset_finance_modeler/assets/business/model.py` (~88); reusar el patrón de `core/statements.py::CashFlowBuilder` (96-114); test `tests/unit/test_business_model.py`.
- Bug: `cfo_y = net_income + depreciation`; los días de cobro/pago/inventario nunca ajustan la CFO.
- [ ] **Test primero:** subir `receivable_days` 0→90 cambia la CFO (hoy es idéntica). Verlo fallar.
- [ ] **Fix:** aplicar ΔWC (AR/AP/inventario por días sobre revenue/cogs) a la CFO.
- [ ] Regresión verde. Commit `fix(business): working capital real (dias AR/AP/inventario ajustan CFO)`.

## Task P0-7: Real estate — valor residual del inmueble
**Files:** `src/asset_finance_modeler/assets/business/model.py` / schema; preset `real_estate_rental`; test.
- Bug: inmueble de €3M depreciado a 30y con terminal Gordon sobre FCF operativo nunca recupera el capital → VAN estructuralmente negativo.
- [ ] **Test primero:** el VAN del real_estate incluye un valor residual/venta del inmueble al final del horizonte (p. ej. valor de mercado o coste depreciado) → VAN deja de estar artificialmente negativo. Verlo fallar.
- [ ] **Fix:** añadir un `residual_value`/terminal de venta para activos inmobiliarios.
- [ ] Regresión verde. Commit `fix(real_estate): valor residual del inmueble al final del horizonte`.

## Task P0-8: Regresión + golden SVJ
- [ ] Ejecutar el comando de regresión completo. Todo verde.
- [ ] Recalcular y reportar el headline SVJ (no debería cambiar por P0 — el SVJ no usa terminal Gordon ni es business; confirmar `run_svj({})` sigue en €956.749). Si cambia, explicar por qué.

---

# FASE P1 — Completitud (curvas en todas las renovables + timeline)

- **P1-1 Curvas para todas las renovables:** añadir campos `*_curve_name`/`*_points` a PPA, Offtake (H2/biometano), Capacity, Certificate, Rental, SLA en `schema.py` y consumirlos en `revenue.py` (mismo patrón que merchant/arbitrage, sin doble-descuento). Test: curva-driven en cada stream.
- **P1-2 Exponer campos de curva None en el schema:** `introspect.py:40-41` salta leaves None; surface los campos de curva conocidos (opcionales) aunque sean None, para que solar/eólica standalone puedan adjuntar curva por API. Test: schema de solar expone `price_curve_name`.
- **P1-3 Curvas de consultor adicionales en librería:** añadir curvas eólica/H2/biometano/PPA (con fuente) a la librería YAML. Test: `/api/curves` las lista.
- **P1-4 Timeline de construcción/permitting:** consumir `PermitsTimeline` + `construction_drawdown_schedule` en `model.py`/`capex.py` → desplazar inicio de producción y repartir capex; revenue=0 durante construcción. Test: revenue/producción = 0 en meses de construcción. (Afecta IRR/DSCR de todas las tec, incl. SVJ.)
- **P1-5 Depreciar capex events:** depreciar cada `CapexEvent` desde su año (reusar método/vida). Test: depreciación total ≈ total_capex incluyendo el repowering €846k del SVJ.

---

# FASE P2 — Capacidades muertas (cablear o quitar honestamente)

- **P2-1 DSRA:** cablear `compute_dsra` en el cash flow/DSCR (o quitar el campo). Test: `dsra_months` cambia el output.
- **P2-2 Cash sweep:** cablear `compute_cash_sweep`/`CashSweepConfig` (o quitar). Test.
- **P2-3 Mezzanine:** instanciar `MezzanineDebtConfig` en `_compute_debt` (o quitar). Test: mezzanine afecta deuda/DSCR.
- **P2-4 Perfiles de producción:** consumir `irradiation_profile`/`production_profile`/`price_profile` (o quitar). Test: el perfil cambia la forma por periodo.
- **P2-5 Params SaaS muertos:** cablear `price_escalation_annual`, `expansion_revenue_pct`/`gross_revenue_retention`, `payroll_taxes_pct`, `exit_multiple_arr` (honrar el método), `inflation_annual`, etc. (o quitarlos). Tests por cada uno.

---

# FASE P3 — Consistencia y robustez

- **P3-1 Amortización mensual vs anual:** unificar convención entre `InfrastructureModel._compute_debt` (mensual) y `HybridProject._tranche_debt_service` (anual). Test de equivalencia. (Afecta SVJ sub-DSCR ~1,2%.)
- **P3-2 `svj_hybrid` /run shape:** que devuelva también `income_statement`/`cash_flow` como los demás modelos (o adaptador). Test: payload consumible por el mismo cliente.
- **P3-3 Override inválido → 400:** `introspect.set_by_path` KeyError → HTTP 400 claro, no 500. Test.
- **P3-4 Datacenter opex IT-MW vs facility-MW:** estandarizar y documentar. Test/NOTE.
- **P3-5 BESS `cycles_per_day` duplicado:** una sola fuente de verdad (production ↔ arbitrage). Test.
- **P3-6 SaaS por /api/models:** envolver `ModelResults`→`FinancialOutput` o branch SaaS en `web_api/models.py` (si se quiere paridad). Test.

---

# Decisiones a DOCUMENTAR (no bugs) — al cerrar P0-P3

En `docs/superpowers/modeling_assumptions.md`: DSCR usa EBITDA como proxy CFADS (o migrar a CFADS real); PPA-sobre-BESS ignora coste de carga (proxy); datacenter tier/redundancy cosmético; H2 LCOE etiquetado.

---

## Notas
- Tras cada fase: actualizar `gestnova_finance_engine.md` y re-correr regresión.
- Los fixes que tocan el SVJ (P1-4 timeline, P1-5 capex-event deprec, P3-1 amort) moverán el headline; reportar el nuevo número y reconciliar con el Excel en una fase posterior dedicada al deal.
