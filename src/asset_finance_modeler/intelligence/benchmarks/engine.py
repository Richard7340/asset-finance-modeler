# src/asset_finance_modeler/intelligence/benchmarks/engine.py
from __future__ import annotations

from dataclasses import dataclass

from asset_finance_modeler.intelligence.knowledge.loader import KBLoader
from asset_finance_modeler.intelligence.knowledge.schemas import BenchmarkEntry

_MIN_CONFIDENCE = 0.7


@dataclass
class BenchmarkResult:
    value: float
    source: str
    confidence: float
    unit: str
    methodology: str
    assumptions: list[str]
    source_url: str | None = None
    benchmark_id: str | None = None


class BenchmarkEngine:
    def __init__(self, loader: KBLoader) -> None:
        self._loader = loader

    def search(self, field: str, asset_type: str, region: str | None = None) -> BenchmarkResult | None:
        exact = self._loader.find_benchmark(field, asset_type, region)
        if exact and exact.confidence >= _MIN_CONFIDENCE:
            return self._to_result(exact)
        fallback = self._loader.find_benchmark(field, asset_type, None)
        if fallback and fallback.confidence >= _MIN_CONFIDENCE:
            return self._to_result(fallback)
        return None

    @staticmethod
    def _to_result(entry: BenchmarkEntry) -> BenchmarkResult:
        return BenchmarkResult(
            value=entry.value,
            source=entry.source,
            confidence=entry.confidence,
            unit=entry.unit,
            methodology=entry.methodology,
            assumptions=entry.assumptions,
            source_url=entry.source_url,
            benchmark_id=f"bm-{entry.field}-{entry.asset_type}-{entry.region or 'global'}",
        )
