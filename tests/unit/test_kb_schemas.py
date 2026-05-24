# tests/unit/test_kb_schemas.py
from datetime import date

from asset_finance_modeler.intelligence.knowledge.schemas import (
    AssetIntent,
    BenchmarkEntry,
    ConceptEntry,
    QuestionOption,
    QuestionTemplate,
    QuickStartPreset,
    ValidationRule,
)


def test_benchmark_entry_required_fields():
    bm = BenchmarkEntry(
        field="capex_per_kwp_eur",
        asset_type="solar_pv",
        value=550,
        valid_from=date(2026, 1, 1),
        valid_to=date(2026, 12, 31),
        source="Lazard LCOE v17.0",
        confidence=0.92,
        unit="EUR/kWp",
        methodology="EPC + grid, excludes land",
    )
    assert bm.confidence == 0.92
    assert bm.assumptions == []


def test_benchmark_with_region_and_assumptions():
    bm = BenchmarkEntry(
        field="capex_per_kwp_eur",
        asset_type="solar_pv",
        region="ES",
        value=550,
        valid_from=date(2026, 1, 1),
        valid_to=date(2026, 12, 31),
        source="Lazard",
        confidence=0.92,
        unit="EUR/kWp",
        methodology="EPC + grid",
        assumptions=["utility-scale", "fixed-tilt"],
        source_url="https://lazard.com",
    )
    assert bm.region == "ES"
    assert len(bm.assumptions) == 2


def test_concept_entry():
    ce = ConceptEntry(
        id="dscr",
        title="DSCR",
        content="DSCR measures...",
        asset_types=["solar_pv", "wind"],
        category="debt_metrics",
    )
    assert "solar_pv" in ce.asset_types


def test_question_template():
    qt = QuestionTemplate(
        field_path="production.capacity_mwp",
        question="Capacity?",
        options=[
            QuestionOption(label="10 MWp", value=10),
            QuestionOption(label="50 MWp", value=50),
        ],
        required=True,
        order=1,
    )
    assert qt.required and not qt.expert_only and len(qt.options) == 2


def test_question_with_depends_on():
    qt = QuestionTemplate(
        field_path="revenue[0].price",
        question="PPA price?",
        options=[],
        required=True,
        order=5,
        depends_on="revenue[0].type",
        group="revenue",
    )
    assert qt.depends_on == "revenue[0].type"


def test_validation_rule():
    vr = ValidationRule(
        field_path="production.capacity_mwp",
        rule_id="capacity_mwp.utility_scale_range",
        min_value=0.1,
        max_value=2000,
        message="Capacity must be 0.1-2000 MWp",
    )
    assert vr.min_value == 0.1


def test_quick_start_preset():
    qsp = QuickStartPreset(
        asset_type="solar_pv",
        region="ES",
        size_bracket=[10, 100],
        defaults={
            "production.capacity_mwp": 50,
            "degradation.annual_rate": 0.005,
        },
    )
    assert qsp.defaults["production.capacity_mwp"] == 50


def test_asset_intent():
    ai = AssetIntent(
        patterns=["planta solar", "FV", "PV"],
        asset_type="solar_pv",
    )
    assert "FV" in ai.patterns
