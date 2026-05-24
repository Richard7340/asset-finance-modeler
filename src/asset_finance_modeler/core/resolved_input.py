# src/asset_finance_modeler/core/resolved_input.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class ResolvedInput:
    field_path: str
    value: float | str | bool | int
    source: Literal["user", "benchmark", "preset", "default", "internet"]
    provenance: str
    confidence: float
    benchmark_id: str | None = field(default=None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_path": self.field_path,
            "value": self.value,
            "source": self.source,
            "provenance": self.provenance,
            "confidence": self.confidence,
            "benchmark_id": self.benchmark_id,
        }


class InsufficientDataError(Exception):
    def __init__(self, missing_fields: list[str]) -> None:
        self.missing_fields = missing_fields
        fields_str = ", ".join(missing_fields)
        super().__init__(
            f"Cannot run model: {len(missing_fields)} required input(s) missing: {fields_str}"
        )
