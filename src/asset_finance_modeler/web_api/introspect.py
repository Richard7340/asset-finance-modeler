from __future__ import annotations

import copy
import re
from typing import Any


def _leaf(path: str, value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        t = "bool"
    elif isinstance(value, (int, float)):
        t = "number"
    else:
        t = "text"
    return {
        "path": path,
        "value": value,
        "type": t,
        "section": path.split(".", 1)[0].split("[", 1)[0],
        "label": path.rsplit(".", 1)[-1].split("[", 1)[0].replace("_", " "),
    }


def schema_tree(config: dict[str, Any], _path: str = "") -> list[dict[str, Any]]:
    """Flatten a model config dict into editable input leaves with dotted/
    indexed paths and inferred types. Lists of dicts -> indexed paths; scalar
    leaves carry value+type+section. Skips None and nested empty containers."""
    leaves: list[dict[str, Any]] = []
    for key, val in config.items():
        path = f"{_path}.{key}" if _path else key
        if isinstance(val, dict):
            leaves.extend(schema_tree(val, path))
        elif isinstance(val, list):
            for i, item in enumerate(val):
                ip = f"{path}[{i}]"
                if isinstance(item, dict):
                    leaves.extend(schema_tree(item, ip))
                elif not isinstance(item, list):
                    leaves.append(_leaf(ip, item))
        elif val is not None:
            leaves.append(_leaf(path, val))
    return leaves


def set_by_path(config: dict[str, Any], path: str, value: Any) -> dict[str, Any]:
    """Return a deep copy of config with `value` set at the dotted/indexed
    path (e.g. 'financing.senior.interest_rate' or 'revenue[0].price')."""
    out = copy.deepcopy(config)
    keys: list[Any] = []
    for name, idx in re.findall(r"(\w+)|\[(\d+)\]", path):
        keys.append(name if name else int(idx))
    node: Any = out
    for k in keys[:-1]:
        node = node[k]
    node[keys[-1]] = value
    return out
