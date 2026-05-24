# Core Foundation Implementation Plan (Plan 1 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the asset-agnostic core components that all financial models (SaaS, Infrastructure, future) share: protocols, depreciation, degradation, project finance, incentives, and valuation extensions.

**Architecture:** Protocol-based design where `FinancialModel` is a runtime-checkable protocol. All new engines live in `core/` and are asset-agnostic. Existing `DebtEngine` moves from `assets/saas/` to `core/financing.py`. Existing `PnLBuilder`/`BalanceBuilder` get DTA/DTL extensions.

**Tech Stack:** Python 3.12+, Pydantic v2, numpy-financial, pytest

**Depends on:** Nothing (this is the foundation)
**Enables:** Plan 2 (Infrastructure Module) and Plan 3 (MCP Integration)

---

## File Structure

```
src/asset_finance_modeler/core/
  protocols.py      → NEW: FinancialOutput, ProjectKPIs, DebtSizingResult, FinancialModel protocol
  depreciation.py   → NEW: straight_line, declining_balance, macrs, soyd, compute_depreciation
  degradation.py    → NEW: time_based, cycle_based, usage_based, none
  financing.py      → NEW: DebtEngine (moved), ProjectFinanceEngine, size_debt, cash_sweep, dsra
  incentives.py     → NEW: compute_incentives
  valuation.py      ← MODIFY: add compute_irr, compute_lcoe, compute_lcos, compute_discounted_payback
  statements.py     ← MODIFY: DTA/DTL in PnLBuilder + BalanceBuilder

src/asset_finance_modeler/assets/saas/
  engines.py        ← MODIFY: remove DebtEngine, re-import from core
  model.py          ← MODIFY: import DebtEngine from core

tests/unit/
  test_protocols.py         → NEW
  test_depreciation.py      → NEW
  test_degradation.py       → NEW
  test_financing.py         → NEW
  test_incentives.py        → NEW
  test_valuation.py         ← MODIFY: add IRR/LCOE tests
  test_pnl.py               ← MODIFY: add DTA tests
  test_balance_unit_runway.py ← MODIFY: add DTL tests
  test_debt_engine.py       ← MODIFY: update imports
```

---

### Task 1: core/protocols.py — Data Contracts and Protocol

**Files:**
- Create: `src/asset_finance_modeler/core/protocols.py`
- Test: `tests/unit/test_protocols.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_protocols.py
from dataclasses import fields

from asset_finance_modeler.core.protocols import (
    DebtSizingResult,
    FinancialModel,
    FinancialOutput,
    ProjectKPIs,
)


def test_financial_output_has_required_fields():
    names = {f.name for f in fields(FinancialOutput)}
    assert "pnl" in names
    assert "cashflow" in names
    assert "balance" in names
    assert "debt_metrics" in names
    assert "revenue_breakdown" in names
    assert "valuation" in names
    assert "sensitivity" in names
    assert "summary" in names
    assert "inputs_resolved" in names
    assert "project_kpis" in names


def test_financial_output_default_project_kpis_is_none():
    out = FinancialOutput(
        pnl={}, cashflow={}, balance={}, debt_metrics={},
        revenue_breakdown={}, valuation={}, sensitivity=None,
        summary={}, inputs_resolved={},
    )
    assert out.project_kpis is None


def test_project_kpis_fields():
    kpis = ProjectKPIs(
        irr_project=0.08, irr_equity=0.12, npv=1_000_000,
        lcoe=45.0, lcos=None, payback_years=7.5,
        dscr_series=[1.3, 1.4, 1.5], dscr_min=1.3, dscr_avg=1.4,
        discount_rate_used=0.07, debt_sizing=None,
    )
    assert kpis.irr_equity == 0.12
    assert kpis.lcos is None
    assert kpis.dscr_min == 1.3


def test_debt_sizing_result_feasible():
    r = DebtSizingResult(
        max_debt=10_000_000, dscr_series=[1.3, 1.35],
        dscr_min=1.3, dscr_avg=1.325, leverage_ratio=0.75,
        equity_required=3_333_333, feasible=True, reason="ok",
    )
    assert r.feasible is True
    assert r.leverage_ratio == 0.75


def test_debt_sizing_result_infeasible():
    r = DebtSizingResult(
        max_debt=0, dscr_series=[], dscr_min=0, dscr_avg=0,
        leverage_ratio=0, equity_required=10_000_000,
        feasible=False, reason="DSCR target unreachable",
    )
    assert r.feasible is False


def test_financial_model_protocol_check():
    from pydantic import BaseModel

    class DummyConfig(BaseModel):
        x: int = 1

    class GoodModel:
        config_schema = DummyConfig
        def run(self) -> FinancialOutput:
            return FinancialOutput(
                pnl={}, cashflow={}, balance={}, debt_metrics={},
                revenue_breakdown={}, valuation={}, sensitivity=None,
                summary={}, inputs_resolved={},
            )

    assert isinstance(GoodModel(), FinancialModel)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/Users/rikyizquierdo/Documents/New project/asset-finance-modeler" && python -m pytest tests/unit/test_protocols.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'asset_finance_modeler.core.protocols'`

- [ ] **Step 3: Write implementation**

```python
# src/asset_finance_modeler/core/protocols.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from pydantic import BaseModel


@dataclass
class DebtSizingResult:
    max_debt: float
    dscr_series: list[float]
    dscr_min: float
    dscr_avg: float
    leverage_ratio: float
    equity_required: float
    feasible: bool
    reason: str


@dataclass
class ProjectKPIs:
    irr_project: float
    irr_equity: float
    npv: float
    lcoe: float | None
    lcos: float | None
    payback_years: float
    dscr_series: list[float]
    dscr_min: float
    dscr_avg: float
    discount_rate_used: float
    debt_sizing: DebtSizingResult | None


@dataclass
class FinancialOutput:
    pnl: dict[str, list[float]]
    cashflow: dict[str, list[float]]
    balance: dict[str, list[float]]
    debt_metrics: dict[str, list[float]]
    revenue_breakdown: dict[str, list[float]]
    valuation: dict[str, float]
    sensitivity: list[list[float]] | None
    summary: dict[str, float | int]
    inputs_resolved: dict[str, object]
    project_kpis: ProjectKPIs | None = field(default=None)


@runtime_checkable
class FinancialModel(Protocol):
    config_schema: type[BaseModel]

    def run(self) -> FinancialOutput: ...
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "/Users/rikyizquierdo/Documents/New project/asset-finance-modeler" && python -m pytest tests/unit/test_protocols.py -v`
Expected: 6 passed

