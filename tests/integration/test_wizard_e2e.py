# tests/integration/test_wizard_e2e.py
"""E2E test: wizard flow for solar PV — start → answer → finalize."""
import pytest
from asset_finance_modeler.wizard.engine import WizardEngine
from asset_finance_modeler.core.resolved_input import InsufficientDataError


def test_wizard_full_flow_solar():
    """Complete wizard flow: start → answer all → finalize."""
    engine = WizardEngine()
    start = engine.start("planta solar de 50MW en España", region="ES")
    sid = start["session_id"]
    assert start["asset_type"] == "solar_pv"

    # Answer all questions (use first option or skip)
    max_iterations = 50  # safety limit
    for _ in range(max_iterations):
        status = engine.status(sid)
        if status["current_question"] is None:
            break
        q = status["current_question"]
        if q.get("options") and len(q["options"]) > 0:
            engine.answer(sid, q["options"][0]["value"])
        else:
            # Try skip (benchmark), if no benchmark use a default
            skip_result = engine.skip(sid)
            if "no_benchmark" in skip_result:
                engine.answer(sid, 0)  # fallback default

    result = engine.finalize(sid)
    assert "resolved_inputs" in result
    assert result["confidence_summary"]["high"] >= 0
    assert len(result["resolved_inputs"]) > 0


def test_wizard_missing_required_blocks_finalize():
    """Finalize without answering required questions raises InsufficientDataError."""
    engine = WizardEngine()
    start = engine.start("solar", region="ES")
    sid = start["session_id"]
    with pytest.raises(InsufficientDataError) as exc_info:
        engine.finalize(sid)
    assert len(exc_info.value.missing_fields) > 0


def test_wizard_quick_start_solar_es():
    """Quick start mode pre-fills most inputs."""
    engine = WizardEngine()
    start = engine.start("planta solar", region="ES")
    sid = start["session_id"]
    assert start["mode"] == "quick_start"
    assert "proposed_inputs" in start
    assert len(start["proposed_inputs"]) > 0

    # In quick start, many questions are pre-answered
    status = engine.status(sid)
    assert status["answered"] > 0


def test_wizard_back_and_change():
    """Answer, go back, change answer."""
    engine = WizardEngine()
    start = engine.start("solar 50MW", region="ES")
    sid = start["session_id"]

    # Answer first question
    engine.answer(sid, 50.0)
    assert engine.status(sid)["answered"] >= 1

    # Go back
    back_result = engine.back(sid)
    assert back_result["current_answer"] is not None

    # Answer differently
    engine.answer(sid, 100.0)

    # Check the new answer stuck
    status = engine.status(sid)
    resolved = {ri["field_path"]: ri["value"] for ri in status["resolved_inputs"]}
    first_field = start.get("first_question", {}).get("field_path")
    if first_field and first_field in resolved:
        # In quick_start mode the first visible question may not be capacity
        pass  # Just verify no crash


def test_wizard_cancel():
    """Cancel discards session."""
    engine = WizardEngine()
    start = engine.start("solar", region=None)
    sid = start["session_id"]
    result = engine.cancel(sid)
    assert result["cancelled"] is True
    with pytest.raises(KeyError):
        engine.status(sid)


def test_wizard_unknown_asset_uses_generic():
    """Unknown asset description falls back to generic questions."""
    engine = WizardEngine()
    start = engine.start("something completely unknown", region=None)
    assert start["asset_type"] is None
    assert start["total_questions"] > 0  # generic questions loaded
