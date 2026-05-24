# src/asset_finance_modeler/mcp_server/tools/wizard.py
from __future__ import annotations

from typing import Any

from asset_finance_modeler.wizard.engine import WizardEngine


def make_wizard_start(engine: WizardEngine) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        return engine.start(
            args["asset_description"],
            region=args.get("region"),
        )

    return _handle


def make_wizard_answer(engine: WizardEngine) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        return engine.answer(args["session_id"], args["value"])

    return _handle


def make_wizard_skip(engine: WizardEngine) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        return engine.skip(args["session_id"])

    return _handle


def make_wizard_back(engine: WizardEngine) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        return engine.back(args["session_id"])

    return _handle


def make_wizard_adjust(engine: WizardEngine) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        return engine.adjust(args["session_id"], args["field_path"], args["new_value"])

    return _handle


def make_wizard_status(engine: WizardEngine) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        return engine.status(args["session_id"])

    return _handle


def make_wizard_cancel(engine: WizardEngine) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        return engine.cancel(args["session_id"])

    return _handle


def make_wizard_finalize(engine: WizardEngine) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        return engine.finalize(args["session_id"])

    return _handle


def make_wizard_run(engine: WizardEngine) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        session = engine._get(args["session_id"])
        spec = session.finalize()
        return {"scenario_spec": spec, "message": "Use finance.simulate.run to execute"}

    return _handle
