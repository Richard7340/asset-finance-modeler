# src/asset_finance_modeler/wizard/session.py
from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from typing import Any, Literal

from asset_finance_modeler.core.resolved_input import InsufficientDataError, ResolvedInput
from asset_finance_modeler.intelligence.knowledge.schemas import QuestionTemplate

_CONFIDENCE_HIGH = 0.8
_CONFIDENCE_MEDIUM_LOW = 0.5
_CONFIDENCE_WARN = 0.6


@dataclass
class WizardSession:
    session_id: str
    asset_type: str
    mode: Literal["full", "quick_start"]
    questions: list[QuestionTemplate]
    resolved: dict[str, ResolvedInput] = field(default_factory=dict)
    _current_idx: int = 0
    _history: list[int] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        asset_type: str,
        questions: list[QuestionTemplate],
        quick_start: dict[str, ResolvedInput] | None = None,
    ) -> WizardSession:
        session = cls(
            session_id=f"wiz-{secrets.token_hex(6)}",
            asset_type=asset_type,
            mode="quick_start" if quick_start else "full",
            questions=sorted(questions, key=lambda q: q.order),
        )
        if quick_start:
            session.resolved = dict(quick_start)
            session._advance_past_answered()
        return session

    @property
    def current_question(self) -> QuestionTemplate | None:
        while self._current_idx < len(self.questions):
            q = self.questions[self._current_idx]
            if q.field_path not in self.resolved:
                return q
            self._current_idx += 1
        return None

    @property
    def progress(self) -> dict[str, int]:
        return {
            "answered": len(self.resolved),
            "total": len(self.questions),
            "pending": len(self.questions) - len(self.resolved),
        }

    def answer(
        self,
        value: Any,
        source: str,
        provenance: str,
        confidence: float,
        benchmark_id: str | None = None,
    ) -> dict[str, Any]:
        q = self.current_question
        if q is None:
            return {"completed": True, "progress": self.progress}
        self._history.append(self._current_idx)
        self.resolved[q.field_path] = ResolvedInput(
            field_path=q.field_path,
            value=value,
            source=source,
            provenance=provenance,
            confidence=confidence,
            benchmark_id=benchmark_id,
        )
        self._current_idx += 1
        nxt = self.current_question
        if nxt is None:
            return {"completed": True, "progress": self.progress}
        return {"next_question": nxt.model_dump(), "progress": self.progress}

    def back(self) -> dict[str, Any]:
        if not self._history:
            return {"error": "No previous question"}
        prev_idx = self._history.pop()
        q = self.questions[prev_idx]
        old_value = self.resolved.pop(q.field_path, None)
        self._current_idx = prev_idx
        return {
            "previous_question": q.model_dump(),
            "current_answer": old_value.value if old_value else None,
        }

    def adjust(
        self,
        field_path: str,
        new_value: Any,
        source: str,
        provenance: str,
        confidence: float,
    ) -> dict[str, Any]:
        self.resolved[field_path] = ResolvedInput(
            field_path=field_path,
            value=new_value,
            source=source,
            provenance=provenance,
            confidence=confidence,
        )
        return {"updated_input": self.resolved[field_path]}

    def status(self) -> dict[str, Any]:
        q = self.current_question
        return {
            **self.progress,
            "current_question": q.model_dump() if q else None,
            "resolved_inputs": [ri.to_dict() for ri in self.resolved.values()],
        }

    def finalize(self) -> dict[str, Any]:
        missing = [
            q.field_path
            for q in self.questions
            if q.required and q.field_path not in self.resolved
        ]
        if missing:
            raise InsufficientDataError(missing)
        inputs = list(self.resolved.values())
        high = sum(1 for ri in inputs if ri.confidence >= _CONFIDENCE_HIGH)
        medium = sum(1 for ri in inputs if _CONFIDENCE_MEDIUM_LOW <= ri.confidence < _CONFIDENCE_HIGH)
        low = sum(1 for ri in inputs if ri.confidence < _CONFIDENCE_MEDIUM_LOW)
        warnings: list[str] = []
        low_conf = [ri for ri in inputs if ri.confidence < _CONFIDENCE_WARN]
        if low_conf:
            fields = ", ".join(ri.field_path for ri in low_conf)
            warnings.append(
                f"Low confidence inputs ({len(low_conf)}): {fields}. Verify with real data."
            )
        return {
            "resolved_inputs": [ri.to_dict() for ri in inputs],
            "confidence_summary": {"high": high, "medium": medium, "low": low},
            "warnings": warnings,
        }

    def _advance_past_answered(self) -> None:
        while self._current_idx < len(self.questions):
            if self.questions[self._current_idx].field_path not in self.resolved:
                break
            self._current_idx += 1