- [ ] **Step 5: Lint + type check**

Run: `cd "/Users/rikyizquierdo/Documents/New project/asset-finance-modeler" && ruff check src/asset_finance_modeler/core/protocols.py && mypy src/asset_finance_modeler/core/protocols.py`

- [ ] **Step 6: Commit**

```bash
git add src/asset_finance_modeler/core/protocols.py tests/unit/test_protocols.py
git commit -m "feat(core): add FinancialModel protocol + FinancialOutput + ProjectKPIs"
```

---

### Task 2: core/depreciation.py — Accelerated Depreciation Methods

**Files:**
- Create: `src/asset_finance_modeler/core/depreciation.py`
- Test: `tests/unit/test_depreciation.py`

- [ ] **Step 1: Write failing tests for straight-line and MACRS**

```python
# tests/unit/test_depreciation.py
import pytest

from asset_finance_modeler.core.depreciation import (
    compute_depreciation,
    depreciate_declining_balance,
    depreciate_macrs,
    depreciate_soyd,
    depreciate_straight_line,
)


def test_straight_line_basic():
    dep = depreciate_straight_line(amount=120_000, life_periods=12, residual_pct=0)
    assert len(dep) == 12
    assert dep[0] == pytest.approx(10_000)
    assert sum(dep) == pytest.approx(120_000)


def test_straight_line_with_residual():
    dep = depreciate_straight_line(amount=100_000, life_periods=10, residual_pct=0.10)
    assert sum(dep) == pytest.approx(90_000)
    assert dep[0] == pytest.approx(9_000)


def test_macrs_5year():
    dep = depreciate_macrs(amount=100_000, macrs_class=5, periods_per_year=12)
    total = sum(dep)
    assert total == pytest.approx(100_000, abs=1)
    assert dep[0] > dep[-1]
    assert len(dep) == 72  # 6 years × 12 months


def test_macrs_7year():
    dep = depreciate_macrs(amount=200_000, macrs_class=7, periods_per_year=12)
    total = sum(dep)
    assert total == pytest.approx(200_000, abs=1)
    assert len(dep) == 96  # 8 years × 12 months


def test_declining_balance():
    dep = depreciate_declining_balance(
        amount=100_000, life_periods=60, factor=2.0, residual_pct=0.10,
    )
    assert len(dep) == 60
    assert dep[0] > dep[59]
    cumulative = sum(dep)
    assert cumulative == pytest.approx(90_000, abs=100)


def test_soyd():
    dep = depreciate_soyd(amount=100_000, life_periods=24, residual_pct=0)
    assert len(dep) == 24
    assert dep[0] > dep[23]
    assert sum(dep) == pytest.approx(100_000, abs=1)


def test_compute_depreciation_dispatches():
    result = compute_depreciation(
        amount=120_000, years=10, method="straight_line",
        periods_per_year=12, residual_value_pct=0,
    )
    assert "book" in result
    assert "tax" in result
    assert len(result["book"]) == 120
    assert sum(result["book"]) == pytest.approx(120_000)


def test_compute_depreciation_macrs_gives_different_tax():
    result = compute_depreciation(
        amount=100_000, years=20, method="macrs",
        periods_per_year=12, macrs_class=5, residual_value_pct=0,
    )
    assert len(result["book"]) == 240
    assert len(result["tax"]) == 72
    assert sum(result["book"]) == pytest.approx(100_000, abs=1)
    assert sum(result["tax"]) == pytest.approx(100_000, abs=1)


def test_compute_depreciation_unknown_method_raises():
    with pytest.raises(ValueError, match="Unknown depreciation method"):
        compute_depreciation(
            amount=100_000, years=10, method="magic",
            periods_per_year=12,
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/Users/rikyizquierdo/Documents/New project/asset-finance-modeler" && python -m pytest tests/unit/test_depreciation.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

```python
# src/asset_finance_modeler/core/depreciation.py
MACRS_TABLES: dict[int, list[float]] = {
    5: [20.00, 32.00, 19.20, 11.52, 11.52, 5.76],
    7: [14.29, 24.49, 17.49, 12.49, 8.93, 8.92, 8.93, 4.46],
    15: [
        5.00, 9.50, 8.55, 7.70, 6.93, 6.23, 5.90, 5.90,
        5.91, 5.90, 5.91, 5.90, 5.91, 5.90, 5.91, 2.95,
    ],
    20: [
        3.750, 7.219, 6.677, 6.177, 5.713, 5.285, 4.888, 4.522,
        4.462, 4.461, 4.462, 4.461, 4.462, 4.461, 4.462, 4.461,
        4.462, 4.461, 4.462, 4.461, 2.231,
    ],
}


def depreciate_straight_line(
    amount: float, life_periods: int, residual_pct: float = 0,
) -> list[float]:
    depreciable = amount * (1 - residual_pct)
    per_period = depreciable / life_periods
    return [per_period] * life_periods


def depreciate_declining_balance(
    amount: float, life_periods: int, factor: float = 2.0, residual_pct: float = 0,
) -> list[float]:
    residual = amount * residual_pct
    depreciable = amount - residual
    rate = factor / life_periods
    result: list[float] = []
    book_value = amount
    for i in range(life_periods):
        dep = book_value * rate
        if book_value - dep < residual:
            dep = book_value - residual
        if dep < 0:
            dep = 0
        result.append(dep)
        book_value -= dep
    shortfall = depreciable - sum(result)
    if shortfall > 0.01 and result:
        result[-1] += shortfall
    return result


