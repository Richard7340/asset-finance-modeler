# Plan 1 — Foundation + Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Python library foundation, complete pydantic schema for SaaS modeling (Gestnova), and the financial calculation engine end-to-end — without scenarios persistence or MCP server (those are Plans 2 & 3).

**Architecture:** Pure Python library, no I/O surfaces yet. `core/` holds asset-agnostic primitives (TimeGrid, drivers, valuation). `assets/saas/` holds the SaaS schema + engines + orchestrator (`SaasModel`). Each engine is independently testable. Output of `SaasModel.run(config)` is a `ModelResults` dataclass containing all statements + metrics.

**Tech Stack:** Python 3.12, pydantic v2, pandas, numpy_financial, PyYAML, pytest, pytest-snapshot, ruff, mypy.

**Spec reference:** `docs/superpowers/specs/2026-05-14-asset-finance-modeler-design.md`

---

### Task 1: Project scaffolding + tooling

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `README.md`
- Create: `src/asset_finance_modeler/__init__.py`
- Create: `src/asset_finance_modeler/core/__init__.py`
- Create: `src/asset_finance_modeler/assets/__init__.py`
- Create: `src/asset_finance_modeler/assets/saas/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "asset-finance-modeler"
version = "0.1.0"
description = "Comprehensive financial modeling engine for SaaS and other assets, exposed via MCP."
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.7,<3",
    "pandas>=2.2,<3",
    "numpy-financial>=1.0",
    "openpyxl>=3.1",
    "PyYAML>=6.0",
    "jsonpath-ng>=1.6",
]

[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-snapshot>=0.9",
    "ruff>=0.5",
    "mypy>=1.10",
]

[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --strict-markers"
pythonpath = ["src"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "N", "PL"]
ignore = ["PLR0913"]

[tool.mypy]
python_version = "3.12"
strict = true
files = ["src"]
```

- [ ] **Step 2: Create `.gitignore`**

```
.venv/
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/
.ruff_cache/
*.egg-info/
dist/
build/
.DS_Store
```

- [ ] **Step 3: Create `README.md`**

```markdown
# asset-finance-modeler

Comprehensive financial modeling engine exposed via MCP. V1 covers SaaS (Gestnova); designed to scale to renewables, real estate, generic business.

See `docs/superpowers/specs/2026-05-14-asset-finance-modeler-design.md` for design.

## Quickstart (dev)

    python -m venv .venv && source .venv/bin/activate
    pip install -e ".[dev]"
    pytest
```

- [ ] **Step 4: Create empty `__init__.py` files**

Create empty files at:
- `src/asset_finance_modeler/__init__.py`
- `src/asset_finance_modeler/core/__init__.py`
- `src/asset_finance_modeler/assets/__init__.py`
- `src/asset_finance_modeler/assets/saas/__init__.py`
- `tests/__init__.py`
- `tests/unit/__init__.py`

- [ ] **Step 5: Create `tests/conftest.py`**

```python
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))
```

- [ ] **Step 6: Set up venv and install**

Run:
```bash
cd /Users/rikyizquierdo/Documents/New\ project/asset-finance-modeler
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest --version
```

Expected: `pytest 8.x.x` printed.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml .gitignore README.md src/ tests/
git commit -m "feat: project scaffolding with pydantic + pytest + ruff + mypy"
```

---

### Task 2: TimeGrid primitive

**Files:**
- Create: `src/asset_finance_modeler/core/time_grid.py`
- Create: `tests/unit/test_time_grid.py`

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_time_grid.py`:
```python
from datetime import date

import pytest

from asset_finance_modeler.core.time_grid import TimeGrid


def test_monthly_grid_basic():
    g = TimeGrid(periods=12, frequency="M", start_date=date(2026, 1, 1))
    assert g.periods == 12
    assert g.dates[0] == date(2026, 1, 1)
    assert g.dates[11] == date(2026, 12, 1)


def test_quarterly_grid():
    g = TimeGrid(periods=4, frequency="Q", start_date=date(2026, 1, 1))
    assert [d.month for d in g.dates] == [1, 4, 7, 10]


def test_annual_grid():
    g = TimeGrid(periods=3, frequency="Y", start_date=date(2026, 1, 1))
    assert [d.year for d in g.dates] == [2026, 2027, 2028]


def test_periods_per_year():
    assert TimeGrid(periods=12, frequency="M", start_date=date(2026, 1, 1)).periods_per_year == 12
    assert TimeGrid(periods=4, frequency="Q", start_date=date(2026, 1, 1)).periods_per_year == 4
    assert TimeGrid(periods=3, frequency="Y", start_date=date(2026, 1, 1)).periods_per_year == 1


def test_invalid_frequency():
    with pytest.raises(ValueError):
        TimeGrid(periods=12, frequency="X", start_date=date(2026, 1, 1))
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `pytest tests/unit/test_time_grid.py -v`
Expected: ImportError or ModuleNotFoundError.

- [ ] **Step 3: Implement `TimeGrid`**

`src/asset_finance_modeler/core/time_grid.py`:
```python
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

Frequency = Literal["M", "Q", "Y"]

_PERIODS_PER_YEAR: dict[str, int] = {"M": 12, "Q": 4, "Y": 1}


def _add_months(d: date, months: int) -> date:
    total = d.year * 12 + (d.month - 1) + months
    year, month = divmod(total, 12)
    return date(year, month + 1, d.day)


@dataclass(frozen=True)
class TimeGrid:
    periods: int
    frequency: Frequency
    start_date: date
    dates: list[date] = field(init=False)

    def __post_init__(self) -> None:
        if self.frequency not in _PERIODS_PER_YEAR:
            raise ValueError(f"Invalid frequency: {self.frequency!r}")
        if self.periods <= 0:
            raise ValueError("periods must be > 0")
        step = {"M": 1, "Q": 3, "Y": 12}[self.frequency]
        ds = [_add_months(self.start_date, i * step) for i in range(self.periods)]
        object.__setattr__(self, "dates", ds)

    @property
    def periods_per_year(self) -> int:
        return _PERIODS_PER_YEAR[self.frequency]
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `pytest tests/unit/test_time_grid.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/asset_finance_modeler/core/time_grid.py tests/unit/test_time_grid.py
git commit -m "feat(core): TimeGrid primitive (monthly/quarterly/annual)"
```

---

### Task 3: GrowthCurve + AmortizationSchedule drivers

**Files:**
- Create: `src/asset_finance_modeler/core/drivers.py`
- Create: `tests/unit/test_drivers.py`
- Create: `tests/unit/test_amortization.py`

- [ ] **Step 1: Write failing tests for GrowthCurve**

`tests/unit/test_drivers.py`:
```python
import pytest

from asset_finance_modeler.core.drivers import GrowthCurve, expand_growth


def test_constant_value_expands():
    assert expand_growth(5.0, periods=4) == [5.0, 5.0, 5.0, 5.0]


def test_list_value_passes_through():
    assert expand_growth([1.0, 2.0, 3.0], periods=3) == [1.0, 2.0, 3.0]


def test_list_value_wrong_length_raises():
    with pytest.raises(ValueError):
        expand_growth([1.0, 2.0], periods=3)


def test_growth_curve_linear():
    c = GrowthCurve(kind="linear", start=10, end=20, periods=5)
    assert c.values() == [10.0, 12.5, 15.0, 17.5, 20.0]


def test_growth_curve_geometric():
    c = GrowthCurve(kind="geometric", start=10, rate=0.10, periods=4)
    vals = c.values()
    assert vals[0] == 10
    assert vals[1] == pytest.approx(11.0)
    assert vals[3] == pytest.approx(13.31)


def test_growth_curve_step():
    c = GrowthCurve(kind="step", values=[0, 0, 5, 10, 10], periods=5)
    assert c.values() == [0.0, 0.0, 5.0, 10.0, 10.0]
```

- [ ] **Step 2: Write failing tests for AmortizationSchedule**

`tests/unit/test_amortization.py`:
```python
import pytest

from asset_finance_modeler.core.drivers import AmortizationSchedule


def test_bullet_amortization():
    s = AmortizationSchedule(
        principal=100_000, annual_rate=0.05, term_periods=12,
        periods_per_year=12, kind="bullet",
    )
    rows = s.rows()
    assert len(rows) == 12
    # Interest each month = 100k * 0.05 / 12
    expected_interest = 100_000 * 0.05 / 12
    assert rows[0]["interest"] == pytest.approx(expected_interest)
    assert rows[0]["principal_payment"] == 0
    assert rows[11]["principal_payment"] == 100_000
    assert rows[11]["balance_end"] == pytest.approx(0)


def test_linear_amortization():
    s = AmortizationSchedule(
        principal=120_000, annual_rate=0.06, term_periods=12,
        periods_per_year=12, kind="linear",
    )
    rows = s.rows()
    assert all(r["principal_payment"] == pytest.approx(10_000) for r in rows)
    assert rows[11]["balance_end"] == pytest.approx(0)


def test_french_amortization_constant_payment():
    s = AmortizationSchedule(
        principal=100_000, annual_rate=0.06, term_periods=12,
        periods_per_year=12, kind="french",
    )
    rows = s.rows()
    payments = {round(r["total_payment"], 2) for r in rows}
    assert len(payments) == 1  # constant total payment
    assert rows[11]["balance_end"] == pytest.approx(0, abs=0.01)


def test_grace_period_only_interest():
    s = AmortizationSchedule(
        principal=100_000, annual_rate=0.06, term_periods=24,
        periods_per_year=12, kind="french", grace_periods=6,
    )
    rows = s.rows()
    for i in range(6):
        assert rows[i]["principal_payment"] == 0
        assert rows[i]["interest"] > 0
    assert rows[23]["balance_end"] == pytest.approx(0, abs=0.01)
```

- [ ] **Step 3: Run tests, verify they fail**

Run: `pytest tests/unit/test_drivers.py tests/unit/test_amortization.py -v`
Expected: ImportError.

- [ ] **Step 4: Implement drivers**

