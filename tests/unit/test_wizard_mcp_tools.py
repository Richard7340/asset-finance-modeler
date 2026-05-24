# tests/unit/test_wizard_mcp_tools.py
import pytest

from asset_finance_modeler.core.resolved_input import InsufficientDataError
from asset_finance_modeler.mcp_server.tools.wizard import (
    make_wizard_adjust,
    make_wizard_answer,
    make_wizard_back,
    make_wizard_cancel,
    make_wizard_finalize,
    make_wizard_skip,
    make_wizard_start,
    make_wizard_status,
)
from asset_finance_modeler.wizard.engine import WizardEngine


@pytest.fixture()
def engine():
    return WizardEngine()


def test_mcp_wizard_start(engine):
    handler = make_wizard_start(engine)
    result = handler({"asset_description": "planta solar de 50MW", "region": "ES"})
    assert "session_id" in result
    assert result["asset_type"] == "solar_pv"


def test_mcp_wizard_answer(engine):
    start = make_wizard_start(engine)({"asset_description": "solar", "region": "ES"})
    sid = start["session_id"]
    result = make_wizard_answer(engine)({"session_id": sid, "value": 50})
    assert "progress" in result


def test_mcp_wizard_status(engine):
    start = make_wizard_start(engine)({"asset_description": "solar"})
    sid = start["session_id"]
    result = make_wizard_status(engine)({"session_id": sid})
    assert "answered" in result


def test_mcp_wizard_cancel(engine):
    start = make_wizard_start(engine)({"asset_description": "solar"})
    sid = start["session_id"]
    result = make_wizard_cancel(engine)({"session_id": sid})
    assert result["cancelled"] is True


def test_mcp_wizard_back(engine):
    start = make_wizard_start(engine)({"asset_description": "solar", "region": "ES"})
    sid = start["session_id"]
    make_wizard_answer(engine)({"session_id": sid, "value": 50})
    result = make_wizard_back(engine)({"session_id": sid})
    assert "previous_question" in result


def test_mcp_wizard_skip(engine):
    start = make_wizard_start(engine)({"asset_description": "solar", "region": "ES"})
    sid = start["session_id"]
    result = make_wizard_skip(engine)({"session_id": sid})
    assert "proposed_value" in result or "no_benchmark" in result


def test_mcp_wizard_adjust(engine):
    start = make_wizard_start(engine)({"asset_description": "solar", "region": "ES"})
    sid = start["session_id"]
    # Answer first question to have something to adjust
    make_wizard_answer(engine)({"session_id": sid, "value": 50})
    result = make_wizard_adjust(engine)(
        {"session_id": sid, "field_path": "capacity_mw", "new_value": 75}
    )
    # adjust returns a dict — should not raise
    assert isinstance(result, dict)


def test_mcp_wizard_finalize_incomplete_raises(engine):
    start = make_wizard_start(engine)({"asset_description": "solar", "region": "ES"})
    sid = start["session_id"]
    with pytest.raises(InsufficientDataError):
        make_wizard_finalize(engine)({"session_id": sid})
