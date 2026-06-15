from dataclasses import dataclass
from typing import Literal


def expand_growth(value: float | list[float], periods: int) -> list[float]:
    if isinstance(value, (int, float)):
        return [float(value)] * periods
    if len(value) > periods:
        raise ValueError(f"List length {len(value)} > periods {periods}")
    if len(value) < periods:
        # Pad with last value (ramp-then-hold semantics)
        last = float(value[-1])
        return [float(v) for v in value] + [last] * (periods - len(value))
    return [float(v) for v in value]


@dataclass(frozen=True)
class CurvePhase:
    """A growth phase: `years` periods at `growth_pct` per-period compounding."""

    years: int
    growth_pct: float


def build_phased_curve(base: float, phases: list["CurvePhase"], periods: int) -> list[float]:
    """Build a value series from a base and phased compounding growth.

    Year 1 (index 0) = base. Growth steps INTO each year of a phase: a phase
    declared "N years at +g%" produces N compounding steps, so the value at the
    end of that phase (index N, when it is the first phase) is
    ``base * (1+g)**N``. The growth declared for the k-th year of a phase is
    applied when stepping from index k-1 to index k. Phases are consumed in
    order by their `years` span; if they run out before `periods`, the last
    phase's growth continues (ramp-then-hold semantics).
    """
    growth_by_period: list[float] = []
    for ph in phases:
        growth_by_period.extend([ph.growth_pct] * ph.years)
    if not growth_by_period:
        growth_by_period = [0.0]
    values: list[float] = []
    current = base
    for t in range(periods):
        if t > 0:
            # Step from t-1 to t uses the growth of the (t-1)-th declared year,
            # so the first phase-year's growth is not skipped (FIX 2).
            idx = t - 1
            g = growth_by_period[idx] if idx < len(growth_by_period) else growth_by_period[-1]
            current = current * (1.0 + g)
        values.append(current)
    return values


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
    idc_periods: int = 0
    deferral_periods: int = 0

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

        # Construction DEFERRAL (no IDC roll-up): the asset produces no cash
        # until COD, so amortization is deferred to COD on the FACE principal.
        # The construction-phase interest is assumed funded outside the debt
        # balance (equity / a dedicated IDC reserve), so the balance is NOT
        # grossed up. This is the treatment that reconciles with the validated
        # SVJ Excel (sub-DSCR ~1.14-1.31 over the operating years). Mutually
        # exclusive with idc_periods. ``deferral_periods == 0`` => legacy.
        for _ in range(self.deferral_periods):
            rows.append({
                "balance_start": balance,
                "interest": 0.0,
                "principal_payment": 0.0,
                "total_payment": 0.0,
                "balance_end": balance,
            })

        # Interest During Construction (IDC): standard project-finance treatment.
        # The debt is drawn at financial close but the asset produces no cash
        # until commercial operation (COD). During the ``idc_periods`` before
        # COD, interest is CAPITALIZED into the balance (no cash debt service)
        # rather than paid. Amortization below then runs on the grossed-up
        # balance starting at COD. ``idc_periods == 0`` => no construction phase,
        # behaviour is byte-identical to the legacy schedule.
        for _ in range(self.idc_periods):
            capitalized = balance * rate
            rows.append({
                "balance_start": balance,
                "interest": 0.0,
                "principal_payment": 0.0,
                "total_payment": 0.0,
                "balance_end": balance + capitalized,
            })
            balance += capitalized

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