`src/asset_finance_modeler/core/drivers.py`:
```python
from dataclasses import dataclass
from typing import Literal


def expand_growth(value: float | list[float], periods: int) -> list[float]:
    if isinstance(value, (int, float)):
        return [float(value)] * periods
    if len(value) != periods:
        raise ValueError(f"List length {len(value)} != periods {periods}")
    return [float(v) for v in value]


GrowthKind = Literal["linear", "geometric", "step"]


@dataclass(frozen=True)
class GrowthCurve:
    kind: GrowthKind
    periods: int
    start: float | None = None
    end: float | None = None
    rate: float | None = None
    values_list: list[float] | None = None

    def __init__(
        self,
        kind: GrowthKind,
        periods: int,
        start: float | None = None,
        end: float | None = None,
        rate: float | None = None,
        values: list[float] | None = None,
    ) -> None:
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "periods", periods)
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        object.__setattr__(self, "rate", rate)
        object.__setattr__(self, "values_list", values)

    def values(self) -> list[float]:
        if self.kind == "linear":
            assert self.start is not None and self.end is not None
            if self.periods == 1:
                return [self.start]
            step = (self.end - self.start) / (self.periods - 1)
            return [self.start + step * i for i in range(self.periods)]
        if self.kind == "geometric":
            assert self.start is not None and self.rate is not None
            return [self.start * (1 + self.rate) ** i for i in range(self.periods)]
        if self.kind == "step":
            assert self.values_list is not None and len(self.values_list) == self.periods
            return [float(v) for v in self.values_list]
        raise ValueError(f"Unknown kind: {self.kind}")


AmortKind = Literal["french", "bullet", "linear", "custom"]


@dataclass
class AmortizationSchedule:
    principal: float
    annual_rate: float
    term_periods: int
    periods_per_year: int
    kind: AmortKind = "french"
    grace_periods: int = 0
    custom_schedule: list[float] | None = None

    @property
    def period_rate(self) -> float:
        return self.annual_rate / self.periods_per_year

    def rows(self) -> list[dict[str, float]]:
        rate = self.period_rate
        n_total = self.term_periods
        n_grace = self.grace_periods
        n_amort = n_total - n_grace
        if n_amort <= 0:
            raise ValueError("grace_periods >= term_periods")

        rows: list[dict[str, float]] = []
        balance = self.principal

        # Grace: interest-only
        for _ in range(n_grace):
            interest = balance * rate
            rows.append({
                "balance_start": balance,
                "interest": interest,
                "principal_payment": 0.0,
                "total_payment": interest,
                "balance_end": balance,
            })

        if self.kind == "french":
            # Constant total payment over the amortizing portion
            if rate == 0:
                payment = balance / n_amort
            else:
                payment = balance * rate / (1 - (1 + rate) ** -n_amort)
            for _ in range(n_amort):
                interest = balance * rate
                principal_pmt = payment - interest
                balance_end = balance - principal_pmt
                rows.append({
                    "balance_start": balance,
                    "interest": interest,
                    "principal_payment": principal_pmt,
                    "total_payment": payment,
                    "balance_end": balance_end,
                })
                balance = balance_end
        elif self.kind == "bullet":
            for i in range(n_amort):
                interest = balance * rate
                is_last = i == n_amort - 1
                principal_pmt = balance if is_last else 0.0
                rows.append({
                    "balance_start": balance,
                    "interest": interest,
                    "principal_payment": principal_pmt,
                    "total_payment": interest + principal_pmt,
                    "balance_end": balance - principal_pmt,
                })
                balance -= principal_pmt
        elif self.kind == "linear":
            principal_pmt = balance / n_amort
            for _ in range(n_amort):
                interest = balance * rate
                rows.append({
                    "balance_start": balance,
                    "interest": interest,
                    "principal_payment": principal_pmt,
                    "total_payment": interest + principal_pmt,
                    "balance_end": balance - principal_pmt,
                })
                balance -= principal_pmt
        elif self.kind == "custom":
            assert self.custom_schedule is not None and len(self.custom_schedule) == n_amort
            for principal_pmt in self.custom_schedule:
                interest = balance * rate
                rows.append({
                    "balance_start": balance,
                    "interest": interest,
                    "principal_payment": principal_pmt,
                    "total_payment": interest + principal_pmt,
                    "balance_end": balance - principal_pmt,
                })
                balance -= principal_pmt
        else:
            raise ValueError(f"Unknown amortization kind: {self.kind}")

        return rows
```

- [ ] **Step 5: Run tests, verify they pass**

Run: `pytest tests/unit/test_drivers.py tests/unit/test_amortization.py -v`
Expected: 10 passed.

- [ ] **Step 6: Commit**

```bash
git add src/asset_finance_modeler/core/drivers.py tests/unit/test_drivers.py tests/unit/test_amortization.py
git commit -m "feat(core): GrowthCurve + AmortizationSchedule drivers (french/bullet/linear/custom + grace)"
```

---

### Task 4: ModelMeta + HorizonConfig schemas

**Files:**
- Create: `src/asset_finance_modeler/assets/saas/schema.py`
- Create: `tests/unit/test_schema_meta.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_schema_meta.py`:
```python
from datetime import date

import pytest
from pydantic import ValidationError

from asset_finance_modeler.assets.saas.schema import HorizonConfig, ModelMeta


def test_horizon_basic():
    h = HorizonConfig(periods=60, frequency="M")
    assert h.periods == 60
    assert h.frequency == "M"


def test_horizon_invalid_frequency():
    with pytest.raises(ValidationError):
        HorizonConfig(periods=60, frequency="X")  # type: ignore[arg-type]


def test_model_meta_minimal():
    m = ModelMeta(
        name="gestnova",
        horizon=HorizonConfig(periods=60, frequency="M"),
        start_date=date(2026, 5, 1),
        initial_cash=100_000,
    )
    assert m.base_currency == "EUR"
    assert m.inflation_annual == 0.025
    assert m.fx_rates == {}


def test_model_meta_with_fx():
    m = ModelMeta(
        name="gestnova",
        horizon=HorizonConfig(periods=60, frequency="M"),
        start_date=date(2026, 5, 1),
        initial_cash=100_000,
        fx_rates={"USD": 1.08},
    )
    assert m.fx_rates["USD"] == 1.08
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `pytest tests/unit/test_schema_meta.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement schemas**

`src/asset_finance_modeler/assets/saas/schema.py`:
```python
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, NonNegativeFloat


class HorizonConfig(BaseModel):
    periods: int = Field(gt=0, description="Number of periods")
    frequency: Literal["M", "Q", "Y"] = Field(description="M=monthly, Q=quarterly, Y=annual")


class ModelMeta(BaseModel):
    name: str = Field(description="Model name (e.g. 'gestnova')")
    base_currency: str = Field(default="EUR", description="ISO 4217 base currency")
    fx_rates: dict[str, float] = Field(default_factory=dict, description="FX rates to base_currency keyed by ISO 4217")
    inflation_annual: float = Field(default=0.025, description="Annual inflation rate for real terms")
    horizon: HorizonConfig
    start_date: date = Field(description="First period start date")
    initial_cash: NonNegativeFloat = Field(description="Cash on hand at t=0")
    schema_version: int = Field(default=1, description="Schema version for forward compat")
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `pytest tests/unit/test_schema_meta.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/asset_finance_modeler/assets/saas/schema.py tests/unit/test_schema_meta.py
git commit -m "feat(saas): ModelMeta + HorizonConfig schemas"
```

---

### Task 5: RevenueConfig schema

**Files:**
- Modify: `src/asset_finance_modeler/assets/saas/schema.py`
- Create: `tests/unit/test_schema_revenue.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_schema_revenue.py`:
```python
import pytest
from pydantic import ValidationError

from asset_finance_modeler.assets.saas.schema import (
    AcquisitionConfig,
    PricingConfig,
    RetentionConfig,
    RevenueConfig,
    RevenueSource,
)


def test_pricing_basic():
    p = PricingConfig(per_unit_per_period=300, setup_one_time=1000)
    assert p.per_unit_per_period == 300
    assert p.price_escalation_annual == 0


def test_acquisition_basic():
    a = AcquisitionConfig(
        new_units_per_period=[1, 2, 3, 4, 5],
        avg_units_per_customer=2.5,
        cac_per_customer=800,
    )
    assert a.cac_payback_target_months == 12


def test_retention_default_grr():
    r = RetentionConfig(monthly_churn_rate=0.02)
    assert r.gross_revenue_retention == 1.0


def test_retention_churn_out_of_range():
    with pytest.raises(ValidationError):
        RetentionConfig(monthly_churn_rate=1.5)


def test_revenue_source_complete():
    s = RevenueSource(
        name="agent_subscriptions",
        pricing=PricingConfig(per_unit_per_period=300),
        acquisition=AcquisitionConfig(
            new_units_per_period=5,
            avg_units_per_customer=2.5,
            cac_per_customer=800,
        ),
        retention=RetentionConfig(monthly_churn_rate=0.02),
    )
    assert s.name == "agent_subscriptions"


def test_revenue_config_requires_at_least_one_source():
    with pytest.raises(ValidationError):
        RevenueConfig(sources=[])
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `pytest tests/unit/test_schema_revenue.py -v`
Expected: ImportError.

- [ ] **Step 3: Append to schema.py**

Append to `src/asset_finance_modeler/assets/saas/schema.py`:
```python
from pydantic import NonNegativeInt, conlist


class PricingConfig(BaseModel):
    per_unit_per_period: NonNegativeFloat = Field(description="Recurring price per unit (e.g. €/agent/month)")
    setup_one_time: NonNegativeFloat = Field(default=0, description="One-time setup fee per new customer")
    price_escalation_annual: float = Field(default=0, ge=0, le=1, description="Annual % price increase applied at year boundary")


class AcquisitionConfig(BaseModel):
    new_units_per_period: list[float] | float = Field(description="New units added per period — list (per-period) or constant")
    avg_units_per_customer: NonNegativeFloat = Field(default=1.0, description="Multiplier units per acquired customer")
    cac_per_customer: NonNegativeFloat = Field(description="Cost to acquire one customer (blended)")
    cac_payback_target_months: NonNegativeInt = Field(default=12, description="Informational only")


class RetentionConfig(BaseModel):
    monthly_churn_rate: float = Field(ge=0, le=1, description="Gross logo churn per month (0-1)")
    gross_revenue_retention: float = Field(default=1.0, ge=0, le=1)
    expansion_revenue_pct: float = Field(default=0, ge=0, description="Monthly expansion revenue % over existing base")


class RevenueSource(BaseModel):
    name: str
    pricing: PricingConfig
    acquisition: AcquisitionConfig
    retention: RetentionConfig


class RevenueConfig(BaseModel):
    sources: conlist(RevenueSource, min_length=1)  # type: ignore[valid-type]
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `pytest tests/unit/test_schema_revenue.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/asset_finance_modeler/assets/saas/schema.py tests/unit/test_schema_revenue.py
git commit -m "feat(saas): RevenueConfig schema (pricing, acquisition, retention)"
```

---

### Task 6: COGSConfig schema

**Files:**
- Modify: `src/asset_finance_modeler/assets/saas/schema.py`
- Create: `tests/unit/test_schema_cogs.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_schema_cogs.py`:
```python
from asset_finance_modeler.assets.saas.schema import (
    COGSConfig,
    LLMTier,
    PerActiveCustomerCosts,
    PerActiveUnitCosts,
    TwilioCost,
    VoiceProviderCost,
)


def test_llm_tier():
    t = LLMTier(
        model="sonnet-4-7",
        eur_per_million_input=3.0,
        eur_per_million_output=15.0,
        avg_tokens_in_per_month=800_000,
        avg_tokens_out_per_month=200_000,
    )
    # Expected monthly cost = (0.8 * 3) + (0.2 * 15) = 2.4 + 3.0 = 5.4
    assert t.monthly_cost_eur() == 5.4


def test_voice_provider_stt():
    v = VoiceProviderCost(provider="deepgram", eur_per_minute=0.0043, monthly_usage=200)
    assert v.monthly_cost_eur() == 0.0043 * 200


def test_voice_provider_tts():
    v = VoiceProviderCost(provider="cartesia", eur_per_million_chars=25, monthly_usage=50_000)
    # 50k chars * 25 / 1M = 1.25
    assert v.monthly_cost_eur() == 1.25


def test_twilio_cost():
    t = TwilioCost(
        whatsapp_eur_per_msg=0.005,
        voice_eur_per_min=0.012,
        msgs_per_month=600,
        min_per_month=80,
    )
    # 0.005*600 + 0.012*80 = 3.0 + 0.96 = 3.96
    assert t.monthly_cost_eur() == 3.96


def test_cogs_minimal():
    c = COGSConfig(
        per_active_unit=PerActiveUnitCosts(llm_tokens=[], infra_eur=2.0),
        per_active_customer=PerActiveCustomerCosts(),
    )
    assert c.per_active_customer.support_eur == 0
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `pytest tests/unit/test_schema_cogs.py -v`
Expected: ImportError.

- [ ] **Step 3: Append to schema.py**

