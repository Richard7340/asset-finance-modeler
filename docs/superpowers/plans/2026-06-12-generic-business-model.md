# Modelo de negocio genérico (`assets/business/`) — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Un modelo de negocio genérico (cuenta de resultados propia) para valorar cualquier empresa/negocio, que devuelve el mismo `FinancialOutput` que infraestructura y encaja en la plataforma `/api/models`.

**Architecture:** Nuevo módulo `assets/business/` (schema + engines + model + loader + presets) que reutiliza `core/statements`, `core/valuation`, `core/financing`, `core/depreciation`, `core/capex_events`. `BusinessModel(cfg).run()` produce `FinancialOutput(pnl, cashflow, ..., project_kpis)` con las MISMAS claves que infra → la plataforma lo muestra sin cambios. Wiring en `web_api/models.py` para despachar infra vs business.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, ruff PL, mypy strict.

**Repo/rama:** `/Users/rikyizquierdo/Documents/New project/asset-finance-modeler`, rama `feat/finance-engine-general-deals`. No romper los 567 tests. Run `tests/web tests/core tests/unit`.

**REFERENCIA CLAVE:** mirar `assets/infrastructure/model.py` como plantilla de cómo se construye un `FinancialOutput` (claves de `pnl`/`cashflow`, `ProjectKPIs`, uso de `core/statements`, `core/valuation`, `DebtEngine`). El nuevo `BusinessModel` sigue ese mismo patrón con inputs de negocio.

---

## Task 1: Schema `assets/business/schema.py`

**Files:** Create `src/asset_finance_modeler/assets/business/__init__.py` (vacío), `assets/business/schema.py`. Test `tests/assets/test_business_schema.py` (crear dir/__init__ si no existe; ver dónde viven los tests de infra schema — probablemente `tests/unit/`).

**VERIFY FIRST:** reutilizar de `assets/infrastructure/schema.py`: `SeniorDebtConfig`, `SubordinatedDebtConfig`, `CapexEvent`, y el patrón `meta/horizon/frequency`. Importarlos, no duplicar.

- [ ] **Step 1 — Failing test:**
```python
from asset_finance_modeler.assets.business.schema import BusinessModelConfig, RevenueLine


def test_business_config_defaults_and_lines():
    cfg = BusinessModelConfig(
        meta={"name": "Restaurante", "horizon": {"periods": 120, "frequency": "M"}},
        revenue=[{"name": "Comidas", "year1_amount": 500000, "growth_pct_yr": 0.03}],
        cogs={"pct_of_revenue": 0.35},
        opex={"fixed_lines": [{"name": "Personal", "year1_amount": 200000}], "variable_pct_of_revenue": 0.05},
        capex={"items": [{"name": "Reforma", "amount": 150000, "period": 0, "depreciation_years": 10}]},
        taxes={"corporate_income_tax_rate": 0.25},
        valuation={"discount_rate_annual": 0.10},
    )
    assert cfg.revenue[0].year1_amount == 500000
    assert cfg.cogs.pct_of_revenue == 0.35
    assert cfg.opex.variable_pct_of_revenue == 0.05
    # ampliable: añadir una línea más
    cfg2 = cfg.model_copy(update={"revenue": cfg.revenue + [RevenueLine(name="Bebidas", year1_amount=120000)]})
    assert len(cfg2.revenue) == 2
```

- [ ] **Step 2 — Run, verify FAIL** (ImportError).
- [ ] **Step 3 — Implement** `schema.py`: `RevenueLine(name:str, year1_amount:float, growth_pct_yr:float=0.0)`, `OpexLine(name, year1_amount, growth_pct_yr=0.0)`, `CapexItemB(name, amount, period:int=0, depreciation_years:int=10)`, `CogsConfig(pct_of_revenue:float=0.0)`, `OpexConfigB(fixed_lines:list[OpexLine]=[], variable_pct_of_revenue:float=0.0, escalation_pct_yr:float=0.02)`, `CapexConfigB(items:list[CapexItemB]=[], events:list[CapexEvent]=[])`, `WorkingCapitalB(receivable_days=0, payable_days=0, inventory_days=0)`, `FinancingB(senior:SeniorDebtConfig|None=None, subordinated:SubordinatedDebtConfig|None=None, max_leverage:float=0.0)`, `TaxesB(corporate_income_tax_rate=0.25, tax_loss_carryforward=True)`, `ValuationB(discount_rate_annual=0.10, cost_of_equity_annual:float|None=None, terminal_growth_rate=0.0, terminal_method="gordon")`, `BusinessMeta(name, horizon, base_currency="EUR", start_date="2026-01-01")` (reusar/espejar `HorizonConfig` de infra), y `BusinessModelConfig` con esos campos (listas con `Field(default_factory=list)`).
- [ ] **Step 4 — Run, verify PASS.** ruff+mypy clean.
- [ ] **Step 5 — Commit** `feat(business): schema BusinessModelConfig (lineas revenue/opex/capex ampliables)`.

