# src/asset_finance_modeler/wizard/engine.py
from __future__ import annotations

from typing import Any

from asset_finance_modeler.core.resolved_input import ResolvedInput
from asset_finance_modeler.intelligence.benchmarks.engine import BenchmarkEngine
from asset_finance_modeler.intelligence.knowledge.loader import KBLoader

from .session import WizardSession


class WizardEngine:
    def __init__(self) -> None:
        self._loader = KBLoader()
        self._benchmark = BenchmarkEngine(self._loader)
        self._sessions: dict[str, WizardSession] = {}

    def start(self, asset_description: str, region: str | None = None) -> dict[str, Any]:
        asset_type = self._loader.detect_asset_type(asset_description)
        questions = self._loader.load_questions(asset_type or "generic")
        quick_start: dict[str, ResolvedInput] | None = None
        mode = "full"
        if asset_type and region:
            presets = self._loader.load_quick_starts()
            for preset in presets:
                if preset.asset_type == asset_type and (
                    preset.region is None or preset.region == region
                ):
                    quick_start = {}
                    for fp, val in preset.defaults.items():
                        quick_start[fp] = ResolvedInput(
                            field_path=fp,
                            value=val,
                            source="preset",
                            provenance=f"quick_start_{asset_type}_{region}",
                            confidence=0.3,
                        )
                    mode = "quick_start"
                    break
        session = WizardSession.create(asset_type or "generic", questions, quick_start)
        self._sessions[session.session_id] = session
        result: dict[str, Any] = {
            "session_id": session.session_id,
            "asset_type": asset_type,
            "mode": mode,
            "total_questions": len(questions),
        }
        if mode == "quick_start" and quick_start:
            result["proposed_inputs"] = [ri.to_dict() for ri in quick_start.values()]
        q = session.current_question
        if q:
            result["first_question"] = q.model_dump()
        return result

    def _get(self, session_id: str) -> WizardSession:
        if session_id not in self._sessions:
            raise KeyError(f"Session {session_id} not found")
        return self._sessions[session_id]

    def answer(self, session_id: str, value: Any) -> dict[str, Any]:
        return self._get(session_id).answer(
            value, source="user", provenance="User input", confidence=1.0
        )

    def skip(self, session_id: str) -> dict[str, Any]:
        session = self._get(session_id)
        q = session.current_question
        if q is None:
            return {"error": "No current question"}
        bm = self._benchmark.search(
            q.benchmark_key or q.field_path, session.asset_type, None
        )
        if bm:
            session.answer(
                bm.value,
                source="benchmark",
                provenance=bm.source,
                confidence=bm.confidence,
                benchmark_id=bm.benchmark_id,
            )
            return {
                "proposed_value": bm.value,
                "source": bm.source,
                "confidence": bm.confidence,
                "methodology": bm.methodology,
                "assumptions": bm.assumptions,
            }
        return {"no_benchmark": True, "field": q.field_path}

    def back(self, session_id: str) -> dict[str, Any]:
        return self._get(session_id).back()

    def adjust(self, session_id: str, field_path: str, new_value: Any) -> dict[str, Any]:
        return self._get(session_id).adjust(
            field_path,
            new_value,
            source="user",
            provenance="User adjustment",
            confidence=1.0,
        )

    def status(self, session_id: str) -> dict[str, Any]:
        return self._get(session_id).status()

    def cancel(self, session_id: str) -> dict[str, Any]:
        del self._sessions[session_id]
        return {"cancelled": True}

    def finalize(self, session_id: str) -> dict[str, Any]:
        return self._get(session_id).finalize()