Append to `src/asset_finance_modeler/assets/saas/schema.py`:
```python
class LLMTier(BaseModel):
    model: str = Field(description="Model identifier (e.g. 'sonnet-4-7')")
    eur_per_million_input: NonNegativeFloat
    eur_per_million_output: NonNegativeFloat
    avg_tokens_in_per_month: NonNegativeFloat
    avg_tokens_out_per_month: NonNegativeFloat

    def monthly_cost_eur(self) -> float:
        return (
            self.avg_tokens_in_per_month / 1_000_000 * self.eur_per_million_input
            + self.avg_tokens_out_per_month / 1_000_000 * self.eur_per_million_output
        )


class VoiceProviderCost(BaseModel):
    provider: str
    eur_per_minute: float | None = Field(default=None, description="STT pricing")
    eur_per_million_chars: float | None = Field(default=None, description="TTS pricing")
    monthly_usage: NonNegativeFloat = Field(description="Minutes (STT) or chars (TTS) per month per active unit")

    def monthly_cost_eur(self) -> float:
        if self.eur_per_minute is not None:
            return self.eur_per_minute * self.monthly_usage
        if self.eur_per_million_chars is not None:
            return self.monthly_usage / 1_000_000 * self.eur_per_million_chars
        return 0.0


class TwilioCost(BaseModel):
    whatsapp_eur_per_msg: NonNegativeFloat = 0
    voice_eur_per_min: NonNegativeFloat = 0
    msgs_per_month: NonNegativeFloat = 0
    min_per_month: NonNegativeFloat = 0

    def monthly_cost_eur(self) -> float:
        return self.whatsapp_eur_per_msg * self.msgs_per_month + self.voice_eur_per_min * self.min_per_month


class PerActiveUnitCosts(BaseModel):
    llm_tokens: list[LLMTier] = Field(default_factory=list)
    stt: VoiceProviderCost | None = None
    tts: VoiceProviderCost | None = None
    twilio: TwilioCost | None = None
    infra_eur: NonNegativeFloat = 0

    def monthly_cost_eur(self) -> float:
        total = sum(t.monthly_cost_eur() for t in self.llm_tokens) + self.infra_eur
        if self.stt:
            total += self.stt.monthly_cost_eur()
        if self.tts:
            total += self.tts.monthly_cost_eur()
        if self.twilio:
            total += self.twilio.monthly_cost_eur()
        return total


class PerActiveCustomerCosts(BaseModel):
    support_eur: NonNegativeFloat = 0
    onboarding_one_time_eur: NonNegativeFloat = 0


class COGSConfig(BaseModel):
    per_active_unit: PerActiveUnitCosts
    per_active_customer: PerActiveCustomerCosts
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `pytest tests/unit/test_schema_cogs.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/asset_finance_modeler/assets/saas/schema.py tests/unit/test_schema_cogs.py
git commit -m "feat(saas): COGSConfig schema with LLM tiers, voice providers, Twilio"
```

---

### Task 7: OpexConfig schema with TeamRole validator

**Files:**
- Modify: `src/asset_finance_modeler/assets/saas/schema.py`
- Create: `tests/unit/test_schema_opex.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_schema_opex.py`:
```python
import pytest
from pydantic import ValidationError

from asset_finance_modeler.assets.saas.schema import OpexConfig, TeamRole


def test_team_role_headcount_constant():
    r = TeamRole(role="founder", monthly_cost=4000, headcount=3)
    assert r.headcount_at_period(0) == 3
    assert r.headcount_at_period(100) == 3


def test_team_role_headcount_schedule():
    r = TeamRole(role="engineer", monthly_cost=5500, headcount_schedule=[0, 0, 1, 1, 2])
    assert r.headcount_at_period(0) == 0
    assert r.headcount_at_period(2) == 1
    assert r.headcount_at_period(4) == 2
    # Out of range -> last value (assume steady-state)
    assert r.headcount_at_period(99) == 2


def test_team_role_start_period():
    r = TeamRole(role="marketing", monthly_cost=3000, headcount=1, start_period=6)
    assert r.headcount_at_period(5) == 0
    assert r.headcount_at_period(6) == 1


def test_team_role_end_period():
    r = TeamRole(role="contractor", monthly_cost=4500, headcount=1, end_period=12)
    assert r.headcount_at_period(11) == 1
    assert r.headcount_at_period(12) == 0


def test_team_role_both_fields_rejected():
    with pytest.raises(ValidationError):
        TeamRole(role="x", monthly_cost=1000, headcount=2, headcount_schedule=[1, 1])


def test_team_role_neither_field_rejected():
    with pytest.raises(ValidationError):
        TeamRole(role="x", monthly_cost=1000)


def test_opex_defaults():
    o = OpexConfig(team=[TeamRole(role="founder", monthly_cost=4000, headcount=1)])
    assert o.infra_fixed_eur == 0
    assert o.marketing_eur == 0
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `pytest tests/unit/test_schema_opex.py -v`
Expected: ImportError.

- [ ] **Step 3: Append to schema.py**

Append to `src/asset_finance_modeler/assets/saas/schema.py`:
```python
from pydantic import model_validator


class TeamRole(BaseModel):
    role: str
    monthly_cost: NonNegativeFloat = Field(description="Gross + employer SS per person")
    headcount: int | None = Field(default=None, ge=0)
    headcount_schedule: list[int] | None = Field(default=None, description="Per-period headcount (ramp)")
    start_period: NonNegativeInt = 0
    end_period: int | None = None

    @model_validator(mode="after")
    def _validate_headcount(self) -> "TeamRole":
        if self.headcount is None and self.headcount_schedule is None:
            raise ValueError("Either 'headcount' or 'headcount_schedule' must be set")
        if self.headcount is not None and self.headcount_schedule is not None:
            raise ValueError("'headcount' and 'headcount_schedule' are mutually exclusive")
        return self

    def headcount_at_period(self, period: int) -> int:
        if period < self.start_period:
            return 0
        if self.end_period is not None and period >= self.end_period:
            return 0
        if self.headcount is not None:
            return self.headcount
        assert self.headcount_schedule is not None
        idx = period - self.start_period
        if idx < 0:
            return 0
        if idx >= len(self.headcount_schedule):
            return self.headcount_schedule[-1]
        return self.headcount_schedule[idx]


class OpexConfig(BaseModel):
    team: list[TeamRole]
    infra_fixed_eur: NonNegativeFloat | list[NonNegativeFloat] = 0
    marketing_eur: NonNegativeFloat | list[NonNegativeFloat] = 0
    legal_admin_eur: NonNegativeFloat | list[NonNegativeFloat] = 0
    other_eur: NonNegativeFloat | list[NonNegativeFloat] = 0
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `pytest tests/unit/test_schema_opex.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/asset_finance_modeler/assets/saas/schema.py tests/unit/test_schema_opex.py
git commit -m "feat(saas): OpexConfig + TeamRole with headcount/schedule validator"
```

---

### Task 8: CapitalConfig schema (debt, capex, funding, working capital)

**Files:**
- Modify: `src/asset_finance_modeler/assets/saas/schema.py`
- Create: `tests/unit/test_schema_capital.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_schema_capital.py`:
```python
import pytest
from pydantic import ValidationError

from asset_finance_modeler.assets.saas.schema import (
    CapExItem,
    CapitalConfig,
    DebtInstrument,
    FundingRound,
    WorkingCapital,
)


def test_working_capital_defaults():
    wc = WorkingCapital()
    assert wc.days_sales_outstanding == 30
    assert wc.days_payable_outstanding == 30
    assert wc.days_inventory == 0


def test_funding_round():
    r = FundingRound(period=6, amount=250_000, type="pre_seed", dilution=0.15)
    assert r.valuation_pre is None


def test_debt_instrument_french():
    d = DebtInstrument(
        name="enisa", principal=200_000, drawdown_period=0,
        interest_rate_annual=0.045, term_months=84, amortization="french",
    )
    assert d.grace_period_months == 0
    assert d.origination_fee_pct == 0


def test_debt_instrument_custom_requires_schedule():
    with pytest.raises(ValidationError):
        DebtInstrument(
            name="bad", principal=100_000, drawdown_period=0,
            interest_rate_annual=0.04, term_months=12, amortization="custom",
        )


def test_capex_item():
    c = CapExItem(name="laptop_fleet", amount=12_000, period=3, depreciation_years=3)
    assert c.depreciation_years == 3


def test_capital_minimal():
    cap = CapitalConfig(working_capital=WorkingCapital())
    assert cap.debt == []
    assert cap.funding_rounds == []
    assert cap.capex_schedule == []
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `pytest tests/unit/test_schema_capital.py -v`
Expected: ImportError.

- [ ] **Step 3: Append to schema.py**

Append to `src/asset_finance_modeler/assets/saas/schema.py`:
```python
class WorkingCapital(BaseModel):
    days_sales_outstanding: NonNegativeInt = 30
    days_payable_outstanding: NonNegativeInt = 30
    days_inventory: NonNegativeInt = 0


class FundingRound(BaseModel):
    period: NonNegativeInt
    amount: NonNegativeFloat
    type: str
    dilution: float = Field(ge=0, le=1)
    valuation_pre: NonNegativeFloat | None = None


class CapExItem(BaseModel):
    name: str
    amount: NonNegativeFloat
    period: NonNegativeInt
    depreciation_years: int = Field(gt=0)


class DebtInstrument(BaseModel):
    name: str
    principal: NonNegativeFloat
    drawdown_period: NonNegativeInt
    interest_rate_annual: float = Field(ge=0)
    term_months: int = Field(gt=0)
    grace_period_months: NonNegativeInt = 0
    amortization: Literal["french", "bullet", "linear", "custom"] = "french"
    custom_schedule: list[float] | None = None
    origination_fee_pct: float = Field(default=0, ge=0, le=1)

    @model_validator(mode="after")
    def _validate_custom(self) -> "DebtInstrument":
        if self.amortization == "custom" and self.custom_schedule is None:
            raise ValueError("custom amortization requires custom_schedule")
        if self.amortization == "custom":
            assert self.custom_schedule is not None
            expected = self.term_months - self.grace_period_months
            if len(self.custom_schedule) != expected:
                raise ValueError(f"custom_schedule length {len(self.custom_schedule)} != {expected}")
        return self


class CapitalConfig(BaseModel):
    working_capital: WorkingCapital
    capex_schedule: list[CapExItem] = Field(default_factory=list)
    funding_rounds: list[FundingRound] = Field(default_factory=list)
    debt: list[DebtInstrument] = Field(default_factory=list)
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `pytest tests/unit/test_schema_capital.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/asset_finance_modeler/assets/saas/schema.py tests/unit/test_schema_capital.py
git commit -m "feat(saas): CapitalConfig (working_cap, capex, funding, debt with validators)"
```

---

### Task 9: TaxesConfig + ValuationConfig + ExternalDataConfig + SaasModelConfig aggregator

**Files:**
- Modify: `src/asset_finance_modeler/assets/saas/schema.py`
- Create: `tests/unit/test_schema_aggregate.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_schema_aggregate.py`:
```python
from datetime import date

from asset_finance_modeler.assets.saas.schema import (
    AcquisitionConfig,
    COGSConfig,
    CapitalConfig,
    ExternalDataConfig,
    HorizonConfig,
    ModelMeta,
    OpexConfig,
    PerActiveCustomerCosts,
    PerActiveUnitCosts,
    PricingConfig,
    RetentionConfig,
    RevenueConfig,
    RevenueSource,
    SaasModelConfig,
    SensitivityGrid,
    TaxesConfig,
    TeamRole,
    ValuationConfig,
    WorkingCapital,
)


def test_taxes_defaults():
    t = TaxesConfig()
    assert t.corporate_income_tax_rate == 0.25
    assert t.tax_loss_carryforward is True


def test_valuation_with_sensitivity():
    v = ValuationConfig(
        discount_rate_annual=0.20,
        sensitivity_grid=SensitivityGrid(wacc=[0.15, 0.20], growth=[0.02, 0.03]),
    )
    assert v.terminal_method == "gordon"


def test_external_data_empty():
    e = ExternalDataConfig()
    assert e.benchmarks == {}


