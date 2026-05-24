# src/asset_finance_modeler/intelligence/knowledge/schemas.py
from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class BenchmarkEntry(BaseModel):
    field: str
    asset_type: str
    region: str | None = None
    value: float
    valid_from: date
    valid_to: date
    source: str
    confidence: float = Field(ge=0, le=1)
    source_url: str | None = None
    unit: str
    methodology: str
    assumptions: list[str] = Field(default_factory=list)
    unverified: bool = False


class ConceptEntry(BaseModel):
    id: str
    title: str
    content: str
    asset_types: list[str] = Field(default_factory=list)
    category: str = "general"
    tags: list[str] = Field(default_factory=list)


class QuestionOption(BaseModel):
    label: str
    value: float | str | bool | int


class QuestionTemplate(BaseModel):
    field_path: str
    question: str
    help_text: str = ""
    options: list[QuestionOption] = Field(default_factory=list)
    required: bool = True
    order: int = 0
    depends_on: str | None = None
    benchmark_key: str | None = None
    validation: str | None = None
    expert_only: bool = False
    group: str = "general"


class ValidationRule(BaseModel):
    field_path: str
    rule_id: str
    min_value: float | None = None
    max_value: float | None = None
    allowed_values: list[Any] | None = None
    message: str = ""


class QuickStartPreset(BaseModel):
    asset_type: str
    region: str | None = None
    size_bracket: list[float] | None = None
    defaults: dict[str, Any] = Field(default_factory=dict)


class AssetIntent(BaseModel):
    patterns: list[str]
    asset_type: str