def depreciate_macrs(
    amount: float, macrs_class: int, periods_per_year: int = 12,
) -> list[float]:
    if macrs_class not in MACRS_TABLES:
        raise ValueError(f"Unsupported MACRS class: {macrs_class}. Use one of {sorted(MACRS_TABLES)}")
    annual_pcts = MACRS_TABLES[macrs_class]
    result: list[float] = []
    for pct in annual_pcts:
        annual_dep = amount * pct / 100
        per_period = annual_dep / periods_per_year
        result.extend([per_period] * periods_per_year)
    return result


def depreciate_soyd(
    amount: float, life_periods: int, residual_pct: float = 0,
) -> list[float]:
    depreciable = amount * (1 - residual_pct)
    total_digits = life_periods * (life_periods + 1) // 2
    return [
        depreciable * (life_periods - t) / total_digits
        for t in range(life_periods)
    ]


def compute_depreciation(
    amount: float,
    years: int,
    method: str,
    periods_per_year: int = 12,
    macrs_class: int | None = None,
    residual_value_pct: float = 0,
) -> dict[str, list[float]]:
    life_periods = years * periods_per_year
    book = depreciate_straight_line(amount, life_periods, residual_value_pct)

    if method == "straight_line":
        tax = list(book)
    elif method == "declining_balance":
        tax = depreciate_declining_balance(amount, life_periods, 2.0, residual_value_pct)
    elif method == "macrs":
        if macrs_class is None:
            raise ValueError("macrs_class required for MACRS depreciation")
        tax = depreciate_macrs(amount, macrs_class, periods_per_year)
    elif method == "soyd":
        tax = depreciate_soyd(amount, life_periods, residual_value_pct)
    else:
        raise ValueError(f"Unknown depreciation method: {method!r}")

    return {"book": book, "tax": tax}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "/Users/rikyizquierdo/Documents/New project/asset-finance-modeler" && python -m pytest tests/unit/test_depreciation.py -v`
Expected: 10 passed

- [ ] **Step 5: Lint + commit**

```bash
cd "/Users/rikyizquierdo/Documents/New project/asset-finance-modeler"
ruff check src/asset_finance_modeler/core/depreciation.py
git add src/asset_finance_modeler/core/depreciation.py tests/unit/test_depreciation.py
git commit -m "feat(core): add depreciation module — straight-line, declining balance, MACRS, SOYD"
```

---

### Task 3: core/degradation.py — Asset Degradation Curves

**Files:**
- Create: `src/asset_finance_modeler/core/degradation.py`
- Test: `tests/unit/test_degradation.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_degradation.py
import pytest

from asset_finance_modeler.core.degradation import (
    degradation_cycle_based,
    degradation_none,
    degradation_time_based,
    degradation_usage_based,
)


def test_time_based_basic():
    mults = degradation_time_based(periods=240, annual_rate=0.005, periods_per_year=12)
    assert len(mults) == 240
    assert mults[0] == pytest.approx(1.0)
    assert mults[11] == pytest.approx(1 - 0.005 * (11 / 12), abs=0.001)
    assert mults[239] < mults[0]


def test_time_based_20yr_end_value():
    mults = degradation_time_based(periods=240, annual_rate=0.005, periods_per_year=12)
    assert mults[-1] == pytest.approx(1 - 0.005 * 20, abs=0.01)


def test_cycle_based_declines():
    mults = degradation_cycle_based(
        periods=120, cycles_per_period=45, fade_per_cycle=0.00005,
        calendar_fade_annual=0.02, periods_per_year=12, eol_pct=0.70,
    )
    assert len(mults) == 120
    assert mults[0] == pytest.approx(1.0)
    assert mults[-1] < mults[0]


def test_cycle_based_clamps_at_eol():
    mults = degradation_cycle_based(
        periods=360, cycles_per_period=90, fade_per_cycle=0.001,
        calendar_fade_annual=0.05, periods_per_year=12, eol_pct=0.70,
    )
    assert all(m >= 0.70 for m in mults)


def test_usage_based():
    mults = degradation_usage_based(
        periods=120, hours_per_period=720, loss_per_1000h=0.001,
    )
    assert mults[0] == pytest.approx(1.0)
    assert mults[-1] < 1.0
    assert all(mults[i] >= mults[i + 1] for i in range(len(mults) - 1))


def test_none_returns_ones():
    mults = degradation_none(periods=60)
    assert mults == [1.0] * 60
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/Users/rikyizquierdo/Documents/New project/asset-finance-modeler" && python -m pytest tests/unit/test_degradation.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

```python
# src/asset_finance_modeler/core/degradation.py


def degradation_time_based(
    periods: int, annual_rate: float, periods_per_year: int,
) -> list[float]:
    return [
        max(0.0, 1.0 - annual_rate * t / periods_per_year)
        for t in range(periods)
    ]


def degradation_cycle_based(
    periods: int,
    cycles_per_period: float,
    fade_per_cycle: float,
    calendar_fade_annual: float,
    periods_per_year: int,
    eol_pct: float = 0.70,
) -> list[float]:
    result: list[float] = []
    capacity = 1.0
    calendar_per_period = calendar_fade_annual / periods_per_year
    for _ in range(periods):
        result.append(max(eol_pct, capacity))
        cycle_loss = cycles_per_period * fade_per_cycle
        capacity -= cycle_loss + calendar_per_period
    return result


def degradation_usage_based(
    periods: int, hours_per_period: float, loss_per_1000h: float,
) -> list[float]:
    result: list[float] = []
    efficiency = 1.0
    for _ in range(periods):
        result.append(efficiency)
        efficiency -= hours_per_period / 1000 * loss_per_1000h
        efficiency = max(0.0, efficiency)
    return result


def degradation_none(periods: int) -> list[float]:
    return [1.0] * periods
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "/Users/rikyizquierdo/Documents/New project/asset-finance-modeler" && python -m pytest tests/unit/test_degradation.py -v`
Expected: 6 passed

