from typing import Any

from asset_finance_modeler.intelligence.workflows.engine import WorkflowEngine
from asset_finance_modeler.intelligence.workflows.loader import (
    list_builtin_workflows,
    load_workflow,
)


def handle_workflows_list(_args: dict[str, Any]) -> dict[str, Any]:
    return {"workflows": list_builtin_workflows()}


def handle_workflows_describe(args: dict[str, Any]) -> dict[str, Any]:
    try:
        wf = load_workflow(args["workflow_id"])
    except FileNotFoundError as exc:
        return {"error": str(exc)}
    return {
        "id": wf["id"],
        "name": wf.get("name", wf["id"]),
        "description": wf.get("description", ""),
        "inputs": wf.get("inputs", []),
        "steps_count": len(wf.get("steps", [])),
    }


def make_workflows_run(registry_provider: Any) -> Any:
    """`registry_provider` is a callable that returns the current registry
    (avoids circular reference at registry-build time)."""
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        try:
            wf = load_workflow(args["workflow_id"])
        except FileNotFoundError as exc:
            return {"error": str(exc)}

        def dispatcher(tool_name: str, tool_args: dict[str, Any]) -> Any:
            if tool_name == "noop.identity":
                return tool_args
            registry = registry_provider()
            spec = registry.get(tool_name)
            if spec is None:
                raise ValueError(f"workflow referenced unknown tool: {tool_name}")
            return spec.handler(tool_args)

        engine = WorkflowEngine(tool_dispatcher=dispatcher)
        try:
            return engine.run(wf, args.get("inputs", {}))
        except ValueError as exc:
            return {"error": str(exc)}

    return _handle
