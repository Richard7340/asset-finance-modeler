import pytest

from asset_finance_modeler.core.resolved_input import InsufficientDataError, ResolvedInput
from asset_finance_modeler.intelligence.knowledge.schemas import QuestionOption, QuestionTemplate
from asset_finance_modeler.wizard.session import WizardSession


def _sample_questions():
    return [
        QuestionTemplate(field_path="production.capacity_mwp", question="Capacity?",
                         options=[QuestionOption(label="50", value=50)], required=True, order=1),
        QuestionTemplate(field_path="capex.items[0].amount_per_unit", question="CAPEX?",
                         options=[], required=True, order=2),
        QuestionTemplate(field_path="financing.max_leverage", question="Leverage?",
                         options=[], required=False, order=3),
    ]


def test_session_creation():
    session = WizardSession.create("solar_pv", _sample_questions())
    assert session.asset_type == "solar_pv"
    assert session.mode == "full"
    assert session.current_question is not None
    assert session.progress["answered"] == 0


def test_session_answer():
    session = WizardSession.create("solar_pv", _sample_questions())
    result = session.answer(50.0, source="user", provenance="User", confidence=1.0)
    assert result["progress"]["answered"] == 1


def test_session_complete_flow():
    session = WizardSession.create("solar_pv", _sample_questions())
    session.answer(50.0, source="user", provenance="User", confidence=1.0)
    session.answer(0.45, source="benchmark", provenance="Lazard", confidence=0.92)
    result = session.answer(0.75, source="preset", provenance="default", confidence=0.3)
    assert result.get("completed") is True


def test_session_back():
    session = WizardSession.create("solar_pv", _sample_questions())
    session.answer(50.0, source="user", provenance="User", confidence=1.0)
    result = session.back()
    assert result["current_answer"] == 50.0
    assert session.progress["answered"] == 0


def test_session_finalize_with_missing_required():
    session = WizardSession.create("solar_pv", _sample_questions())
    session.answer(50.0, source="user", provenance="User", confidence=1.0)
    with pytest.raises(InsufficientDataError) as exc_info:
        session.finalize()
    assert "capex.items[0].amount_per_unit" in exc_info.value.missing_fields


def test_session_finalize_success():
    session = WizardSession.create("solar_pv", _sample_questions())
    session.answer(50.0, source="user", provenance="User", confidence=1.0)
    session.answer(0.45, source="user", provenance="User", confidence=1.0)
    session.answer(0.75, source="user", provenance="User", confidence=1.0)
    result = session.finalize()
    assert "resolved_inputs" in result
    assert len(result["resolved_inputs"]) == 3
    assert "confidence_summary" in result


def test_session_status():
    session = WizardSession.create("solar_pv", _sample_questions())
    session.answer(50.0, source="user", provenance="User", confidence=1.0)
    status = session.status()
    assert status["answered"] == 1
    assert status["pending"] == 2


def test_quick_start_mode():
    defaults = {"production.capacity_mwp": ResolvedInput(
        field_path="production.capacity_mwp", value=50, source="preset",
        provenance="quick_start", confidence=0.3)}
    session = WizardSession.create("solar_pv", _sample_questions(), quick_start=defaults)
    assert session.mode == "quick_start"
    assert session.progress["answered"] == 1


def test_adjust_in_quick_start():
    defaults = {"production.capacity_mwp": ResolvedInput(
        field_path="production.capacity_mwp", value=50, source="preset",
        provenance="quick_start", confidence=0.3)}
    session = WizardSession.create("solar_pv", _sample_questions(), quick_start=defaults)
    result = session.adjust("production.capacity_mwp", 100, source="user",
                            provenance="User adjusted", confidence=1.0)
    assert result["updated_input"].value == 100
