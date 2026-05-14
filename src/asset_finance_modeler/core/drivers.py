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
