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
        if specific:
            raw = specific + generic
        elif asset_type not in ("generic", None, ""):
            raw = self._generate_universal_questions(asset_type) + generic
        else:
            raw = generic
        templates = [QuestionTemplate.model_validate(r) for r in raw]
        return sorted(templates, key=lambda q: q.order)

    @staticmethod
    def _generate_universal_questions(asset_type: str) -> list[dict]:
        """Generate standard financial modeling questions for any unknown asset type."""
        label = asset_type.replace("_", " ").title()
        return [
            {
                "field_path": "meta.horizon.periods",
                "question": f"¿A cuántos años quieres proyectar el modelo de {label}?",
                "help_text": "Horizonte del análisis financiero. Típico: 10-30 años según el activo.",
                "options": [
                    {"label": "10 años", "value": 120},
                    {"label": "20 años", "value": 240},
                    {"label": "25 años", "value": 300},
                    {"label": "30 años", "value": 360},
                ],
                "required": True, "order": 0, "group": "meta",
            },
            {
                "field_path": "production.capacity",
                "question": f"¿Cuál es la capacidad o tamaño del activo ({label})?",
                "help_text": "Unidades de producción, MW instalados, m², unidades, o la métrica relevante.",
                "options": [], "required": True, "order": 1, "group": "production",
            },
            {
                "field_path": "production.utilization",
                "question": "¿Qué factor de utilización o rendimiento esperas?",
                "help_text": "% del tiempo o capacidad que opera efectivamente. Ej: 80-95% para industrial, 25-35% para eólica.",
                "options": [
                    {"label": "70%", "value": 0.70},
                    {"label": "80%", "value": 0.80},
                    {"label": "90%", "value": 0.90},
                    {"label": "95%", "value": 0.95},
                ],
                "required": True, "order": 2, "group": "production",
            },
            {
                "field_path": "revenue.main_price",
                "question": f"¿Cuál es el precio/ingreso principal por unidad producida?",
                "help_text": "€/MWh, €/m²/mes, €/kg, €/unidad — según el tipo de activo.",
                "options": [], "required": True, "order": 3, "group": "revenue",
            },
            {
                "field_path": "revenue.contract_type",
                "question": "¿Cómo es la estructura de ingresos?",
                "help_text": "Contrato fijo (PPA/alquiler), mercado spot, mixto, o por proyecto.",
                "options": [
                    {"label": "Contrato fijo (precio garantizado)", "value": "fixed"},
                    {"label": "Mercado / spot", "value": "market"},
                    {"label": "Mixto (parte fija + parte variable)", "value": "mixed"},
                    {"label": "Por proyecto / bajo demanda", "value": "project"},
                ],
                "required": True, "order": 4, "group": "revenue",
            },
            {
                "field_path": "revenue.escalation",
                "question": "¿Los ingresos tienen escalación anual?",
                "help_text": "IPC, escalación contractual, o precio fijo sin subidas.",
                "options": [
                    {"label": "0% (precio fijo)", "value": 0.0},
                    {"label": "2% (IPC)", "value": 0.02},
                    {"label": "3% (contractual)", "value": 0.03},
                ],
                "required": False, "order": 5, "group": "revenue",
            },
            {
                "field_path": "capex.total_per_unit",
                "question": f"¿Cuánto cuesta el CAPEX total por unidad de {label}?",
                "help_text": "Inversión inicial: €/MW, €/m², €/unidad. Incluye equipo + instalación.",
                "options": [], "required": True, "order": 6, "group": "capex",
            },
            {
                "field_path": "capex.additional_costs",
                "question": "¿Hay costes adicionales de desarrollo, conexión o terreno?",
                "help_text": "Permisos, ingeniería, conexión a red, adquisición de terreno.",
                "options": [
                    {"label": "No, todo incluido en CAPEX", "value": 0},
                    {"label": "€100,000 adicionales", "value": 100000},
                    {"label": "€500,000 adicionales", "value": 500000},
                    {"label": "€1,000,000 adicionales", "value": 1000000},
                ],
                "required": False, "order": 7, "group": "capex",
            },
            {
                "field_path": "opex.fixed_annual",
                "question": "¿Cuánto son los costes fijos anuales de operación?",
                "help_text": "O&M, seguros, alquiler terreno, gestión, personal fijo.",
                "options": [], "required": True, "order": 8, "group": "opex",
            },
            {
                "field_path": "opex.variable_per_unit",
                "question": "¿Hay costes variables por unidad producida?",
                "help_text": "€/MWh, €/unidad, €/m³ — costes que escalan con producción.",
                "options": [
                    {"label": "No hay costes variables significativos", "value": 0},
                ],
                "required": False, "order": 9, "group": "opex",
            },
            {
                "field_path": "financing.leverage",
                "question": "¿Cómo se financia el proyecto?",
                "help_text": "100% equity (sin deuda), project finance (70-80% deuda), o mixto.",
                "options": [
                    {"label": "100% equity (sin deuda)", "value": 0},
                    {"label": "50% deuda / 50% equity", "value": 0.50},
                    {"label": "70% deuda / 30% equity", "value": 0.70},
                    {"label": "80% deuda / 20% equity", "value": 0.80},
                ],
                "required": True, "order": 10, "group": "financing",
            },
            {
                "field_path": "financing.interest_rate",
                "question": "¿A qué tipo de interés la deuda (si aplica)?",
                "help_text": "Project finance: 3-5%. Corporate: 4-7%. SME: 5-10%.",
                "options": [
                    {"label": "4% (project finance)", "value": 0.04},
                    {"label": "5% (corporate)", "value": 0.05},
                    {"label": "7% (SME)", "value": 0.07},
                ],
                "required": False, "order": 11, "group": "financing", "expert_only": True,
            },
            {
                "field_path": "location.country",
                "question": "¿En qué país está el activo?",
                "help_text": "Importante para impuestos, regulación, incentivos y coste de capital.",
                "options": [
                    {"label": "España", "value": "ES"},
                    {"label": "Portugal", "value": "PT"},
                    {"label": "USA", "value": "US"},
                    {"label": "Otro", "value": "other"},
                ],
                "required": True, "order": 12, "group": "taxes",
            },
            {
                "field_path": "custom_notes",
                "question": "¿Quieres añadir algún input adicional o nota especial?",
                "help_text": "Subvenciones, restricciones, condiciones de mercado, cualquier factor especial.",
                "options": [
                    {"label": "No, todo está definido", "value": "none"},
                    {"label": "Sí, quiero añadir algo", "value": "custom"},
                ],
                "required": False, "order": 99, "group": "custom",
            },
        ]

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
