from __future__ import annotations

from dataclasses import dataclass

from asset_finance_modeler.core.drivers import CurvePhase, build_phased_curve


@dataclass(frozen=True)
class Curve:
    """A projected value series attachable to any parameter (price, spread,
    ancillary, demand, cost…). Built from points, phases, growth, or library."""

    values: tuple[float, ...]
    name: str = ""
    source: str = ""

    @classmethod
    def from_points(cls, values: list[float], name: str = "", source: str = "") -> Curve:
        return cls(tuple(float(v) for v in values), name, source)

    @classmethod
    def from_phases(
        cls, base: float, phases: list[CurvePhase], periods: int,
        name: str = "", source: str = "",
    ) -> Curve:
        return cls(tuple(build_phased_curve(base, phases, periods)), name, source)

    @classmethod
    def from_growth(
        cls, base: float, rate: float, periods: int, name: str = "", source: str = "",
    ) -> Curve:
        return cls(tuple(base * (1.0 + rate) ** i for i in range(periods)), name, source)

    @classmethod
    def from_library(cls, name: str) -> Curve:
        # Lazy import: curve_library is added in a later task; importing it
        # at module load time would break until then.
        from asset_finance_modeler.core.curve_library import (  # type: ignore[import-not-found]
            load_curve,
        )
        result: Curve = load_curve(name)
        return result

    def at(self, period_index: int) -> float:
        if not self.values:
            return 0.0
        return self.values[min(period_index, len(self.values) - 1)]

    def to_list(self, periods: int) -> list[float]:
        return [self.at(i) for i in range(periods)]
