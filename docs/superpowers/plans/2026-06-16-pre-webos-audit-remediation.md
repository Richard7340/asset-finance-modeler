# Remediación pre-webOS (auditoría global) — Plan

> REQUIRED SUB-SKILL: superpowers:subagent-driven-development. TDD por fix. Origen: 3 auditorías 2026-06-16 (motor / día-a-día / API). Baselines a preservar: SVJ `npv_hybrid` €918.282, demos creíbles, regresión ~382 passed. Interpreter `.venv/bin/python`; comando regresión en `2026-06-16-engine-remediation-all-assets.md` (NUNCA pytest pelado). Firmar commits `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. SIN tocar web/ salvo nota.

## PASADA 1 — Motor LIVE (core/live.py, web_api/live.py, web_api/actuals.py)
- **L1 (CRÍTICO) tax en overlay de coste/margen:** al sustituir una línea ebitda/ebit/ebt/tax/net_income, propagar solo hasta `ebt`, recomputar `tax` al tipo efectivo del año base y `net_income = ebt − tax`; desplazar CFO por el delta **neto de impuestos**, no bruto. (`core/live.py:196-204`).
- **L2 (ALTO) interest_expense:** no está en `_PNL_ORDER` → o se excluye de las líneas trackeables del overlay LIVE, o se trata: `ebt -= delta`, recomputar tax+ni, CFO por delta neto. (`core/live.py:202-204`, `web_api/actuals.py:68`).
- **L3 (ALTO) fecha malformada → 500:** validar `period_start` ISO en el límite Pydantic (`ActualInput`) → 400; y/o `_year_index` devuelve sentinela que el guard `0<=idx<n` descarta en vez de lanzar. (`web_api/actuals.py:112-130`).
- **L4 (MED) residual + gordon doble-conteo:** cuando `terminal_method != none`, NO meter `residual_value` en `fcf[-1]`; sumar su PV aparte (o exigir mutuamente excluyentes). (`core/live.py:74-76`).
- **Tests:** ejercitar CADA línea trackeable (no solo revenue) y aseverar `NI = EBT − tax` en la serie live; interés sube → NI/CFO bajan; fecha malformada → 400 (POST) y /variance,/live no 500; residual+gordon no duplica.

## PASADA 2 — Motor (cash sweep, opex empresa, NPV infra, inputs silenciosos)
- **E1 (ALTO) cash sweep:** topar el principal acumulado al principal original; poner principal programado a 0 una vez `new_balance`→0 (idealmente re-amortizar sobre saldo reducido). (`assets/infrastructure/model.py:467-490`). Test: con sweep on, Σprincipal ≤ principal drawn; Σcff coherente.
- **E2 (ALTO) opex `growth_pct_yr` por línea:** `year1 * (1+ln.growth_pct_yr|escalation)^y`. (`assets/business/engines.py:33`). Test: subir growth de una línea cambia EBITDA/NI.
- **E3 (MED) NPV/IRR infra desapalancado:** calcular EV de infra sobre FCF desapalancado (NOPAT + D&A − capex ± ΔWC) como business; mantener métricas apalancadas en `npv_equity`/`irr_equity`. (`core/statements.py:103-107`, `model.py:357`). Test: NPV proyecto infra no cambia con leverage/sweep. **Recalcular baselines demo y actualizar goldens con comentario.** Confirmar SVJ €918.282 intacto.
- **E4 (LOW) inputs silenciosos infra:** wire o **ocultar del schema** `reserves.mra_eur`, `reserves.working_capital_eur`, `equity.target_irr`, `equity.distribution_lock_years`, `taxes.r_and_d_deduction_pct`, `meta.inflation_annual` (en infra/business), SLA `uptime_target`. Preferir ocultar lo que no se cablee (que nada editable no haga nada). Test: schema no expone leaves inertes (o el wire mueve KPI).

## PASADA 3 — API robustez + validación + tests (svj.py, introspect, models.py, tests)
- **A1 (CRÍTICO) SVJ override 500:** enrutar overrides de SVJ por validación Pydantic + try/except → 400, como el camino genérico. (`deals/svj.py:_build_deal ~189-194`, `web_api/routes.py:27,32`, `web_api/models.py:278`). Test: `wacc:"abc"` y `wacc:-1` → 400 (no 500) en /api/svj/run, /export, /models/svj_hybrid/run.
- **A2 (MED) validación de leaf en override:** `introspect.set_by_path` debe rechazar leaf inexistente (parent válido, hoja typo) → 400. Test: `financing.senior.bogus`, `meta.tax_rate` → 400.
- **A3 (MED) DSRA por API:** que un cambio de `dsra_months` mueva un KPI surfaced (o documentar por qué no). Test.
- **A4 (MED) mezzanine por API:** surfacing en schema_tree aunque None (como los curve fields); editable y mueve KPI. Test.
- **A5 (HIGH cobertura) golden KPIs por modelo:** fijar npv/irr/dscr_min de los 11 modelos no-SVJ a default. Cazaría derivas silenciosas.
- **A6 test viejo:** arreglar `tests/.../test_schema_aggregate.py::test_valuation_with_sensitivity` (espera `gordon`, ahora default `none`).
- **LOW**: pre-COD/horizonte → surface cuántos actuals se descartan; soft-delete → limpiar/!orfanar actuals; `/live` dscr_min 0.0 sin cff → mostrar n/a.

## Cierre
Regresión completa verde + golden por modelo + SVJ €918.282. Re-correr los 3 verificadores o un smoke E2E. Entonces certificar → integración webOS.