def test_saas_model_config_minimal():
    cfg = SaasModelConfig(
        meta=ModelMeta(
            name="gestnova",
            horizon=HorizonConfig(periods=12, frequency="M"),
            start_date=date(2026, 5, 1),
            initial_cash=100_000,
        ),
        revenue=RevenueConfig(sources=[
            RevenueSource(
                name="subs",
                pricing=PricingConfig(per_unit_per_period=300),
                acquisition=AcquisitionConfig(
                    new_units_per_period=5, avg_units_per_customer=2.5, cac_per_customer=800,
                ),
                retention=RetentionConfig(monthly_churn_rate=0.02),
            ),
        ]),
        cost_of_revenue=COGSConfig(
            per_active_unit=PerActiveUnitCosts(llm_tokens=[], infra_eur=2),
            per_active_customer=PerActiveCustomerCosts(),
        ),
        operating_expenses=OpexConfig(
            team=[TeamRole(role="founder", monthly_cost=4000, headcount=3)],
        ),
        capital=CapitalConfig(working_capital=WorkingCapital()),
        taxes=TaxesConfig(),
        valuation=ValuationConfig(discount_rate_annual=0.20),
        external_data=ExternalDataConfig(),
    )
    assert cfg.meta.name == "gestnova"
    assert cfg.taxes.corporate_income_tax_rate == 0.25
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `pytest tests/unit/test_schema_aggregate.py -v`
Expected: ImportError.

- [ ] **Step 3: Append to schema.py**

Append to `src/asset_finance_modeler/assets/saas/schema.py`:
```python
from datetime import datetime


class TaxesConfig(BaseModel):
    corporate_income_tax_rate: float = Field(default=0.25, ge=0, le=1)
    vat_rate: float = Field(default=0.21, ge=0, le=1)
    payroll_taxes_pct: float = Field(default=0.30, ge=0, le=1)
    r_and_d_deduction_pct: float = Field(default=0, ge=0, le=1)
    tax_loss_carryforward: bool = True


class SensitivityGrid(BaseModel):
    wacc: list[float]
    growth: list[float]


class ValuationConfig(BaseModel):
    discount_rate_annual: float = Field(gt=0, description="WACC for DCF")
    terminal_growth_rate: float = Field(default=0.025, ge=0)
    exit_multiple_arr: float | None = None
    exit_multiple_ebitda: float | None = None
    terminal_method: Literal["gordon", "exit_multiple"] = "gordon"
    sensitivity_grid: SensitivityGrid | None = None


class ExternalValue(BaseModel):
    value: float
    source: str | None = None
    fetched_at: datetime | None = None
    confidence: Literal["low", "medium", "high"] = "medium"


class ExternalDataConfig(BaseModel):
    benchmarks: dict[str, ExternalValue] = Field(default_factory=dict)
    fx_source: str | None = None
    bond_yields_source: str | None = None


class SaasModelConfig(BaseModel):
    meta: ModelMeta
    revenue: RevenueConfig
    cost_of_revenue: COGSConfig
    operating_expenses: OpexConfig
    capital: CapitalConfig
    taxes: TaxesConfig = Field(default_factory=TaxesConfig)
    valuation: ValuationConfig
    external_data: ExternalDataConfig = Field(default_factory=ExternalDataConfig)
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `pytest tests/unit/test_schema_aggregate.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/asset_finance_modeler/assets/saas/schema.py tests/unit/test_schema_aggregate.py
git commit -m "feat(saas): TaxesConfig + ValuationConfig + ExternalDataConfig + SaasModelConfig aggregator"
```

---

### Task 10: CohortRevenueEngine

**Files:**
- Create: `src/asset_finance_modeler/assets/saas/engines.py`
- Create: `tests/unit/test_cohort_engine.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_cohort_engine.py`:
```python
import pytest

from asset_finance_modeler.assets.saas.engines import CohortRevenueEngine
from asset_finance_modeler.assets.saas.schema import (
    AcquisitionConfig,
    PricingConfig,
    RetentionConfig,
    RevenueSource,
)


def _src(churn=0.02, price=300, new_units=None, avg_units=2.5):
    if new_units is None:
        new_units = 5.0
    return RevenueSource(
        name="subs",
        pricing=PricingConfig(per_unit_per_period=price, setup_one_time=1000),
        acquisition=AcquisitionConfig(
            new_units_per_period=new_units,
            avg_units_per_customer=avg_units,
            cac_per_customer=800,
        ),
        retention=RetentionConfig(monthly_churn_rate=churn),
    )


def test_no_churn_active_units_accumulate():
    eng = CohortRevenueEngine([_src(churn=0.0, new_units=2.0)], periods=4)
    out = eng.compute()
    # period 0: 2 new, total 2
    # period 1: 2 new + 2 retained = 4
    # period 2: 2 + 4 = 6
    # period 3: 2 + 6 = 8
    assert out["active_units"] == pytest.approx([2.0, 4.0, 6.0, 8.0])


def test_with_churn_retention():
    eng = CohortRevenueEngine([_src(churn=0.10, new_units=10.0)], periods=3)
    out = eng.compute()
    # period 0: 10 new
    # period 1: 10*0.9 retained + 10 new = 19
    # period 2: 10*0.81 + 10*0.9 + 10 = 8.1+9+10 = 27.1
    assert out["active_units"][0] == pytest.approx(10.0)
    assert out["active_units"][1] == pytest.approx(19.0)
    assert out["active_units"][2] == pytest.approx(27.1)


def test_revenue_components():
    eng = CohortRevenueEngine([_src(churn=0.0, new_units=2.0, price=300, avg_units=2.5)], periods=3)
    out = eng.compute()
    # new_units = 2 (units, not customers). new_customers = 2/2.5 = 0.8
    # period 0: subscription = 2 * 300 = 600; setup = 0.8 * 1000 = 800
    assert out["subscription_revenue"][0] == pytest.approx(600.0)
    assert out["setup_revenue"][0] == pytest.approx(800.0)


def test_active_customers():
    eng = CohortRevenueEngine([_src(churn=0.0, new_units=5.0, avg_units=2.5)], periods=3)
    out = eng.compute()
    # 5/2.5 = 2 new customers/period
    assert out["active_customers"] == pytest.approx([2.0, 4.0, 6.0])
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `pytest tests/unit/test_cohort_engine.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement engine**

`src/asset_finance_modeler/assets/saas/engines.py`:
```python
from dataclasses import dataclass

from asset_finance_modeler.core.drivers import expand_growth

from .schema import RevenueSource


@dataclass
class CohortRevenueEngine:
    sources: list[RevenueSource]
    periods: int

    def compute(self) -> dict[str, list[float]]:
        active_units = [0.0] * self.periods
        active_customers = [0.0] * self.periods
        subscription = [0.0] * self.periods
        setup = [0.0] * self.periods
        new_units_total = [0.0] * self.periods
        new_customers_total = [0.0] * self.periods

        for src in self.sources:
            new_units_series = expand_growth(src.acquisition.new_units_per_period, self.periods)
            churn = src.retention.monthly_churn_rate
            avg_u_per_c = src.acquisition.avg_units_per_customer
            price = src.pricing.per_unit_per_period
            setup_fee = src.pricing.setup_one_time

            au = [0.0] * self.periods
            ac = [0.0] * self.periods
            sub = [0.0] * self.periods
            stp = [0.0] * self.periods
            for cohort_t, new_u in enumerate(new_units_series):
                new_c = new_u / avg_u_per_c if avg_u_per_c > 0 else 0
                stp[cohort_t] += new_c * setup_fee
                for t in range(cohort_t, self.periods):
                    survival = (1 - churn) ** (t - cohort_t)
                    au[t] += new_u * survival
                    ac[t] += new_c * survival
            for t in range(self.periods):
                sub[t] = au[t] * price

            for t in range(self.periods):
                active_units[t] += au[t]
                active_customers[t] += ac[t]
                subscription[t] += sub[t]
                setup[t] += stp[t]
                new_units_total[t] += new_units_series[t]
                new_customers_total[t] += new_units_series[t] / avg_u_per_c if avg_u_per_c > 0 else 0

        return {
            "active_units": active_units,
            "active_customers": active_customers,
            "subscription_revenue": subscription,
            "setup_revenue": setup,
            "total_revenue": [s + u for s, u in zip(subscription, setup)],
            "new_units": new_units_total,
            "new_customers": new_customers_total,
        }
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `pytest tests/unit/test_cohort_engine.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/asset_finance_modeler/assets/saas/engines.py tests/unit/test_cohort_engine.py
git commit -m "feat(saas): CohortRevenueEngine with per-cohort retention and revenue split"
```

---

### Task 11: COGSEngine + OpexEngine

**Files:**
- Modify: `src/asset_finance_modeler/assets/saas/engines.py`
- Create: `tests/unit/test_cogs_opex_engines.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_cogs_opex_engines.py`:
```python
import pytest

from asset_finance_modeler.assets.saas.engines import COGSEngine, OpexEngine
from asset_finance_modeler.assets.saas.schema import (
    COGSConfig,
    LLMTier,
    OpexConfig,
    PerActiveCustomerCosts,
    PerActiveUnitCosts,
    TeamRole,
)


def test_cogs_per_active_unit():
    cogs = COGSConfig(
        per_active_unit=PerActiveUnitCosts(
            llm_tokens=[LLMTier(
                model="sonnet-4-7",
                eur_per_million_input=3.0,
                eur_per_million_output=15.0,
                avg_tokens_in_per_month=1_000_000,
                avg_tokens_out_per_month=200_000,
            )],
            infra_eur=2.0,
        ),
        per_active_customer=PerActiveCustomerCosts(support_eur=15),
    )
    eng = COGSEngine(cogs, active_units=[2.0, 4.0], active_customers=[1.0, 2.0])
    out = eng.compute()
    # per-unit monthly = 3 + 3 + 2 = 8 EUR
    # period 0: 8*2 + 15*1 = 31
    # period 1: 8*4 + 15*2 = 62
    assert out["total_cogs"][0] == pytest.approx(31.0)
    assert out["total_cogs"][1] == pytest.approx(62.0)


def test_opex_team_ramp():
    opex = OpexConfig(
        team=[
            TeamRole(role="founder", monthly_cost=4000, headcount=3),
            TeamRole(role="engineer", monthly_cost=5500, headcount_schedule=[0, 0, 1, 1, 2]),
        ],
        infra_fixed_eur=1200,
        marketing_eur=2000,
    )
    eng = OpexEngine(opex, periods=5)
    out = eng.compute()
    # period 0: founders 3*4000=12000, eng 0, infra 1200, marketing 2000 -> 15200
    # period 2: 12000 + 5500 + 1200 + 2000 = 20700
    # period 4: 12000 + 11000 + 1200 + 2000 = 26200
    assert out["total_opex"][0] == pytest.approx(15200.0)
    assert out["total_opex"][2] == pytest.approx(20700.0)
    assert out["total_opex"][4] == pytest.approx(26200.0)
    assert out["team_cost"][2] == pytest.approx(17500.0)
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `pytest tests/unit/test_cogs_opex_engines.py -v`
Expected: ImportError.

- [ ] **Step 3: Append to engines.py**

```python
from asset_finance_modeler.core.drivers import expand_growth

from .schema import COGSConfig, OpexConfig


@dataclass
class COGSEngine:
    cogs: COGSConfig
    active_units: list[float]
    active_customers: list[float]

    def compute(self) -> dict[str, list[float]]:
        periods = len(self.active_units)
        per_unit = self.cogs.per_active_unit.monthly_cost_eur()
        support = self.cogs.per_active_customer.support_eur
        variable_unit = [per_unit * u for u in self.active_units]
        variable_customer = [support * c for c in self.active_customers]
        total = [v + c for v, c in zip(variable_unit, variable_customer)]
        return {
            "variable_per_unit": variable_unit,
            "variable_per_customer": variable_customer,
            "total_cogs": total,
        }


def _expand_opex_bucket(value: float | list[float], periods: int) -> list[float]:
    return expand_growth(value, periods)