## Task 2: Engines puros `assets/business/engines.py`

**Files:** Create `assets/business/engines.py`. Test `tests/.../test_business_engines.py`.

- [ ] **Step 1 — Failing test:**
```python
from asset_finance_modeler.assets.business.engines import revenue_series, opex_series, pnl_rows


def test_revenue_series_lines_and_growth():
    lines = [{"name": "A", "year1_amount": 100.0, "growth_pct_yr": 0.10}, {"name": "B", "year1_amount": 50.0, "growth_pct_yr": 0.0}]
    rev = revenue_series(lines, years=3)
    assert rev == [150.0, 160.0, 171.0]   # A:100,110,121 + B:50,50,50


def test_pnl_rows_basic():
    rows = pnl_rows(revenue=[150.0, 160.0], cogs_pct=0.4, opex=[60.0, 61.0], dep=[10.0, 10.0],
                    interest=[5.0, 4.0], tax_rate=0.25)
    assert rows["gross_profit"][0] == 150.0 * 0.6
    assert rows["ebitda"][0] == 150.0 * 0.6 - 60.0
    assert rows["ebit"][0] == rows["ebitda"][0] - 10.0
    assert rows["ebt"][0] == rows["ebit"][0] - 5.0
    assert rows["tax"][0] == max(0.0, rows["ebt"][0]) * 0.25
    assert rows["net_income"][0] == rows["ebt"][0] - rows["tax"][0]
```

- [ ] **Step 2 — Run, verify FAIL.**
- [ ] **Step 3 — Implement** funciones puras anuales: `revenue_series(lines, years)`, `opex_series(fixed_lines, variable_pct, revenue, escalation, years)`, `pnl_rows(revenue, cogs_pct, opex, dep, interest, tax_rate)` → dict con `revenue, cogs, gross_profit, opex, ebitda, depreciation, ebit, interest_expense, ebt, tax, net_income` (listas). (Impuesto sobre EBT positivo; carryforward simple opcional.)
- [ ] **Step 4 — Run, verify PASS.** ruff+mypy clean.
- [ ] **Step 5 — Commit** `feat(business): engines puros (revenue/opex/pnl_rows)`.

## Task 3: `BusinessModel.run()` → `FinancialOutput`

**Files:** Create `assets/business/model.py`. Test `tests/.../test_business_model.py`.

**VERIFY FIRST:** leer `assets/infrastructure/model.py` para: la firma/campos de `FinancialOutput` (de `core/protocols`), cómo se construye `ProjectKPIs`, cómo se anualiza/expande a periodos (ppy), cómo se usa `DebtEngine`/`size_debt` y `compute_irr`/`compute_dcf`/`consolidate_npv`. Mirror ese patrón.

- [ ] **Step 1 — Failing test:**
```python
from asset_finance_modeler.assets.business.schema import BusinessModelConfig
from asset_finance_modeler.assets.business.model import BusinessModel


def _cfg(rev=500000):
    return BusinessModelConfig(
        meta={"name": "Neg", "horizon": {"periods": 120, "frequency": "M"}},
        revenue=[{"name": "Ventas", "year1_amount": rev, "growth_pct_yr": 0.03}],
        cogs={"pct_of_revenue": 0.35},
        opex={"fixed_lines": [{"name": "Personal", "year1_amount": 200000}], "variable_pct_of_revenue": 0.05},
        capex={"items": [{"name": "Capex", "amount": 150000, "period": 0, "depreciation_years": 10}]},
        taxes={"corporate_income_tax_rate": 0.25}, valuation={"discount_rate_annual": 0.10},
    )


def test_business_run_produces_statements_and_kpis():
    out = BusinessModel(_cfg()).run()
    for k in ("revenue", "ebitda", "ebit", "ebt", "tax", "net_income"):
        assert k in out.pnl
    assert "cfo" in out.cashflow and "cfi" in out.cashflow
    assert out.project_kpis is not None
    # más ingresos -> más EBITDA año 1
    more = BusinessModel(_cfg(rev=800000)).run()
    assert sum(more.pnl["ebitda"][:12]) > sum(out.pnl["ebitda"][:12])
```

