from importlib.resources import files
from typing import Any

import yaml


def list_builtin_workflows() -> list[dict[str, Any]]:
    """List all built-in workflow templates with id + name + description."""
    out: list[dict[str, Any]] = []
    base = files("asset_finance_modeler.intelligence.workflows.templates")
    for resource in base.iterdir():
        name = resource.name
        if not name.endswith(".yaml"):
            continue
        with resource.open() as f:
            data = yaml.safe_load(f)
        out.append({
            "id": data["id"],
            "name": data.get("name", data["id"]),
            "description": data.get("description", ""),
            "inputs": data.get("inputs", []),
        })
    return out


def load_workflow(workflow_id: str) -> dict[str, Any]:
    """Load a workflow YAML by id."""
    path = files("asset_finance_modeler.intelligence.workflows.templates") / f"{workflow_id}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"workflow {workflow_id!r} not found")
    with path.open() as f:
        result: dict[str, Any] = yaml.safe_load(f)
    return result
