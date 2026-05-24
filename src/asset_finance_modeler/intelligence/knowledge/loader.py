from __future__ import annotations

from importlib.resources import files

import yaml

from .schemas import (
    AssetIntent,
    BenchmarkEntry,
    ConceptEntry,
    QuestionTemplate,
    QuickStartPreset,
    ValidationRule,
)

_DATA_PKG = "asset_finance_modeler.intelligence.knowledge.data"


def _load_yaml_list(subpath: str) -> list[dict]:
    try:
        resource = files(_DATA_PKG) / subpath
        with resource.open() as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, TypeError):
        return []


def _load_yaml_dir(subdir: str) -> list[dict]:
    result: list[dict] = []
    try:
        pkg = files(_DATA_PKG) / subdir
        for item in pkg.iterdir():
            if str(item).endswith(".yaml"):
                with item.open() as f:
                    data = yaml.safe_load(f)
                if isinstance(data, list):
                    result.extend(data)
    except (FileNotFoundError, TypeError):
        pass
    return result


class KBLoader:
    def load_intents(self) -> list[AssetIntent]:
        raw = _load_yaml_list("intents/asset_recognition.yaml")
        return [AssetIntent.model_validate(r) for r in raw]

    def load_questions(self, asset_type: str) -> list[QuestionTemplate]:
        specific = _load_yaml_list(f"questions/{asset_type}.yaml")
        generic = _load_yaml_list("questions/generic.yaml")
        raw = specific + generic if specific else generic
        templates = [QuestionTemplate.model_validate(r) for r in raw]
        return sorted(templates, key=lambda q: q.order)

    def load_benchmarks(self) -> list[BenchmarkEntry]:
        raw = _load_yaml_dir("benchmarks")
        return [BenchmarkEntry.model_validate(r) for r in raw]

    def load_concepts(self) -> list[ConceptEntry]:
        raw = _load_yaml_dir("concepts")
        return [ConceptEntry.model_validate(r) for r in raw]

    def load_validations(self) -> list[ValidationRule]:
        raw = _load_yaml_list("validations/ranges.yaml")
        return [ValidationRule.model_validate(r) for r in raw]

    def load_quick_starts(self) -> list[QuickStartPreset]:
        raw = _load_yaml_list("presets/quick_start.yaml")
        return [QuickStartPreset.model_validate(r) for r in raw]

    def detect_asset_type(self, text: str) -> str | None:
        text_lower = text.lower()
        for intent in self.load_intents():
            for pattern in intent.patterns:
                if pattern.lower() in text_lower:
                    return intent.asset_type
        return None

    def find_benchmark(
        self, field: str, asset_type: str, region: str | None = None
    ) -> BenchmarkEntry | None:
        for bm in self.load_benchmarks():
            if bm.field == field and bm.asset_type == asset_type:
                if region is None or bm.region is None or bm.region == region:
                    return bm
        return None

    def get_validation(self, rule_ref: str) -> ValidationRule | None:
        for rule in self.load_validations():
            if rule.rule_id == rule_ref:
                return rule
        return None