- [ ] **Step 5: Lint + commit**

```bash
cd "/Users/rikyizquierdo/Documents/New project/asset-finance-modeler"
ruff check src/asset_finance_modeler/core/degradation.py
git add src/asset_finance_modeler/core/degradation.py tests/unit/test_degradation.py
git commit -m "feat(core): add degradation module — time, cycle, usage, none curves"
```

---

### Task 4: Refactor DebtEngine from saas/ to core/financing.py

**Files:**
- Create: `src/asset_finance_modeler/core/financing.py`
- Modify: `src/asset_finance_modeler/assets/saas/engines.py`
- Modify: `tests/unit/test_debt_engine.py`

- [ ] **Step 1: Create core/financing.py with DebtEngine copied from saas/engines.py**

Copy the `DebtEngine` class (lines 110-153 of `assets/saas/engines.py`) and `DebtInstrument` schema import to `core/financing.py`:

```python
# src/asset_finance_modeler/core/financing.py
from dataclasses import dataclass

from asset_finance_modeler.core.drivers import AmortizationSchedule
from asset_finance_modeler.assets.saas.schema import DebtInstrument


@dataclass
class DebtEngine:
    instruments: list[DebtInstrument]
    periods: int
    periods_per_year: int

    def compute(self) -> dict[str, list[float]]:
        interest = [0.0] * self.periods
        principal_repaid = [0.0] * self.periods
        drawdowns = [0.0] * self.periods
        origination_fees = [0.0] * self.periods
        balance = [0.0] * self.periods

        for inst in self.instruments:
            t0 = inst.drawdown_period
            if t0 >= self.periods:
                continue
            drawdowns[t0] += inst.principal
            origination_fees[t0] += inst.principal * inst.origination_fee_pct
            sched = AmortizationSchedule(
                principal=inst.principal,
                annual_rate=inst.interest_rate_annual,
                term_periods=inst.term_months,
                periods_per_year=self.periods_per_year,
                kind=inst.amortization,
                grace_periods=inst.grace_period_months,
                custom_schedule=inst.custom_schedule,
            ).rows()
            for i, row in enumerate(sched):
                t = t0 + i
                if t >= self.periods:
                    break
                interest[t] += row["interest"]
                principal_repaid[t] += row["principal_payment"]
                balance[t] += row["balance_end"]

        return {
            "drawdowns": drawdowns,
            "origination_fees": origination_fees,
            "interest_expense": interest,
            "principal_repaid": principal_repaid,
            "balance_outstanding": balance,
        }
```

- [ ] **Step 2: Update saas/engines.py to re-export from core**

Replace the `DebtEngine` class in `assets/saas/engines.py` with a re-export:

```python
# At the top of assets/saas/engines.py, replace the DebtEngine class with:
from asset_finance_modeler.core.financing import DebtEngine

__all__ = ["CohortRevenueEngine", "COGSEngine", "OpexEngine", "CapExEngine", "DebtEngine"]
```

Remove the `DebtEngine` class definition and its `AmortizationSchedule` import (keep the import in the re-export line).

- [ ] **Step 3: Update test_debt_engine.py import**

```python
# tests/unit/test_debt_engine.py — change line 3:
# FROM:
from asset_finance_modeler.assets.saas.engines import DebtEngine
# TO:
from asset_finance_modeler.core.financing import DebtEngine
```