@dataclass
class OpexEngine:
    opex: OpexConfig
    periods: int

    def compute(self) -> dict[str, list[float]]:
        team_cost = [0.0] * self.periods
        for role in self.opex.team:
            for t in range(self.periods):
                team_cost[t] += role.headcount_at_period(t) * role.monthly_cost

        infra = _expand_opex_bucket(self.opex.infra_fixed_eur, self.periods)
        marketing = _expand_opex_bucket(self.opex.marketing_eur, self.periods)
        legal = _expand_opex_bucket(self.opex.legal_admin_eur, self.periods)
        other = _expand_opex_bucket(self.opex.other_eur, self.periods)

        total = [team_cost[t] + infra[t] + marketing[t] + legal[t] + other[t] for t in range(self.periods)]
        return {
            "team_cost": team_cost,
            "infra_fixed": infra,
            "marketing": marketing,
            "legal_admin": legal,
            "other": other,
            "total_opex": total,
        }
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `pytest tests/unit/test_cogs_opex_engines.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/asset_finance_modeler/assets/saas/engines.py tests/unit/test_cogs_opex_engines.py
git commit -m "feat(saas): COGSEngine + OpexEngine"
```

---

### Task 12: DebtEngine

**Files:**
- Modify: `src/asset_finance_modeler/assets/saas/engines.py`
- Create: `tests/unit/test_debt_engine.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_debt_engine.py`:
```python
import pytest

from asset_finance_modeler.assets.saas.engines import DebtEngine
from asset_finance_modeler.assets.saas.schema import DebtInstrument


def test_single_french_loan():
    d = DebtInstrument(
        name="enisa", principal=100_000, drawdown_period=0,
        interest_rate_annual=0.06, term_months=12, amortization="french",
    )
    eng = DebtEngine([d], periods=24, periods_per_year=12)
    out = eng.compute()
    # period 0..11 have interest; after period 11 balance = 0
    assert out["interest_expense"][0] > 0
    assert out["interest_expense"][12] == pytest.approx(0)
    assert out["principal_repaid"][0] > 0
    assert out["balance_outstanding"][11] == pytest.approx(0, abs=0.01)
    # Drawdown captured at period 0
    assert out["drawdowns"][0] == pytest.approx(100_000)


def test_origination_fee_modeled_as_period_0_cost():
    d = DebtInstrument(
        name="enisa", principal=100_000, drawdown_period=2,
        interest_rate_annual=0.05, term_months=12, amortization="bullet",
        origination_fee_pct=0.02,
    )
    eng = DebtEngine([d], periods=24, periods_per_year=12)
    out = eng.compute()
    assert out["origination_fees"][2] == pytest.approx(2000)
    assert out["drawdowns"][2] == pytest.approx(100_000)


def test_drawdown_timing_shifts_schedule():
    d = DebtInstrument(
        name="late", principal=50_000, drawdown_period=6,
        interest_rate_annual=0.06, term_months=12, amortization="french",
    )
    eng = DebtEngine([d], periods=24, periods_per_year=12)
    out = eng.compute()
    # No interest until drawdown happens
    assert all(out["interest_expense"][t] == 0 for t in range(6))
    assert out["interest_expense"][6] > 0
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `pytest tests/unit/test_debt_engine.py -v`
Expected: ImportError.

- [ ] **Step 3: Append to engines.py**

```python
from asset_finance_modeler.core.drivers import AmortizationSchedule

from .schema import DebtInstrument


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

- [ ] **Step 4: Run tests, verify they pass**

Run: `pytest tests/unit/test_debt_engine.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/asset_finance_modeler/assets/saas/engines.py tests/unit/test_debt_engine.py
git commit -m "feat(saas): DebtEngine multi-instrument with drawdown timing + origination fees"
```

---

### Task 13: P&L assembly with tax carryforward

**Files:**
- Create: `src/asset_finance_modeler/core/statements.py`
- Create: `tests/unit/test_pnl.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_pnl.py`:
```python
import pytest

from asset_finance_modeler.core.statements import PnLBuilder


def test_pnl_basic_no_loss_carryforward():
    pnl = PnLBuilder(
        revenue=[1000, 1500, 2000],
        cogs=[300, 400, 500],
        opex=[500, 500, 500],
        depreciation=[50, 50, 50],
        interest_expense=[20, 20, 20],
        corporate_tax_rate=0.25,
        carryforward_enabled=False,
    ).build()
    # period 0: GP=700, EBITDA=200, EBIT=150, EBT=130, Tax=32.5, NI=97.5
    assert pnl["gross_profit"][0] == 700
    assert pnl["ebitda"][0] == 200
    assert pnl["ebit"][0] == 150
    assert pnl["ebt"][0] == 130
    assert pnl["tax"][0] == pytest.approx(32.5)
    assert pnl["net_income"][0] == pytest.approx(97.5)


def test_pnl_negative_ebt_no_tax_no_carryforward():
    pnl = PnLBuilder(
        revenue=[100],
        cogs=[50],
        opex=[200],
        depreciation=[0],
        interest_expense=[0],
        corporate_tax_rate=0.25,
        carryforward_enabled=False,
    ).build()
    # EBT = -150, tax = 0, NI = -150
    assert pnl["tax"][0] == 0
    assert pnl["net_income"][0] == -150


def test_pnl_loss_carryforward_consumes_against_future_profit():
    pnl = PnLBuilder(
        revenue=[100, 1000],
        cogs=[0, 100],
        opex=[200, 200],
        depreciation=[0, 0],
        interest_expense=[0, 0],
        corporate_tax_rate=0.25,
        carryforward_enabled=True,
    ).build()
    # period 0: EBT = -100, loss carryforward = 100
    # period 1: EBT = 700, taxable = 700 - 100 = 600, tax = 150
    assert pnl["tax"][0] == 0
    assert pnl["tax"][1] == pytest.approx(150)
    assert pnl["net_income"][1] == pytest.approx(550)
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `pytest tests/unit/test_pnl.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement PnLBuilder**

`src/asset_finance_modeler/core/statements.py`:
```python
from dataclasses import dataclass


@dataclass
class PnLBuilder:
    revenue: list[float]
    cogs: list[float]
    opex: list[float]
    depreciation: list[float]
    interest_expense: list[float]
    corporate_tax_rate: float
    carryforward_enabled: bool = True

    def build(self) -> dict[str, list[float]]:
        n = len(self.revenue)
        gross_profit = [self.revenue[t] - self.cogs[t] for t in range(n)]
        ebitda = [gross_profit[t] - self.opex[t] for t in range(n)]
        ebit = [ebitda[t] - self.depreciation[t] for t in range(n)]
        ebt = [ebit[t] - self.interest_expense[t] for t in range(n)]

        tax = [0.0] * n
        net_income = [0.0] * n
        loss_carry = 0.0

        for t in range(n):
            if ebt[t] >= 0:
                taxable = ebt[t]
                if self.carryforward_enabled and loss_carry > 0:
                    used = min(loss_carry, taxable)
                    taxable -= used
                    loss_carry -= used
                tax[t] = taxable * self.corporate_tax_rate
                net_income[t] = ebt[t] - tax[t]
            else:
                tax[t] = 0
                net_income[t] = ebt[t]
                if self.carryforward_enabled:
                    loss_carry += -ebt[t]

        return {
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
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `pytest tests/unit/test_pnl.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/asset_finance_modeler/core/statements.py tests/unit/test_pnl.py
git commit -m "feat(core): PnLBuilder with tax loss carryforward"
```

---

### Task 14: Cash Flow assembly (indirect method)

**Files:**
- Modify: `src/asset_finance_modeler/core/statements.py`
- Create: `tests/unit/test_cashflow.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_cashflow.py`:
```python
import pytest

from asset_finance_modeler.core.statements import CashFlowBuilder


def test_cashflow_basic_no_wc_no_debt():
    cf = CashFlowBuilder(
        net_income=[100, 200],
        depreciation=[50, 50],
        revenue=[1000, 1000],
        cogs=[300, 300],
        dso_days=0, dpo_days=0,
        capex=[0, 0],
        funding_drawdowns=[0, 0],
        debt_drawdowns=[0, 0],
        debt_principal_repaid=[0, 0],
        origination_fees=[0, 0],
        initial_cash=500,
        period_days=30,
    ).build()
    # CFO = NI + D&A = 150, 250
    # cash[0] = 500 + 150 = 650
    # cash[1] = 650 + 250 = 900
    assert cf["cfo"] == pytest.approx([150, 250])
    assert cf["cash"] == pytest.approx([650, 900])


def test_cashflow_funding_round_adds_to_cash():
    cf = CashFlowBuilder(
        net_income=[-100],
        depreciation=[0],
        revenue=[0], cogs=[0], dso_days=0, dpo_days=0,
        capex=[0],
        funding_drawdowns=[250_000],
        debt_drawdowns=[0],
        debt_principal_repaid=[0],
        origination_fees=[0],
        initial_cash=10_000,
        period_days=30,
    ).build()
    # CFO = -100, CFF = 250_000, cash = 10000 -100 + 250_000
    assert cf["cash"][0] == pytest.approx(259_900)


def test_cashflow_debt_drawdown_and_repayment():
    cf = CashFlowBuilder(
        net_income=[0, 0],
        depreciation=[0, 0],
        revenue=[0, 0], cogs=[0, 0], dso_days=0, dpo_days=0,
        capex=[0, 0],
        funding_drawdowns=[0, 0],
        debt_drawdowns=[100_000, 0],
        debt_principal_repaid=[0, 8_000],
        origination_fees=[1000, 0],
        initial_cash=0,
        period_days=30,
    ).build()
    assert cf["cff"][0] == pytest.approx(99_000)
    assert cf["cff"][1] == pytest.approx(-8_000)
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `pytest tests/unit/test_cashflow.py -v`
Expected: ImportError.

- [ ] **Step 3: Append to statements.py**

```python
@dataclass
class CashFlowBuilder:
    net_income: list[float]
    depreciation: list[float]
    revenue: list[float]
    cogs: list[float]
    dso_days: int
    dpo_days: int
    capex: list[float]
    funding_drawdowns: list[float]
    debt_drawdowns: list[float]
    debt_principal_repaid: list[float]
    origination_fees: list[float]
    initial_cash: float
    period_days: int  # 30 monthly / 91 quarterly / 365 annual approx

    def build(self) -> dict[str, list[float]]:
        n = len(self.net_income)
        # AR/AP balances
        ar = [self.revenue[t] * self.dso_days / self.period_days for t in range(n)]
        ap = [self.cogs[t] * self.dpo_days / self.period_days for t in range(n)]
        delta_ar = [ar[t] - (ar[t - 1] if t > 0 else 0) for t in range(n)]
        delta_ap = [ap[t] - (ap[t - 1] if t > 0 else 0) for t in range(n)]

        cfo = [
            self.net_income[t] + self.depreciation[t] - delta_ar[t] + delta_ap[t]
            for t in range(n)
        ]
        cfi = [-self.capex[t] for t in range(n)]
        cff = [
            self.funding_drawdowns[t]
            + self.debt_drawdowns[t]
            - self.debt_principal_repaid[t]
            - self.origination_fees[t]
            for t in range(n)
        ]

        cash = [0.0] * n
        cash[0] = self.initial_cash + cfo[0] + cfi[0] + cff[0]
        for t in range(1, n):
            cash[t] = cash[t - 1] + cfo[t] + cfi[t] + cff[t]

        return {
            "delta_ar": delta_ar,
            "delta_ap": delta_ap,
            "cfo": cfo,
            "cfi": cfi,
            "cff": cff,
            "cash": cash,
            "ar_balance": ar,
            "ap_balance": ap,
        }
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `pytest tests/unit/test_cashflow.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/asset_finance_modeler/core/statements.py tests/unit/test_cashflow.py
git commit -m "feat(core): CashFlowBuilder with indirect method and working capital deltas"
```

---

### Task 15: Balance + Unit economics + Runway

**Files:**
- Modify: `src/asset_finance_modeler/core/statements.py`
- Create: `tests/unit/test_balance_unit_runway.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_balance_unit_runway.py`:
```python
import math

import pytest

from asset_finance_modeler.core.statements import (
    BalanceBuilder,
    compute_runway,
    compute_unit_economics,
)


