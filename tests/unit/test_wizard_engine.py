# tests/unit/test_wizard_engine.py
import pytest

from asset_finance_modeler.core.resolved_input import InsufficientDataError
from asset_finance_modeler.wizard.engine import WizardEngine


def test_start_session_solar():
    engine = WizardEngine()
    result = engine.start("planta solar de 50MW en España", region="ES")
    assert result["asset_type"] == "solar_pv"
    assert "session_id" in result
    assert result["total_questions"] > 0


def test_start_session_unknown_asset():
    engine = WizardEngine()
    result = engine.start("algo que no existe", region=None)
    assert result["asset_type"] is None


def test_start_solar_with_quick_start():
    engine = WizardEngine()
    result = engine.start("solar 50MW", region="ES")
    assert result["mode"] == "quick_start"
    assert "proposed_inputs" in result


def test_answer_flow():
    engine = WizardEngine()
    start = engine.start("solar 50MW", region="ES")
    sid = start["session_id"]
    result = engine.answer(sid, 50.0)
    assert "progress" in result


def test_skip_returns_benchmark():
    engine = WizardEngine()
    start = engine.start("solar 50MW", region="ES")
    sid = start["session_id"]
    result = engine.skip(sid)
    assert "proposed_value" in result or "no_benchmark" in result


def test_cancel_session():
    engine = WizardEngine()
    start = engine.start("solar", region=None)
    sid = start["session_id"]
    result = engine.cancel(sid)
    assert result["cancelled"] is True
    with pytest.raises(KeyError):
        engine.status(sid)


def test_status():
    engine = WizardEngine()
    start = engine.start("solar", region="ES")
    sid = start["session_id"]
    status = engine.status(sid)
    assert "answered" in status
    assert "pending" in status


def test_back():
    engine = WizardEngine()
    start = engine.start("solar", region="ES")
    sid = start["session_id"]
    engine.answer(sid, 50.0)
    result = engine.back(sid)
    assert "previous_question" in result


def test_finalize_incomplete_raises():
    engine = WizardEngine()
    start = engine.start("solar", region="ES")
    sid = start["session_id"]
    with pytest.raises(InsufficientDataError):
        engine.finalize(sid)