- [ ] **Step 2 — Run, verify FAIL.**
- [ ] **Step 3 — Implement** `BusinessModel(cfg).run() -> FinancialOutput`: usar engines (Task 2) para PyG anual, expandir a periodos (ppy del meta), capex+depreciation (straight-line o `core/depreciation`), deuda (core `DebtEngine`/`size_debt` si `financing.senior`/`subordinated`), working capital (Δ sobre revenue/cogs por días → ajusta cfo), construir `pnl`/`cashflow` por periodo, KPIs (NPV vía `compute_dcf`/`consolidate_npv`, IRR vía `compute_irr`, DSCR). Devolver `FinancialOutput(...)` con TODOS sus campos (mirror infra: balance/debt_metrics/revenue_breakdown/valuation/sensitivity=None/summary/inputs_resolved/project_kpis).
- [ ] **Step 4 — Run, verify PASS.** Regresión. ruff+mypy clean.
- [ ] **Step 5 — Commit** `feat(business): BusinessModel.run -> FinancialOutput (PyG+FCF+KPIs)`.

## Task 4: Loader + presets + wiring a `/api/models`

**Files:** Create `assets/business/loader.py`, presets `business_generic.yaml`, `business_restaurant.yaml`, `business_industrial.yaml`, `real_estate_rental.yaml`. Modify `web_api/models.py` (despachar infra vs business). Test `tests/web/test_business_api.py`.

- [ ] **Step 1 — Failing test:**
```python
from fastapi.testclient import TestClient
def _client(mp):
    mp.setenv("SIM_TOKEN","tk"); mp.setenv("SIM_ONLY","1")
    from asset_finance_modeler.mcp_server.http_server import app
    return TestClient(app)

def test_business_models_in_api(monkeypatch):
    c=_client(monkeypatch)
    ids={m["id"] for m in c.get("/api/models?t=tk").json()["models"]}
    assert "business_generic" in ids and "business_restaurant" in ids
    sch=c.get("/api/models/business_generic/schema?t=tk").json()["inputs"]
    assert any(l["path"].startswith("revenue[0]") for l in sch)
    base=c.post("/api/models/business_generic/run?t=tk",json={"overrides":{}}).json()
    up=c.post("/api/models/business_generic/run?t=tk",json={"overrides":{"revenue[0].year1_amount": 999999}}).json()
    assert up["income_statement"]["rows"]["revenue"][0]!=base["income_statement"]["rows"]["revenue"][0]
```

- [ ] **Step 2 — Run, verify FAIL.**
- [ ] **Step 3 — Implement** `loader.load_business_preset(name)` (lee yaml de `assets/business/presets/`); presets con defaults realistas por sector. En `web_api/models.py`: un registro/dispatch — `_business_ids()` (de la carpeta presets de business) y en `list_models`/`schema`/`run`: si el id es business → `load_business_preset` + `BusinessModel`; si no → infra. `_run_config` ya sirve para ambos (ambos devuelven `FinancialOutput`); generalizar la carga del config+modelo.
- [ ] **Step 4 — Run, verify PASS.** Regresión completa (`tests/web tests/core tests/unit`). ruff+mypy clean.
- [ ] **Step 5 — Commit** `feat(business): loader+presets (restaurante/industrial/generico/inmobiliario) + wiring /api/models`.

---

## Self-Review
- **Spec coverage:** schema con líneas ampliables (T1), engines PyG (T2), BusinessModel→FinancialOutput (T3), presets+wiring a la plataforma (T4). ✅
- **Placeholders:** engines/schema con código; T3/T4 con verify-first sobre infra/model.py y FinancialOutput (patrón usado con éxito en todo el proyecto).
- **Type consistency:** `BusinessModelConfig`, `RevenueLine/OpexLine/CapexItemB`, `revenue_series/opex_series/pnl_rows`, `BusinessModel`, claves pnl/cashflow estándar coherentes; reusa SeniorDebtConfig/SubordinatedDebtConfig/CapexEvent de infra.
- **No rompe:** módulo nuevo aditivo; wiring en models.py preserva los presets de infra; regresión en T3/T4.

## Siguiente (no aquí): vista de portfolio agregada + Frontend IB-grade (Fase B plataforma) + migración webOS.
