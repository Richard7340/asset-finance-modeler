import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

ToolDispatcher = Callable[[str, dict[str, Any]], Any]

_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _resolve_path(context: dict[str, Any], path: str) -> Any:
    """Resolve dotted path against context dict. Supports list indexing [0]."""
    parts = re.split(r"\.|\[|\]", path)
    parts = [p for p in parts if p]
    current: Any = context
    for p in parts:
        if isinstance(current, list):
            current = current[int(p)]
        elif isinstance(current, dict):
            current = current[p]
        else:
            raise KeyError(f"cannot resolve {path!r} (stuck at {type(current).__name__})")
    return current


def _substitute(value: Any, context: dict[str, Any]) -> Any:
    """Recursively substitute ${var.path} in strings within nested structure."""
    if isinstance(value, str):
        # If the entire string is a single variable reference, return the typed value
        m = _VAR_PATTERN.fullmatch(value.strip())
        if m:
            return _resolve_path(context, m.group(1).strip())
        # Otherwise, interpolate as string
        def repl(match: re.Match[str]) -> str:
            return str(_resolve_path(context, match.group(1).strip()))
        return _VAR_PATTERN.sub(repl, value)
    if isinstance(value, dict):
        return {k: _substitute(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute(v, context) for v in value]
    return value


@dataclass
class WorkflowEngine:
    tool_dispatcher: ToolDispatcher

    def run(self, workflow: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
        # Validate inputs
        for spec in workflow.get("inputs", []):
            if spec.get("required", True) and spec["name"] not in inputs:
                raise ValueError(f"required input {spec['name']!r} missing")

        context: dict[str, Any] = dict(inputs)

        for step in workflow.get("steps", []):
            foreach = step.get("foreach")
            if foreach is not None:
                # Run the step once per item in the foreach array
                items = _substitute(foreach, context)
                if not isinstance(items, list):
                    raise ValueError(f"foreach must resolve to a list, got {type(items).__name__}")
                as_var = step.get("as", "item")
                captures: list[Any] = []
                for item in items:
                    iter_context = dict(context, **{as_var: item})
                    resolved_args = _substitute(step.get("args", {}), iter_context)
                    result = self.tool_dispatcher(step["tool"], resolved_args)
                    captures.append(result)
                capture_key = step.get("capture")
                if capture_key:
                    context[capture_key] = captures
            else:
                resolved_args = _substitute(step.get("args", {}), context)
                result = self.tool_dispatcher(step["tool"], resolved_args)
                capture_key = step.get("capture")
                if capture_key:
                    context[capture_key] = result

        # Build output
        output_spec = workflow.get("output", {})
        output = _substitute(output_spec, context)
        return output