def test_balance_identity_holds():
    bal = BalanceBuilder(
        cash=[100, 150],
        ar_balance=[20, 30],
        fixed_assets_net=[10, 8],
        debt_outstanding=[50, 45],
        ap_balance=[15, 18],
        equity_initial=65,
    ).build()
    # Equity[0] = Assets - Liabilities = (100+20+10) - (50+15) = 65
    assert bal["equity"][0] == pytest.approx(65)
    # Check identity
    for t in range(2):
        assets = bal["total_assets"][t]
        liab = bal["total_liabilities"][t]
        eq = bal["equity"][t]
        assert assets == pytest.approx(liab + eq)


def test_unit_economics_basic():
    metrics = compute_unit_economics(
        revenue=[1000, 1100, 1200, 1300, 1400, 1500, 1600, 1700, 1800, 1900, 2000, 2100],
        cogs=[300, 330, 360, 390, 420, 450, 480, 510, 540, 570, 600, 630],
        cac_spend=[400, 400, 400, 400, 400, 400, 400, 400, 400, 400, 400, 400],
        active_customers=[10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21],
        new_customers=[2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
        monthly_churn=0.02,
        periods_per_year=12,
    )
    # ARPU = revenue/active_customers ~ 100 in period 0
    assert metrics["arpu"][0] == pytest.approx(100.0)
    # Gross margin period 0 = (1000-300)/1000 = 0.7
    assert metrics["gross_margin"][0] == pytest.approx(0.7)
    # CAC period 0 = 400/2 = 200
    assert metrics["cac"][0] == pytest.approx(200.0)
    # LTV = ARPU * GM / churn = 100*0.7/0.02 = 3500
    assert metrics["ltv"][0] == pytest.approx(3500.0)
    # LTV/CAC = 17.5
    assert metrics["ltv_cac"][0] == pytest.approx(17.5)


def test_runway_until_cash_zero():
    assert compute_runway([100, 80, 60, 40, 20, -10]) == 5
    assert compute_runway([100, 90, 80]) == math.inf
    assert compute_runway([-10]) == 0
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `pytest tests/unit/test_balance_unit_runway.py -v`
Expected: ImportError.

- [ ] **Step 3: Append to statements.py**

```python
import math


@dataclass
class BalanceBuilder:
    cash: list[float]
    ar_balance: list[float]
    fixed_assets_net: list[float]
    debt_outstanding: list[float]
    ap_balance: list[float]
    equity_initial: float

    def build(self) -> dict[str, list[float]]:
        n = len(self.cash)
        total_assets = [
            self.cash[t] + self.ar_balance[t] + self.fixed_assets_net[t]
            for t in range(n)
        ]
        total_liabilities = [self.debt_outstanding[t] + self.ap_balance[t] for t in range(n)]
        equity = [total_assets[t] - total_liabilities[t] for t in range(n)]
        return {
            "cash": list(self.cash),
            "ar": list(self.ar_balance),
            "fixed_assets_net": list(self.fixed_assets_net),
            "total_assets": total_assets,
            "debt": list(self.debt_outstanding),
            "ap": list(self.ap_balance),
            "total_liabilities": total_liabilities,
            "equity": equity,
        }


def compute_unit_economics(
    revenue: list[float],
    cogs: list[float],
    cac_spend: list[float],
    active_customers: list[float],
    new_customers: list[float],
    monthly_churn: float,
    periods_per_year: int,
) -> dict[str, list[float]]:
    n = len(revenue)
    arpu = [revenue[t] / active_customers[t] if active_customers[t] > 0 else 0 for t in range(n)]
    gross_margin = [(revenue[t] - cogs[t]) / revenue[t] if revenue[t] > 0 else 0 for t in range(n)]
    cac = [cac_spend[t] / new_customers[t] if new_customers[t] > 0 else 0 for t in range(n)]
    # LTV assumes monthly grain regardless — we approximate as ARPU*GM/churn (rule of thumb)
    ltv = [
        (arpu[t] * gross_margin[t]) / monthly_churn if monthly_churn > 0 else math.inf
        for t in range(n)
    ]
    ltv_cac = [ltv[t] / cac[t] if cac[t] > 0 else math.inf for t in range(n)]
    payback = [
        cac[t] / (arpu[t] * gross_margin[t]) if arpu[t] * gross_margin[t] > 0 else math.inf
        for t in range(n)
    ]
    return {
        "arpu": arpu,
        "gross_margin": gross_margin,
        "cac": cac,
        "ltv": ltv,
        "ltv_cac": ltv_cac,
        "payback_months": payback,
    }


def compute_runway(cash_series: list[float]) -> float:
    for t, c in enumerate(cash_series):
        if c < 0:
            return float(t)
    return math.inf
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `pytest tests/unit/test_balance_unit_runway.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/asset_finance_modeler/core/statements.py tests/unit/test_balance_unit_runway.py
git commit -m "feat(core): BalanceBuilder + unit economics + runway computation"
```

---

### Task 16: Valuation engine (DCF + sensitivity grid)

**Files:**
- Create: `src/asset_finance_modeler/core/valuation.py`
- Create: `tests/unit/test_valuation.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_valuation.py`:
```python
import math

import pytest

from asset_finance_modeler.core.valuation import (
    compute_dcf,
    compute_sensitivity_grid,
)


def test_dcf_gordon_simple():
    # FCF = 100 each year for 5 years, WACC 10%, g 2%
    # Annual periodicity (periods_per_year=1)
    result = compute_dcf(
        fcf_series=[100] * 5,
        wacc_annual=0.10,
        terminal_growth=0.02,
        periods_per_year=1,
        terminal_method="gordon",
    )
    # PV of FCF Y1..Y5 + terminal at end of Y5
    # PV1=100/1.1 ~= 90.91, etc.
    expected_pv = sum(100 / (1.1 ** t) for t in range(1, 6))
    terminal = 100 * 1.02 / (0.10 - 0.02)  # = 1275
    pv_terminal = terminal / (1.1 ** 5)
    assert result["pv_explicit"] == pytest.approx(expected_pv, rel=1e-3)
    assert result["pv_terminal"] == pytest.approx(pv_terminal, rel=1e-3)
    assert result["enterprise_value"] == pytest.approx(expected_pv + pv_terminal, rel=1e-3)


def test_dcf_exit_multiple_terminal():
    result = compute_dcf(
        fcf_series=[100, 200, 300, 400, 500],
        wacc_annual=0.20,
        terminal_growth=0,
        periods_per_year=1,
        terminal_method="exit_multiple",
        exit_arr=2000,
        exit_multiple_arr=6,
    )
    # Terminal = 2000 * 6 = 12000, discounted 5 years at 20%
    expected_terminal = 12000 / (1.20 ** 5)
    assert result["pv_terminal"] == pytest.approx(expected_terminal, rel=1e-3)


def test_dcf_handles_negative_growth():
    result = compute_dcf(
        fcf_series=[100, 100, 100],
        wacc_annual=0.10,
        terminal_growth=-0.01,
        periods_per_year=1,
        terminal_method="gordon",
    )
    assert result["enterprise_value"] > 0


def test_dcf_gordon_invalid_when_wacc_le_g():
    with pytest.raises(ValueError):
        compute_dcf(
            fcf_series=[100],
            wacc_annual=0.05,
            terminal_growth=0.10,
            periods_per_year=1,
            terminal_method="gordon",
        )


def test_sensitivity_grid_2d():
    grid = compute_sensitivity_grid(
        fcf_series=[100] * 5,
        wacc_values=[0.10, 0.15],
        growth_values=[0.02, 0.03],
        periods_per_year=1,
        terminal_method="gordon",
    )
    # 2x2 grid of EV values
    assert len(grid) == 2
    assert len(grid[0]) == 2
    # Lower WACC => higher EV
    assert grid[0][0] > grid[1][0]
    # Higher growth => higher EV (Gordon)
    assert grid[0][1] > grid[0][0]
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `pytest tests/unit/test_valuation.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement valuation**

`src/asset_finance_modeler/core/valuation.py`:
```python
from typing import Literal


def compute_dcf(
    fcf_series: list[float],
    wacc_annual: float,
    terminal_growth: float,
    periods_per_year: int,
    terminal_method: Literal["gordon", "exit_multiple"] = "gordon",
    exit_arr: float | None = None,
    exit_multiple_arr: float | None = None,
    exit_ebitda: float | None = None,
    exit_multiple_ebitda: float | None = None,
) -> dict[str, float]:
    n = len(fcf_series)
    if n == 0:
        raise ValueError("fcf_series must be non-empty")
    period_rate = (1 + wacc_annual) ** (1 / periods_per_year) - 1

    pv_explicit = 0.0
    for t, fcf in enumerate(fcf_series, start=1):
        pv_explicit += fcf / ((1 + period_rate) ** t)

    if terminal_method == "gordon":
        if wacc_annual <= terminal_growth:
            raise ValueError("Gordon requires wacc > terminal_growth")
        # Convert annual growth to per-period
        period_growth = (1 + terminal_growth) ** (1 / periods_per_year) - 1
        fcf_terminal_next = fcf_series[-1] * (1 + period_growth)
        terminal_value = fcf_terminal_next / (period_rate - period_growth)
    elif terminal_method == "exit_multiple":
        if exit_arr is not None and exit_multiple_arr is not None:
            terminal_value = exit_arr * exit_multiple_arr
        elif exit_ebitda is not None and exit_multiple_ebitda is not None:
            terminal_value = exit_ebitda * exit_multiple_ebitda
        else:
            raise ValueError("exit_multiple needs exit_arr+exit_multiple_arr or exit_ebitda+exit_multiple_ebitda")
    else:
        raise ValueError(f"Unknown terminal_method: {terminal_method}")

    pv_terminal = terminal_value / ((1 + period_rate) ** n)
    enterprise_value = pv_explicit + pv_terminal

    return {
        "pv_explicit": pv_explicit,
        "terminal_value": terminal_value,
        "pv_terminal": pv_terminal,
        "enterprise_value": enterprise_value,
    }


def compute_sensitivity_grid(
    fcf_series: list[float],
    wacc_values: list[float],
    growth_values: list[float],
    periods_per_year: int,
    terminal_method: Literal["gordon", "exit_multiple"] = "gordon",
    exit_arr: float | None = None,
    exit_multiple_arr: float | None = None,
) -> list[list[float]]:
    grid: list[list[float]] = []
    for wacc in wacc_values:
        row: list[float] = []
        for g in growth_values:
            try:
                ev = compute_dcf(
                    fcf_series=fcf_series,
                    wacc_annual=wacc,
                    terminal_growth=g,
                    periods_per_year=periods_per_year,
                    terminal_method=terminal_method,
                    exit_arr=exit_arr,
                    exit_multiple_arr=exit_multiple_arr,
                )["enterprise_value"]
            except ValueError:
                ev = float("nan")
            row.append(ev)
        grid.append(row)
    return grid
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `pytest tests/unit/test_valuation.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/asset_finance_modeler/core/valuation.py tests/unit/test_valuation.py
git commit -m "feat(core): DCF (Gordon + exit multiple) + 2D sensitivity grid"
```

---

### Task 17: Debt metrics (DSCR, ICR, leverage)

**Files:**
- Modify: `src/asset_finance_modeler/core/statements.py`
- Create: `tests/unit/test_debt_metrics.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_debt_metrics.py`:
```python
import math

import pytest

from asset_finance_modeler.core.statements import compute_debt_metrics


def test_dscr():
    m = compute_debt_metrics(
        ebitda=[500, 500],
        ebit=[400, 400],
        interest_expense=[50, 50],
        principal_repaid=[100, 100],
        debt_outstanding=[1000, 900],
    )
    # DSCR = EBITDA / (interest + principal) = 500/150 ~= 3.33
    assert m["dscr"][0] == pytest.approx(500 / 150)
    # ICR = EBIT / interest = 400/50 = 8
    assert m["icr"][0] == pytest.approx(8)
    # Leverage = debt / EBITDA = 1000/500 = 2
    assert m["leverage"][0] == pytest.approx(2)


def test_dscr_no_debt_service_returns_inf():
    m = compute_debt_metrics(
        ebitda=[100],
        ebit=[100],
        interest_expense=[0],
        principal_repaid=[0],
        debt_outstanding=[0],
    )
    assert m["dscr"][0] == math.inf
    assert m["icr"][0] == math.inf
    assert m["leverage"][0] == 0
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `pytest tests/unit/test_debt_metrics.py -v`
Expected: ImportError.

- [ ] **Step 3: Append to statements.py**

```python
def compute_debt_metrics(
    ebitda: list[float],
    ebit: list[float],
    interest_expense: list[float],
    principal_repaid: list[float],
    debt_outstanding: list[float],
) -> dict[str, list[float]]:
    n = len(ebitda)
    dscr: list[float] = []
    icr: list[float] = []
    leverage: list[float] = []
    for t in range(n):
        debt_service = interest_expense[t] + principal_repaid[t]
        dscr.append(ebitda[t] / debt_service if debt_service > 0 else math.inf)
        icr.append(ebit[t] / interest_expense[t] if interest_expense[t] > 0 else math.inf)
        leverage.append(debt_outstanding[t] / ebitda[t] if ebitda[t] > 0 else 0)
    return {"dscr": dscr, "icr": icr, "leverage": leverage}
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `pytest tests/unit/test_debt_metrics.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/asset_finance_modeler/core/statements.py tests/unit/test_debt_metrics.py
git commit -m "feat(core): debt metrics (DSCR, ICR, leverage)"
```

---

### Task 18: CapEx engine + depreciation schedule

**Files:**
- Modify: `src/asset_finance_modeler/assets/saas/engines.py`
- Create: `tests/unit/test_capex_engine.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_capex_engine.py`:
```python
import pytest

from asset_finance_modeler.assets.saas.engines import CapExEngine
from asset_finance_modeler.assets.saas.schema import CapExItem


def test_capex_no_items():
    eng = CapExEngine(items=[], periods=12, periods_per_year=12)
    out = eng.compute()
    assert out["capex_spend"] == [0] * 12
    assert out["depreciation"] == [0] * 12


def test_capex_single_laptop_fleet():
    item = CapExItem(name="laptops", amount=12_000, period=0, depreciation_years=3)
    eng = CapExEngine(items=[item], periods=48, periods_per_year=12)
    out = eng.compute()
    # depreciation_per_period = 12000 / 36 = 333.33 over 36 months
    assert out["capex_spend"][0] == 12_000
    assert out["depreciation"][0] == pytest.approx(12_000 / 36)
    assert out["depreciation"][35] == pytest.approx(12_000 / 36)
    assert out["depreciation"][36] == pytest.approx(0)
    # Net fixed assets period 0: 12000 - 333.33 = 11666.67
    assert out["fixed_assets_net"][0] == pytest.approx(12_000 - 12_000 / 36)
    # Fully depreciated by period 35
    assert out["fixed_assets_net"][35] == pytest.approx(0, abs=0.01)
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `pytest tests/unit/test_capex_engine.py -v`
Expected: ImportError.

- [ ] **Step 3: Append to engines.py**

```python
from .schema import CapExItem


@dataclass
class CapExEngine:
    items: list[CapExItem]
    periods: int
    periods_per_year: int

    def compute(self) -> dict[str, list[float]]:
        capex = [0.0] * self.periods
        depreciation = [0.0] * self.periods
        fixed_net = [0.0] * self.periods

        for item in self.items:
            if item.period >= self.periods:
                continue
            capex[item.period] += item.amount
            life_periods = item.depreciation_years * self.periods_per_year
            per_period_dep = item.amount / life_periods
            for t in range(item.period, min(item.period + life_periods, self.periods)):
                depreciation[t] += per_period_dep

        # Fixed assets net = cumulative capex - cumulative depreciation
        cum_capex = 0.0
        cum_dep = 0.0
        for t in range(self.periods):
            cum_capex += capex[t]
            cum_dep += depreciation[t]
            fixed_net[t] = cum_capex - cum_dep

        return {
            "capex_spend": capex,
            "depreciation": depreciation,
            "fixed_assets_net": fixed_net,
        }
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `pytest tests/unit/test_capex_engine.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/asset_finance_modeler/assets/saas/engines.py tests/unit/test_capex_engine.py
git commit -m "feat(saas): CapExEngine with straight-line depreciation"
```

---

### Task 19: SaasModel orchestrator

**Files:**
- Create: `src/asset_finance_modeler/assets/saas/model.py`
- Create: `tests/unit/test_saas_model.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_saas_model.py`:
```python
from datetime import date

import pytest

from asset_finance_modeler.assets.saas.model import ModelResults, SaasModel
from asset_finance_modeler.assets.saas.schema import (
    AcquisitionConfig,
    COGSConfig,
    CapitalConfig,
    DebtInstrument,
    ExternalDataConfig,
    HorizonConfig,
    ModelMeta,
    OpexConfig,
    PerActiveCustomerCosts,
    PerActiveUnitCosts,
    PricingConfig,
    RetentionConfig,
    RevenueConfig,
    RevenueSource,
    SaasModelConfig,
    TaxesConfig,
    TeamRole,
    ValuationConfig,
    WorkingCapital,
)


def _minimal_config(periods=24, with_debt=False) -> SaasModelConfig:
    debt = []
    if with_debt:
        debt = [DebtInstrument(
            name="enisa", principal=100_000, drawdown_period=0,
            interest_rate_annual=0.05, term_months=24, amortization="french",
        )]
    return SaasModelConfig(
        meta=ModelMeta(
            name="test",
            horizon=HorizonConfig(periods=periods, frequency="M"),
            start_date=date(2026, 1, 1),
            initial_cash=50_000,
        ),
        revenue=RevenueConfig(sources=[RevenueSource(
            name="subs",
            pricing=PricingConfig(per_unit_per_period=300, setup_one_time=1000),
            acquisition=AcquisitionConfig(
                new_units_per_period=5, avg_units_per_customer=2.5, cac_per_customer=800,
            ),
            retention=RetentionConfig(monthly_churn_rate=0.02),
        )]),
        cost_of_revenue=COGSConfig(
            per_active_unit=PerActiveUnitCosts(llm_tokens=[], infra_eur=5.0),
            per_active_customer=PerActiveCustomerCosts(support_eur=10),
        ),
        operating_expenses=OpexConfig(
            team=[TeamRole(role="founder", monthly_cost=4000, headcount=2)],
            infra_fixed_eur=500,
            marketing_eur=1000,
        ),
        capital=CapitalConfig(working_capital=WorkingCapital(days_sales_outstanding=30, days_payable_outstanding=30), debt=debt),
        taxes=TaxesConfig(),
        valuation=ValuationConfig(discount_rate_annual=0.20),
        external_data=ExternalDataConfig(),
    )


def test_saas_model_run_returns_results():
    cfg = _minimal_config(periods=12)
    results = SaasModel(cfg).run()
    assert isinstance(results, ModelResults)
    assert len(results.pnl["revenue"]) == 12
    assert len(results.cashflow["cash"]) == 12
    assert "ltv_cac" in results.unit_econ
    assert "enterprise_value" in results.valuation
    assert "revenue_y1" in results.summary


def test_saas_model_revenue_positive():
    cfg = _minimal_config(periods=12)
    results = SaasModel(cfg).run()
    assert results.pnl["revenue"][0] > 0
    assert results.pnl["revenue"][11] > results.pnl["revenue"][0]


def test_saas_model_with_debt_has_interest_expense():
    cfg = _minimal_config(periods=24, with_debt=True)
    results = SaasModel(cfg).run()
    assert results.pnl["interest_expense"][0] > 0
    assert results.debt_metrics["leverage"][0] >= 0


def test_saas_model_runway_metric_present():
    cfg = _minimal_config(periods=12)
    results = SaasModel(cfg).run()
    assert "runway_months" in results.summary
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `pytest tests/unit/test_saas_model.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement SaasModel**

`src/asset_finance_modeler/assets/saas/model.py`:
```python
from dataclasses import dataclass, field

from asset_finance_modeler.core.statements import (
    BalanceBuilder,
    CashFlowBuilder,
    PnLBuilder,
    compute_debt_metrics,
    compute_runway,
    compute_unit_economics,
)
from asset_finance_modeler.core.time_grid import TimeGrid
from asset_finance_modeler.core.valuation import (
    compute_dcf,
    compute_sensitivity_grid,
)

from .engines import (
    CapExEngine,
    COGSEngine,
    CohortRevenueEngine,
    DebtEngine,
    OpexEngine,
)
from .schema import SaasModelConfig

_PERIOD_DAYS = {"M": 30, "Q": 91, "Y": 365}


@dataclass
class ModelResults:
    pnl: dict[str, list[float]]
    cashflow: dict[str, list[float]]
    balance: dict[str, list[float]]
    unit_econ: dict[str, list[float]]
    valuation: dict[str, float]
    sensitivity: list[list[float]] | None
    debt_metrics: dict[str, list[float]]
    revenue_breakdown: dict[str, list[float]]
    summary: dict[str, float | int]
    inputs_resolved: dict = field(default_factory=dict)


@dataclass
class SaasModel:
    config: SaasModelConfig

    def run(self) -> ModelResults:
        cfg = self.config
        n = cfg.meta.horizon.periods
        ppy = TimeGrid(periods=n, frequency=cfg.meta.horizon.frequency, start_date=cfg.meta.start_date).periods_per_year
        period_days = _PERIOD_DAYS[cfg.meta.horizon.frequency]

        # 1. Revenue
        rev = CohortRevenueEngine(cfg.revenue.sources, periods=n).compute()

        # 2. COGS
        cogs = COGSEngine(
            cfg.cost_of_revenue,
            active_units=rev["active_units"],
            active_customers=rev["active_customers"],
        ).compute()

        # 3. CapEx + depreciation
        capex_eng = CapExEngine(cfg.capital.capex_schedule, periods=n, periods_per_year=ppy).compute()

        # 4. Opex (team + buckets)
        opex = OpexEngine(cfg.operating_expenses, periods=n).compute()

        # Marketing + CAC spend together for unit economics
        cac_spend = [
            rev["new_customers"][t] * cfg.revenue.sources[0].acquisition.cac_per_customer
            for t in range(n)
        ]

        # 5. Debt
        debt = DebtEngine(cfg.capital.debt, periods=n, periods_per_year=ppy).compute()

        # 6. P&L
        pnl = PnLBuilder(
            revenue=rev["total_revenue"],
            cogs=cogs["total_cogs"],
            opex=opex["total_opex"],
            depreciation=capex_eng["depreciation"],
            interest_expense=debt["interest_expense"],
            corporate_tax_rate=cfg.taxes.corporate_income_tax_rate,
            carryforward_enabled=cfg.taxes.tax_loss_carryforward,
        ).build()

        # 7. Cash Flow
        funding_drawdowns = [0.0] * n
        for fr in cfg.capital.funding_rounds:
            if fr.period < n:
                funding_drawdowns[fr.period] += fr.amount

        cf = CashFlowBuilder(
            net_income=pnl["net_income"],
            depreciation=capex_eng["depreciation"],
            revenue=pnl["revenue"],
            cogs=pnl["cogs"],
            dso_days=cfg.capital.working_capital.days_sales_outstanding,
            dpo_days=cfg.capital.working_capital.days_payable_outstanding,
            capex=capex_eng["capex_spend"],
            funding_drawdowns=funding_drawdowns,
            debt_drawdowns=debt["drawdowns"],
            debt_principal_repaid=debt["principal_repaid"],
            origination_fees=debt["origination_fees"],
            initial_cash=cfg.meta.initial_cash,
            period_days=period_days,
        ).build()

        # 8. Balance
        balance = BalanceBuilder(
            cash=cf["cash"],
            ar_balance=cf["ar_balance"],
            fixed_assets_net=capex_eng["fixed_assets_net"],
            debt_outstanding=debt["balance_outstanding"],
            ap_balance=cf["ap_balance"],
            equity_initial=cfg.meta.initial_cash,
        ).build()

        # 9. Unit econ
        unit_econ = compute_unit_economics(
            revenue=pnl["revenue"],
            cogs=pnl["cogs"],
            cac_spend=cac_spend,
            active_customers=rev["active_customers"],
            new_customers=rev["new_customers"],
            monthly_churn=cfg.revenue.sources[0].retention.monthly_churn_rate,
            periods_per_year=ppy,
        )

        # 10. Debt metrics
        debt_metrics = compute_debt_metrics(
            ebitda=pnl["ebitda"],
            ebit=pnl["ebit"],
            interest_expense=pnl["interest_expense"],
            principal_repaid=debt["principal_repaid"],
            debt_outstanding=debt["balance_outstanding"],
        )

        # 11. Valuation — convert FCF series to annual
        fcf_period = [cf["cfo"][t] + cf["cfi"][t] for t in range(n)]
        years = n // ppy
        fcf_annual = [sum(fcf_period[y * ppy:(y + 1) * ppy]) for y in range(years)] if years > 0 else fcf_period

        try:
            val = compute_dcf(
                fcf_series=fcf_annual,
                wacc_annual=cfg.valuation.discount_rate_annual,
                terminal_growth=cfg.valuation.terminal_growth_rate,
                periods_per_year=1,
                terminal_method=cfg.valuation.terminal_method,
                exit_arr=pnl["revenue"][-1] * ppy if cfg.valuation.exit_multiple_arr else None,
                exit_multiple_arr=cfg.valuation.exit_multiple_arr,
            )
        except ValueError:
            val = {"pv_explicit": 0.0, "terminal_value": 0.0, "pv_terminal": 0.0, "enterprise_value": 0.0}

        sens = None
        if cfg.valuation.sensitivity_grid:
            sens = compute_sensitivity_grid(
                fcf_series=fcf_annual,
                wacc_values=cfg.valuation.sensitivity_grid.wacc,
                growth_values=cfg.valuation.sensitivity_grid.growth,
                periods_per_year=1,
                terminal_method=cfg.valuation.terminal_method,
            )

        runway = compute_runway(cf["cash"])

        # 12. Summary
        annual_revenue_y1 = sum(pnl["revenue"][:ppy]) if n >= ppy else sum(pnl["revenue"])
        ebitda_margin_last = (
            pnl["ebitda"][-1] / pnl["revenue"][-1] if pnl["revenue"][-1] > 0 else 0
        )
        summary: dict[str, float | int] = {
            "revenue_y1": annual_revenue_y1,
            "revenue_end_period": pnl["revenue"][-1],
            "ebitda_margin_end": ebitda_margin_last,
            "active_customers_end": rev["active_customers"][-1],
            "active_units_end": rev["active_units"][-1],
            "cash_end": cf["cash"][-1],
            "runway_months": runway if runway != float("inf") else -1,
            "ltv_cac_end": unit_econ["ltv_cac"][-1] if unit_econ["ltv_cac"][-1] != float("inf") else -1,
            "enterprise_value": val["enterprise_value"],
        }

        return ModelResults(
            pnl=pnl,
            cashflow=cf,
            balance=balance,
            unit_econ=unit_econ,
            valuation=val,
            sensitivity=sens,
            debt_metrics=debt_metrics,
            revenue_breakdown=rev,
            summary=summary,
            inputs_resolved=cfg.model_dump(mode="json"),
        )
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `pytest tests/unit/test_saas_model.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/asset_finance_modeler/assets/saas/model.py tests/unit/test_saas_model.py
git commit -m "feat(saas): SaasModel orchestrator wiring all engines into ModelResults"
```

---

### Task 20: Gestnova baseline preset + golden test

**Files:**
- Create: `src/asset_finance_modeler/assets/saas/presets/gestnova.yaml`
- Create: `src/asset_finance_modeler/assets/saas/presets/__init__.py`
- Create: `src/asset_finance_modeler/assets/saas/loader.py`
- Create: `tests/golden/__init__.py`
- Create: `tests/golden/test_gestnova_preset.py`

- [ ] **Step 1: Create preset file**

`src/asset_finance_modeler/assets/saas/presets/__init__.py`: empty file.

`src/asset_finance_modeler/assets/saas/presets/gestnova.yaml`:
```yaml
meta:
  name: gestnova
  base_currency: EUR
  inflation_annual: 0.025
  horizon:
    periods: 60
    frequency: M
  start_date: "2026-05-01"
  initial_cash: 50000
  schema_version: 1

revenue:
  sources:
    - name: agent_subscriptions
      pricing:
        per_unit_per_period: 300
        setup_one_time: 1000
        price_escalation_annual: 0.03
      acquisition:
        new_units_per_period: [2, 3, 4, 5, 6, 8, 10, 12, 14, 16, 18, 20]
        avg_units_per_customer: 2.5
        cac_per_customer: 800
        cac_payback_target_months: 12
      retention:
        monthly_churn_rate: 0.02
        gross_revenue_retention: 0.95
        expansion_revenue_pct: 0

cost_of_revenue:
  per_active_unit:
    llm_tokens:
      - model: sonnet-4-7
        eur_per_million_input: 3.0
        eur_per_million_output: 15.0
        avg_tokens_in_per_month: 800000
        avg_tokens_out_per_month: 200000
      - model: haiku-4-5
        eur_per_million_input: 0.8
        eur_per_million_output: 4.0
        avg_tokens_in_per_month: 1500000
        avg_tokens_out_per_month: 400000
    stt:
      provider: deepgram
      eur_per_minute: 0.0043
      monthly_usage: 200
    tts:
      provider: cartesia
      eur_per_million_chars: 25
      monthly_usage: 50000
    twilio:
      whatsapp_eur_per_msg: 0.005
      voice_eur_per_min: 0.012
      msgs_per_month: 600
      min_per_month: 80
    infra_eur: 2
  per_active_customer:
    support_eur: 15
    onboarding_one_time_eur: 0

operating_expenses:
  team:
    - role: founders
      monthly_cost: 4000
      headcount: 3
    - role: engineer
      monthly_cost: 5500
      headcount_schedule: [0, 0, 0, 1, 1, 1, 2, 2, 2, 2, 2, 2]
      start_period: 0
  infra_fixed_eur: 1200
  marketing_eur: 2000
  legal_admin_eur: 800
  other_eur: 500

capital:
  working_capital:
    days_sales_outstanding: 45
    days_payable_outstanding: 30
    days_inventory: 0
  capex_schedule: []
  funding_rounds:
    - period: 6
      amount: 250000
      type: pre_seed
      dilution: 0.15
  debt: []

taxes:
  corporate_income_tax_rate: 0.25
  vat_rate: 0.21
  payroll_taxes_pct: 0.30
  r_and_d_deduction_pct: 0.12
  tax_loss_carryforward: true

valuation:
  discount_rate_annual: 0.20
  terminal_growth_rate: 0.025
  terminal_method: gordon
  exit_multiple_arr: 6
  sensitivity_grid:
    wacc: [0.15, 0.18, 0.20, 0.22, 0.25]
    growth: [0.015, 0.02, 0.025, 0.03]

external_data:
  benchmarks: {}
```

- [ ] **Step 2: Implement loader**

`src/asset_finance_modeler/assets/saas/loader.py`:
```python
from importlib.resources import files
from pathlib import Path

import yaml

from .schema import SaasModelConfig


def load_preset(name: str) -> SaasModelConfig:
    preset_path = files("asset_finance_modeler.assets.saas.presets") / f"{name}.yaml"
    with preset_path.open() as f:
        data = yaml.safe_load(f)
    return SaasModelConfig.model_validate(data)


def load_yaml(path: Path | str) -> SaasModelConfig:
    with open(path) as f:
        data = yaml.safe_load(f)
    return SaasModelConfig.model_validate(data)
```

- [ ] **Step 3: Write failing golden test**

`tests/golden/__init__.py`: empty file.

`tests/golden/test_gestnova_preset.py`:
```python
import pytest

from asset_finance_modeler.assets.saas.loader import load_preset
from asset_finance_modeler.assets.saas.model import SaasModel


def test_gestnova_preset_loads():
    cfg = load_preset("gestnova")
    assert cfg.meta.name == "gestnova"
    assert cfg.meta.horizon.periods == 60


def test_gestnova_preset_runs_no_errors():
    cfg = load_preset("gestnova")
    results = SaasModel(cfg).run()
    assert len(results.pnl["revenue"]) == 60
    assert results.summary["revenue_y1"] > 0


def test_gestnova_preset_summary_shape(snapshot):
    cfg = load_preset("gestnova")
    results = SaasModel(cfg).run()
    rounded_summary = {
        k: (round(v, 2) if isinstance(v, float) else v)
        for k, v in results.summary.items()
    }
    snapshot.assert_match(str(rounded_summary), "gestnova_summary.txt")


def test_gestnova_balance_identity_holds():
    cfg = load_preset("gestnova")
    results = SaasModel(cfg).run()
    for t in range(len(results.balance["total_assets"])):
        assets = results.balance["total_assets"][t]
        liab = results.balance["total_liabilities"][t]
        eq = results.balance["equity"][t]
        assert assets == pytest.approx(liab + eq, abs=0.01)
```

- [ ] **Step 4: Run tests, verify they fail / generate golden**

First run will create the snapshot:
```bash
pytest tests/golden/test_gestnova_preset.py -v --snapshot-update
```

Verify the generated `tests/golden/snapshots/snap_test_gestnova_preset/gestnova_summary.txt` looks reasonable (manually inspect numbers — revenue Y1 should be in the thousands, runway should be positive, etc.).

Then run without `--snapshot-update`:
```bash
pytest tests/golden/test_gestnova_preset.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/asset_finance_modeler/assets/saas/loader.py \
        src/asset_finance_modeler/assets/saas/presets/ \
        tests/golden/
git commit -m "feat(saas): Gestnova baseline preset + YAML loader + golden snapshot test"
```

---

### Task 21: Final sanity — full test suite + lint + types

**Files:** none (verification only)

- [ ] **Step 1: Run full test suite**

```bash
cd /Users/rikyizquierdo/Documents/New\ project/asset-finance-modeler
source .venv/bin/activate
pytest -v
```

Expected: all tests pass. Count should be ≥ 50 tests.

- [ ] **Step 2: Run ruff**

```bash
ruff check src/ tests/
```

Expected: zero issues. Fix any reported violations and re-commit.

- [ ] **Step 3: Run mypy**

```bash
mypy src/
```

Expected: zero errors. Fix any reported violations and re-commit.

- [ ] **Step 4: Verify package can be imported and used as library**

```bash
python -c "
from asset_finance_modeler.assets.saas.loader import load_preset
from asset_finance_modeler.assets.saas.model import SaasModel
cfg = load_preset('gestnova')
r = SaasModel(cfg).run()
print('Revenue Y1:', round(r.summary['revenue_y1'], 2))
print('Cash end:', round(r.summary['cash_end'], 2))
print('Runway:', r.summary['runway_months'])
print('EV:', round(r.summary['enterprise_value'], 2))
"
```

Expected: prints non-zero numbers without errors.

- [ ] **Step 5: Final commit (if anything was fixed in steps 2-3)**

```bash
git add -u
git commit -m "chore: lint and type fixes after full suite verification" || true
```

---

## End of Plan 1

After this plan, the library is fully functional as a pure Python module: load a YAML preset → run the model → inspect results. Plans 2 (scenarios + store + exports + CLI) and 3 (MCP server) build on this foundation.

**Estimated effort:** 6-8 hours of focused TDD work for an engineer with Python + pydantic + pandas experience.
