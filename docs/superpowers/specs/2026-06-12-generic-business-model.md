# Diseño — Modelo de negocio genérico (`assets/business/`)

**Fecha:** 2026-06-12 · **Autores:** Riky + Aurora · **Repo:** `asset-finance-modeler` · **Estado:** spec para revisión

## 1. Propósito

Añadir al motor un **modelo de negocio genérico** para valorar CUALQUIER empresa/activo de tipo negocio (restaurante, industrial, comercio, servicios, una empresa cualquiera) con su **propia cuenta de resultados**: líneas de ingreso, COGS, opex (fijo + variable), capex, working capital, financiación e impuestos → **PyG + FCF + valoración (NPV/IRR/DSCR)**. Con **líneas editables y ampliables** (el usuario añade ingresos/costes que quiera). Encaja en la plataforma multi-activo (`/api/models`) junto a los activos de energía/infraestructura.

El módulo SaaS existente es demasiado específico (churn/LLM/headcount); este es un P&L general y limpio que **reutiliza el core** (`core/statements`, `core/valuation`, `core/financing`, `core/drivers`).

## 2. Schema (`assets/business/schema.py`, Pydantic v2)

```
BusinessModelConfig:
  meta: { name, horizon{periods, frequency M/Q/Y}, base_currency=EUR, start_date }
  revenue: list[RevenueLine]                # ampliable
  cogs: { pct_of_revenue: float = 0.0 }     # COGS como % de ingresos (simple, general)
  opex: { fixed_lines: list[OpexLine], variable_pct_of_revenue: float = 0.0, escalation_pct_yr=0.02 }
  capex: { items: list[CapexItem], events: list[CapexEvent] }   # reusa CapexEvent (yr,amount)
  working_capital: { receivable_days=0, payable_days=0, inventory_days=0 }
  financing: { senior?: SeniorDebtConfig, subordinated?: SubordinatedDebtConfig, max_leverage=0.0 }  # reusa los del infra
  taxes: { corporate_income_tax_rate=0.25, tax_loss_carryforward=true }
  valuation: { discount_rate_annual=0.10, cost_of_equity_annual?, terminal_growth_rate=0.0, terminal_method="gordon" }

RevenueLine: { name, year1_amount: float, growth_pct_yr: float = 0.0 }   # ingreso anual base + crecimiento
  # (alternativa unidades×precio: units, price_per_unit, units_growth — opcional v2)
OpexLine: { name, year1_amount: float, growth_pct_yr: float = 0.0 }
CapexItem: { name, amount: float, period: int = 0, depreciation_years: int = 10 }
```
Todas las listas (revenue/opex/capex) son **ampliables** → así el usuario "añade inputs" (más líneas) desde la plataforma; el introspector (`schema_tree`) ya las expone por path (`revenue[2].year1_amount`).

## 3. Cálculo (`assets/business/engines.py` + `model.py`)

`BusinessModel(cfg).run() -> FinancialOutput` (MISMO tipo que infra, para encajar en `web_api/models._run_config` y la plataforma sin cambios):
- **Revenue** anual = Σ líneas (year1 × (1+growth)^(y-1)), expandido a periodos (ppy).
- **COGS** = revenue × pct → **gross_profit**.
- **Opex** = Σ fixed_lines (con escalation) + variable_pct × revenue → **EBITDA** = gross_profit − opex.
- **Capex** + **depreciation** (reusar `core/depreciation` o straight-line) → **EBIT** = EBITDA − D&A. Eventos capex (reusar helpers `apply_capex_events`).
- **Working capital**: Δ por días sobre revenue/cogs → ajusta CFO (reusar patrón `WorkingCapital` del saas si encaja).
- **Financiación**: `DebtEngine`/`size_debt` del core (senior/subordinado) → interest + principal; **DSCR** (reusar `compute_waterfall_dscr` si hay tramos).
- **Impuestos** sobre EBT (con carryforward) → **net_income**.
- **Estados**: construir `pnl` (revenue, cogs, gross_profit, opex, ebitda, depreciation, ebit, interest_expense, ebt, tax, net_income) y `cashflow` (cfo, cfi, cff) con `core/statements` (mismas claves que infra → la plataforma muestra PyG+FCF igual).
- **KPIs**: NPV (consolidate_npv/compute_dcf), IRR (compute_irr), DSCR, payback → `project_kpis` (mismo dataclass `ProjectKPIs`).

Devolver `FinancialOutput(pnl, cashflow, balance, debt_metrics, revenue_breakdown, valuation, sensitivity=None, summary, inputs_resolved, project_kpis)` — encaja con todo lo existente.

## 4. Loader + presets

- `assets/business/loader.py`: `load_business_preset(name)`.
- Presets de partida (plantillas, todas editables): `business_restaurant.yaml`, `business_industrial.yaml`, `business_generic.yaml`, `real_estate_rental.yaml` — con defaults ilustrativos y realistas por sector.

## 5. Integración con la plataforma (`web_api/models.py`)

- `/api/models` lista también los presets de negocio (asset_type="business"/"real_estate").
- `/api/models/{id}/schema` y `/run` deben **despachar** entre infra y business según el tipo del preset: un registro `MODEL_LOADERS = {infra_ids→infra, business_ids→business}` o detectar por carpeta. `_run_config` se generaliza a `run_model_id(model_id, cfg_dict)` que elige el modelo (`InfrastructureModel` vs `BusinessModel`) y devuelve el mismo dict (kpis+income_statement+cash_flow). Como ambos devuelven `FinancialOutput`, el resto es idéntico.

## 6. Testing
- `BusinessModel`: revenue/cogs/opex/ebitda correctos; capex+depreciation; deuda+DSCR; pnl tiene las claves estándar; NPV finito; añadir una RevenueLine sube el revenue.
- Presets cargan y corren; `schema_tree` expone las líneas (paths `revenue[i].year1_amount`).
- `/api/models` lista los business; `/api/models/business_generic/run` con override de `revenue[0].year1_amount` mueve los KPIs.
- No rompe los 567 tests; ruff+mypy limpios.

## 7. Criterios de aceptación
1. `BusinessModel(cfg).run()` devuelve un `FinancialOutput` con PyG (claves estándar) + FCF + KPIs (NPV/IRR/DSCR).
2. Líneas de revenue/opex/capex ampliables; añadir una línea cambia los resultados.
3. Presets de negocio (restaurante, industrial, genérico, inmobiliario) cargan, corren y aparecen en `/api/models`.
4. `/api/models/{business}/schema` expone TODOS los inputs por secciones; `/run` con override por path recalcula.
5. Se integra en la plataforma sin tocar el frontend (mismo contrato JSON). No rompe nada existente.

## 8. Fuera de alcance (posterior)
- Inputs de TIPO totalmente nuevo más allá de añadir líneas (campos arbitrarios con semántica nueva) — requiere motor de cálculo dinámico; este modelo cubre el 90% vía líneas ampliables.
- Vista de portfolio agregada (todos los activos juntos) — pieza de frontend/endpoint aparte.
- Frontend IB-grade (Fase B de la plataforma) — después de esto.
