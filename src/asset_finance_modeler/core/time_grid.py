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