The `DebtInstrument` import stays the same (it's still in saas schema for now).

- [ ] **Step 4: Run ALL existing tests to verify nothing breaks**

Run: `cd "/Users/rikyizquierdo/Documents/New project/asset-finance-modeler" && python -m pytest tests/ -v --tb=short`
Expected: All existing tests pass (no regressions)

- [ ] **Step 5: Commit**

```bash
git add src/asset_finance_modeler/core/financing.py src/asset_finance_modeler/assets/saas/engines.py tests/unit/test_debt_engine.py
git commit -m "refactor: move DebtEngine from assets/saas/ to core/financing.py"
```

---

### Task 5: core/financing.py — Project Finance Engine

**Files:**
- Modify: `src/asset_finance_modeler/core/financing.py`
- Test: `tests/unit/test_financing.py`

- [ ] **Step 1: Write failing tests for DSRA computation**

```python
# tests/unit/test_financing.py
import pytest

from asset_finance_modeler.core.financing import compute_dsra


def test_dsra_6_months():
    debt_service = [10_000.0] * 24
    dsra = compute_dsra(debt_service, dsra_months=6, periods_per_year=12)
    assert len(dsra) == 24
    assert dsra[0] == pytest.approx(60_000)
    assert dsra[-1] == pytest.approx(0)


def test_dsra_zero_months():
    debt_service = [10_000.0] * 12
    dsra = compute_dsra(debt_service, dsra_months=0, periods_per_year=12)
    assert all(d == 0 for d in dsra)
```

- [ ] **Step 2: Run to verify fail**

Run: `cd "/Users/rikyizquierdo/Documents/New project/asset-finance-modeler" && python -m pytest tests/unit/test_financing.py::test_dsra_6_months -v`
Expected: FAIL — `ImportError: cannot import name 'compute_dsra'`

- [ ] **Step 3: Implement compute_dsra**

Add to `src/asset_finance_modeler/core/financing.py`:

```python
def compute_dsra(
    debt_service: list[float],
    dsra_months: int,
    periods_per_year: int,
) -> list[float]:
    if dsra_months <= 0:
        return [0.0] * len(debt_service)
    n = len(debt_service)
    result: list[float] = []
    for t in range(n):
        lookahead = min(t + dsra_months, n)
        remaining_ds = sum(debt_service[t:lookahead])
        result.append(remaining_ds)
    return result
```

- [ ] **Step 4: Run to verify pass**

Run: `cd "/Users/rikyizquierdo/Documents/New project/asset-finance-modeler" && python -m pytest tests/unit/test_financing.py -v`
Expected: 2 passed

- [ ] **Step 5: Write failing tests for cash sweep**

Add to `tests/unit/test_financing.py`:

```python
from asset_finance_modeler.core.financing import compute_cash_sweep


def test_cash_sweep_above_trigger():
    excess_cash = [50_000.0] * 12
    dscr = [1.5] * 12
    swept = compute_cash_sweep(excess_cash, dscr, trigger_dscr=1.40, sweep_pct=0.50)
    assert all(s == pytest.approx(25_000) for s in swept)


def test_cash_sweep_below_trigger_no_sweep():
    excess_cash = [50_000.0] * 12
    dscr = [1.2] * 12
    swept = compute_cash_sweep(excess_cash, dscr, trigger_dscr=1.40, sweep_pct=0.50)
    assert all(s == 0 for s in swept)


def test_cash_sweep_mixed():
    excess_cash = [50_000.0] * 6
    dscr = [1.5, 1.3, 1.6, 1.1, 1.45, 1.0]
    swept = compute_cash_sweep(excess_cash, dscr, trigger_dscr=1.40, sweep_pct=0.50)
    assert swept[0] == pytest.approx(25_000)
    assert swept[1] == 0
    assert swept[2] == pytest.approx(25_000)
    assert swept[3] == 0
    assert swept[4] == pytest.approx(25_000)
    assert swept[5] == 0
```

- [ ] **Step 6: Implement compute_cash_sweep**

Add to `src/asset_finance_modeler/core/financing.py`:

```python
def compute_cash_sweep(
    excess_cash: list[float],
    dscr_series: list[float],
    trigger_dscr: float,
    sweep_pct: float,
) -> list[float]:
    return [
        excess_cash[t] * sweep_pct if dscr_series[t] >= trigger_dscr else 0.0
        for t in range(len(excess_cash))
    ]
```

- [ ] **Step 7: Run to verify pass**

Run: `cd "/Users/rikyizquierdo/Documents/New project/asset-finance-modeler" && python -m pytest tests/unit/test_financing.py -v`
Expected: 5 passed

- [ ] **Step 8: Write failing tests for debt sizing solver**

Add to `tests/unit/test_financing.py`:

```python
from asset_finance_modeler.core.financing import size_debt
from asset_finance_modeler.core.protocols import DebtSizingResult


def test_size_debt_feasible():
    cfads = [100_000.0] * 180  # 15 years monthly
    result = size_debt(
        cfads=cfads, dscr_target=1.30, dscr_mode="min",
        interest_rate=0.045, tenor_periods=180,
        periods_per_year=12, max_leverage=0.80,
        total_capex=10_000_000, amortization="french", grace_periods=0,
    )
    assert isinstance(result, DebtSizingResult)
    assert result.feasible is True
    assert result.max_debt > 0
    assert result.dscr_min >= 1.29  # allow small solver tolerance
    assert result.leverage_ratio <= 0.80
    assert result.equity_required > 0


def test_size_debt_infeasible():
    cfads = [1_000.0] * 60  # very small cash flows
    result = size_debt(
        cfads=cfads, dscr_target=1.30, dscr_mode="min",
        interest_rate=0.10, tenor_periods=60,
        periods_per_year=12, max_leverage=0.80,
        total_capex=10_000_000, amortization="french", grace_periods=0,
    )
    assert result.feasible is False
    assert result.max_debt == 0


def test_size_debt_leverage_cap():
    cfads = [500_000.0] * 240
    result = size_debt(
        cfads=cfads, dscr_target=1.10, dscr_mode="min",
        interest_rate=0.03, tenor_periods=240,
        periods_per_year=12, max_leverage=0.70,
        total_capex=20_000_000, amortization="french", grace_periods=0,
    )
    assert result.feasible is True
    assert result.max_debt <= 20_000_000 * 0.70 + 1
```

- [ ] **Step 9: Implement size_debt**

Add to `src/asset_finance_modeler/core/financing.py`:

```python
from asset_finance_modeler.core.protocols import DebtSizingResult


def _compute_dscr_for_debt(
    cfads: list[float],
    debt_amount: float,
    interest_rate: float,
    tenor_periods: int,
    periods_per_year: int,
    amortization: str,
    grace_periods: int,
) -> list[float]:
    if debt_amount <= 0:
        return [float("inf")] * len(cfads)
    sched = AmortizationSchedule(
        principal=debt_amount,
        annual_rate=interest_rate,
        term_periods=tenor_periods,
        periods_per_year=periods_per_year,
        kind=amortization,
        grace_periods=grace_periods,
    ).rows()
    n = len(cfads)
    dscr: list[float] = []
    for t in range(n):
        if t < len(sched):
            ds = sched[t]["total_payment"]
            dscr.append(cfads[t] / ds if ds > 0 else float("inf"))
        else:
            dscr.append(float("inf"))
    return dscr


def size_debt(
    cfads: list[float],
    dscr_target: float,
    dscr_mode: str,
    interest_rate: float,
    tenor_periods: int,
    periods_per_year: int,
    max_leverage: float,
    total_capex: float,
    amortization: str,
    grace_periods: int,
) -> DebtSizingResult:
    max_debt_by_leverage = total_capex * max_leverage
    lo, hi = 0.0, max_debt_by_leverage

    for _ in range(50):
        mid = (lo + hi) / 2
        if mid < 1:
            break
        dscr = _compute_dscr_for_debt(
            cfads, mid, interest_rate, tenor_periods,
            periods_per_year, amortization, grace_periods,
        )
        active_dscr = [d for d in dscr[:tenor_periods] if d < float("inf")]
        if not active_dscr:
            lo = mid
            continue
        check = min(active_dscr) if dscr_mode == "min" else sum(active_dscr) / len(active_dscr)
        if check >= dscr_target:
            lo = mid
        else:
            hi = mid

    final_debt = lo
    if final_debt < 1:
        return DebtSizingResult(
            max_debt=0, dscr_series=[], dscr_min=0, dscr_avg=0,
            leverage_ratio=0, equity_required=total_capex,
            feasible=False, reason="DSCR target unreachable with given cash flows",
        )

    final_dscr = _compute_dscr_for_debt(
        cfads, final_debt, interest_rate, tenor_periods,
        periods_per_year, amortization, grace_periods,
    )
    active = [d for d in final_dscr[:tenor_periods] if d < float("inf")]
    return DebtSizingResult(
        max_debt=final_debt,
        dscr_series=final_dscr,
        dscr_min=min(active) if active else 0,
        dscr_avg=sum(active) / len(active) if active else 0,
        leverage_ratio=final_debt / total_capex if total_capex > 0 else 0,
        equity_required=total_capex - final_debt,
        feasible=True,
        reason="ok",
    )
```

- [ ] **Step 10: Run all financing tests**

Run: `cd "/Users/rikyizquierdo/Documents/New project/asset-finance-modeler" && python -m pytest tests/unit/test_financing.py -v`
Expected: 8 passed

- [ ] **Step 11: Run ALL tests for regressions**

Run: `cd "/Users/rikyizquierdo/Documents/New project/asset-finance-modeler" && python -m pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 12: Commit**

```bash
git add src/asset_finance_modeler/core/financing.py tests/unit/test_financing.py
git commit -m "feat(core): add ProjectFinance — DSRA, cash sweep, debt sizing solver"
```

---

### Task 6: core/incentives.py — Incentive Framework

**Files:**
- Create: `src/asset_finance_modeler/core/incentives.py`
- Test: `tests/unit/test_incentives.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_incentives.py
import pytest

from asset_finance_modeler.core.incentives import compute_incentives


def test_capex_grant():
    result = compute_incentives(
        items=[{"type": "capex_grant", "value": 0.30, "duration_years": None, "start_year": 0}],
        periods=120, periods_per_year=12,
        total_capex=10_000_000,
    )
    assert result["total"][0] == pytest.approx(3_000_000)
    assert sum(result["total"][1:]) == 0


def test_production_subsidy():
    production = [1000.0] * 120
    result = compute_incentives(
        items=[{"type": "production_subsidy", "value": 25.0, "duration_years": 5, "start_year": 0}],
        periods=120, periods_per_year=12,
        production_per_period=production,
    )
    assert result["total"][0] == pytest.approx(25_000)
    assert result["total"][59] == pytest.approx(25_000)
    assert result["total"][60] == 0


def test_tax_credit():
    result = compute_incentives(
        items=[{"type": "tax_credit", "value": 0.26, "duration_years": None, "start_year": 0}],
        periods=120, periods_per_year=12,
        total_capex=10_000_000,
    )
    assert result["tax_credits"][0] == pytest.approx(2_600_000)


def test_multiple_incentives():
    production = [1000.0] * 60
    result = compute_incentives(
        items=[
            {"type": "capex_grant", "value": 0.10, "duration_years": None, "start_year": 0},
            {"type": "production_subsidy", "value": 10.0, "duration_years": 3, "start_year": 0},
        ],
        periods=60, periods_per_year=12,
        total_capex=5_000_000, production_per_period=production,
    )
    assert result["total"][0] == pytest.approx(500_000 + 10_000)
    assert result["total"][36] == pytest.approx(0)


def test_no_incentives():
    result = compute_incentives(items=[], periods=12, periods_per_year=12)
    assert result["total"] == [0.0] * 12
```

- [ ] **Step 2: Run to verify fail**

Run: `cd "/Users/rikyizquierdo/Documents/New project/asset-finance-modeler" && python -m pytest tests/unit/test_incentives.py -v`
Expected: FAIL

- [ ] **Step 3: Implement**

```python
# src/asset_finance_modeler/core/incentives.py
from typing import Any


def compute_incentives(
    items: list[dict[str, Any]],
    periods: int,
    periods_per_year: int,
    production_per_period: list[float] | None = None,
    revenue_per_period: list[float] | None = None,
    total_capex: float = 0,
) -> dict[str, list[float]]:
    tax_credits = [0.0] * periods
    subsidies = [0.0] * periods
    grants = [0.0] * periods

    for item in items:
        itype = item["type"]
        value = item["value"]
        duration_years = item.get("duration_years")
        start_year = item.get("start_year", 0)
        start_period = start_year * periods_per_year
        end_period = periods
        if duration_years is not None:
            end_period = min(start_period + duration_years * periods_per_year, periods)

        if itype == "capex_grant":
            if start_period < periods:
                grants[start_period] += total_capex * value

        elif itype == "tax_credit":
            if start_period < periods:
                tax_credits[start_period] += total_capex * value

        elif itype == "production_subsidy":
            if production_per_period is None:
                continue
            for t in range(start_period, end_period):
                if t < periods:
                    subsidies[t] += production_per_period[t] * value

        elif itype == "feed_in_tariff":
            if production_per_period is None:
                continue
            for t in range(start_period, end_period):
                if t < periods:
                    subsidies[t] += production_per_period[t] * value

        elif itype in ("carbon_credit", "rfnbo_premium"):
            if production_per_period is None:
                continue
            for t in range(start_period, end_period):
                if t < periods:
                    subsidies[t] += production_per_period[t] * value

    total = [tax_credits[t] + subsidies[t] + grants[t] for t in range(periods)]
    return {
        "tax_credits": tax_credits,
        "subsidies": subsidies,
        "grants": grants,
        "total": total,
    }
```

- [ ] **Step 4: Run to verify pass**

Run: `cd "/Users/rikyizquierdo/Documents/New project/asset-finance-modeler" && python -m pytest tests/unit/test_incentives.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/asset_finance_modeler/core/incentives.py tests/unit/test_incentives.py
git commit -m "feat(core): add incentives module — tax credits, grants, production subsidies"
```

---

### Task 7: core/valuation.py — IRR, LCOE/LCOS, Discounted Payback

**Files:**
- Modify: `src/asset_finance_modeler/core/valuation.py`
- Modify: `tests/unit/test_valuation.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/unit/test_valuation.py`:

```python
from asset_finance_modeler.core.valuation import (
    compute_discounted_payback,
    compute_irr,
    compute_lcoe,
    compute_lcos,
)


def test_compute_irr_basic():
    cashflows = [-1_000_000] + [150_000] * 12
    irr = compute_irr(cashflows, periods_per_year=1)
    assert 0.05 < irr < 0.15


def test_compute_irr_monthly():
    cashflows = [-500_000] + [10_000] * 120
    irr = compute_irr(cashflows, periods_per_year=12)
    assert irr > 0


def test_compute_lcoe():
    lcoe = compute_lcoe(total_costs_pv=50_000_000, total_energy_pv=1_200_000)
    assert lcoe == pytest.approx(41.67, abs=0.01)


def test_compute_lcos():
    lcos = compute_lcos(total_costs_pv=20_000_000, total_energy_discharged_pv=500_000)
    assert lcos == pytest.approx(40.0)


def test_discounted_payback():
    cashflows = [-1_000_000] + [200_000] * 10
    pb = compute_discounted_payback(cashflows, discount_rate=0.08, periods_per_year=1)
    assert 5 < pb < 8


def test_discounted_payback_never():
    cashflows = [-1_000_000] + [10_000] * 10
    pb = compute_discounted_payback(cashflows, discount_rate=0.10, periods_per_year=1)
    assert pb == float("inf")
```

- [ ] **Step 2: Run to verify fail**

Run: `cd "/Users/rikyizquierdo/Documents/New project/asset-finance-modeler" && python -m pytest tests/unit/test_valuation.py::test_compute_irr_basic -v`
Expected: FAIL — `ImportError: cannot import name 'compute_irr'`

- [ ] **Step 3: Implement — add to core/valuation.py**

Add these functions at the end of `src/asset_finance_modeler/core/valuation.py`:

```python
import numpy_financial as npf  # add to imports at top


def compute_irr(cashflows: list[float], periods_per_year: int) -> float:
    period_irr = npf.irr(cashflows)
    if period_irr is None or not isinstance(period_irr, float):
        return 0.0
    return (1 + period_irr) ** periods_per_year - 1


def compute_lcoe(total_costs_pv: float, total_energy_pv: float) -> float:
    if total_energy_pv <= 0:
        return float("inf")
    return total_costs_pv / total_energy_pv


def compute_lcos(total_costs_pv: float, total_energy_discharged_pv: float) -> float:
    if total_energy_discharged_pv <= 0:
        return float("inf")
    return total_costs_pv / total_energy_discharged_pv


def compute_discounted_payback(
    cashflows: list[float], discount_rate: float, periods_per_year: int,
) -> float:
    period_rate = (1 + discount_rate) ** (1 / periods_per_year) - 1
    cumulative = 0.0
    for t, cf in enumerate(cashflows):
        cumulative += cf / ((1 + period_rate) ** t)
        if cumulative >= 0 and t > 0:
            return float(t) / periods_per_year
    return float("inf")
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd "/Users/rikyizquierdo/Documents/New project/asset-finance-modeler" && python -m pytest tests/unit/test_valuation.py -v`
Expected: All tests pass (existing + 6 new)

- [ ] **Step 5: Commit**

```bash
git add src/asset_finance_modeler/core/valuation.py tests/unit/test_valuation.py
git commit -m "feat(core): add IRR, LCOE/LCOS, discounted payback to valuation"
```

---

### Task 8: core/statements.py — DTA/DTL Extensions

**Files:**
- Modify: `src/asset_finance_modeler/core/statements.py`
- Modify: `tests/unit/test_pnl.py`
- Modify: `tests/unit/test_balance_unit_runway.py`

- [ ] **Step 1: Write failing tests for PnLBuilder with tax depreciation**

Add to `tests/unit/test_pnl.py`:

```python
def test_pnl_with_tax_depreciation_dta():
    """When tax depreciation > book depreciation, DTA is created."""
    from asset_finance_modeler.core.statements import PnLBuilder

    pnl = PnLBuilder(
        revenue=[100_000] * 12,
        cogs=[20_000] * 12,
        opex=[30_000] * 12,
        depreciation=[5_000] * 12,
        interest_expense=[2_000] * 12,
        corporate_tax_rate=0.25,
        tax_depreciation=[15_000] * 12,
    ).build()
    assert "tax_depreciation" in pnl
    assert "dta_dtl" in pnl
    assert pnl["dta_dtl"][0] > 0  # DTA when tax dep > book dep
    assert pnl["tax"][0] < (100_000 - 20_000 - 30_000 - 5_000 - 2_000) * 0.25


def test_pnl_without_tax_depreciation_unchanged():
    """When no tax_depreciation provided, behavior is identical to original."""
    from asset_finance_modeler.core.statements import PnLBuilder

    pnl = PnLBuilder(
        revenue=[100_000] * 6,
        cogs=[20_000] * 6,
        opex=[30_000] * 6,
        depreciation=[5_000] * 6,
        interest_expense=[2_000] * 6,
        corporate_tax_rate=0.25,
    ).build()
    assert "dta_dtl" not in pnl or all(d == 0 for d in pnl.get("dta_dtl", []))
```

- [ ] **Step 2: Run to verify fail**

Run: `cd "/Users/rikyizquierdo/Documents/New project/asset-finance-modeler" && python -m pytest tests/unit/test_pnl.py::test_pnl_with_tax_depreciation_dta -v`
Expected: FAIL — `TypeError: PnLBuilder.__init__() got an unexpected keyword argument 'tax_depreciation'`

- [ ] **Step 3: Extend PnLBuilder**

In `src/asset_finance_modeler/core/statements.py`, modify `PnLBuilder`:

```python
@dataclass
class PnLBuilder:
    revenue: list[float]
    cogs: list[float]
    opex: list[float]
    depreciation: list[float]
    interest_expense: list[float]
    corporate_tax_rate: float
    carryforward_enabled: bool = True
    tax_depreciation: list[float] | None = None

    def build(self) -> dict[str, list[float]]:
        n = len(self.revenue)
        gross_profit = [self.revenue[t] - self.cogs[t] for t in range(n)]
        ebitda = [gross_profit[t] - self.opex[t] for t in range(n)]
        ebit = [ebitda[t] - self.depreciation[t] for t in range(n)]
        ebt = [ebit[t] - self.interest_expense[t] for t in range(n)]

        tax_dep = self.tax_depreciation if self.tax_depreciation else self.depreciation
        dta_dtl = [0.0] * n

        tax = [0.0] * n
        net_income = [0.0] * n
        loss_carry = 0.0

        for t in range(n):
            book_ebt = ebt[t]
            tax_ebt = ebitda[t] - tax_dep[t] - self.interest_expense[t]
            dep_diff = tax_dep[t] - self.depreciation[t]
            dta_dtl[t] = dep_diff * self.corporate_tax_rate

            if tax_ebt >= 0:
                taxable = tax_ebt
                if self.carryforward_enabled and loss_carry > 0:
                    used = min(loss_carry, taxable)
                    taxable -= used
                    loss_carry -= used
                tax[t] = taxable * self.corporate_tax_rate
            else:
                tax[t] = 0
                if self.carryforward_enabled:
                    loss_carry += -tax_ebt

            net_income[t] = book_ebt - tax[t]

        result: dict[str, list[float]] = {
            "revenue": list(self.revenue),
            "cogs": list(self.cogs),
            "gross_profit": gross_profit,
            "opex": list(self.opex),
            "ebitda": ebitda,
            "depreciation": list(self.depreciation),
            "ebit": ebit,
            "interest_expense": list(self.interest_expense),
            "ebt": ebt,
            "tax": tax,
            "net_income": net_income,
        }
        if self.tax_depreciation is not None:
            result["tax_depreciation"] = list(self.tax_depreciation)
            result["dta_dtl"] = dta_dtl
        return result
```

- [ ] **Step 4: Run PnL tests (all)**

Run: `cd "/Users/rikyizquierdo/Documents/New project/asset-finance-modeler" && python -m pytest tests/unit/test_pnl.py -v`
Expected: All pass (existing + 2 new)

- [ ] **Step 5: Write failing test for BalanceBuilder DTA/DTL**

Add to `tests/unit/test_balance_unit_runway.py`:

```python
def test_balance_with_dta():
    from asset_finance_modeler.core.statements import BalanceBuilder

    balance = BalanceBuilder(
        cash=[100_000] * 6,
        ar_balance=[10_000] * 6,
        fixed_assets_net=[500_000] * 6,
        debt_outstanding=[200_000] * 6,
        ap_balance=[5_000] * 6,
        equity_initial=100_000,
        dta_balance=[50_000] * 6,
    ).build()
    assert "dta" in balance
    assert balance["total_assets"][0] == 100_000 + 10_000 + 500_000 + 50_000
```

- [ ] **Step 6: Extend BalanceBuilder**

In `src/asset_finance_modeler/core/statements.py`, modify `BalanceBuilder`:

```python
@dataclass
class BalanceBuilder:
    cash: list[float]
    ar_balance: list[float]
    fixed_assets_net: list[float]
    debt_outstanding: list[float]
    ap_balance: list[float]
    equity_initial: float
    dta_balance: list[float] | None = None

    def build(self) -> dict[str, list[float]]:
        n = len(self.cash)
        dta = self.dta_balance if self.dta_balance else [0.0] * n
        total_assets = [
            self.cash[t] + self.ar_balance[t] + self.fixed_assets_net[t] + dta[t]
            for t in range(n)
        ]
        total_liabilities = [self.debt_outstanding[t] + self.ap_balance[t] for t in range(n)]
        equity = [total_assets[t] - total_liabilities[t] for t in range(n)]
        result: dict[str, list[float]] = {
            "cash": list(self.cash),
            "ar": list(self.ar_balance),
            "fixed_assets_net": list(self.fixed_assets_net),
            "total_assets": total_assets,
            "debt": list(self.debt_outstanding),
            "ap": list(self.ap_balance),
            "total_liabilities": total_liabilities,
            "equity": equity,
        }
        if self.dta_balance is not None:
            result["dta"] = list(self.dta_balance)
        return result
```

- [ ] **Step 7: Run ALL tests for regressions**

Run: `cd "/Users/rikyizquierdo/Documents/New project/asset-finance-modeler" && python -m pytest tests/ -v --tb=short`
Expected: All tests pass — existing SaaS tests are not broken because `tax_depreciation` and `dta_balance` default to `None`, preserving original behavior.

- [ ] **Step 8: Commit**

```bash
git add src/asset_finance_modeler/core/statements.py tests/unit/test_pnl.py tests/unit/test_balance_unit_runway.py
git commit -m "feat(core): add DTA/DTL tracking to PnLBuilder + BalanceBuilder"
```

---

## Final Verification

- [ ] **Run full test suite**

```bash
cd "/Users/rikyizquierdo/Documents/New project/asset-finance-modeler"
python -m pytest tests/ -v --tb=short
ruff check src/
mypy src/
```

Expected: All tests pass, no lint errors, no type errors.

**New files created:** 5 (`protocols.py`, `depreciation.py`, `degradation.py`, `financing.py`, `incentives.py`)
**Files modified:** 5 (`valuation.py`, `statements.py`, `saas/engines.py`, `saas/model.py`)
**New tests:** ~40 test functions across 5 new test files + 2 modified
**Total commits:** 8

---

## What's Next

**Plan 2: Infrastructure Module** — Schema definitions (all Pydantic models), production engines (7 types), revenue/OPEX/CAPEX engines, `InfrastructureModel.run()`, YAML presets, scenario.py protocol refactor.

**Plan 3: MCP + Wizard + Dashboard** — MCP tool registration, wizard interactive flow, Chart.js dashboard generator, benchmark lookup engine.
