from __future__ import annotations

import copy
import re
from typing import Any


# Curve fields are optional and frequently None in a preset, but the platform
# still needs to SEE the slot to attach a library curve / explicit points via
# the API. So these leaf names surface even when their value is None (unlike
# every other None leaf, which is skipped). Matched on the leaf name only, so
# it works for any revenue stream index (revenue[N].price_curve_name, …).
_KNOWN_OPTIONAL_CURVE_FIELDS = frozenset(
    {
        "price_curve_name",
        "price_points",
        "spread_curve_name",
        "spread_points",
        "curve_points",
    }
)


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
        elif key in _KNOWN_OPTIONAL_CURVE_FIELDS:
            # Surface a known-optional curve slot even when None so the platform
            # can attach a curve. Carry value=None; type "text" (curve name or
            # JSON points list both edit as text).
            leaves.append(_leaf(path, None))
    return leaves


class InvalidPathError(ValueError):
    """An override path does not resolve against the model config. Carries the
    offending ``path`` so the web layer can return a 400 (not a 500)."""

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(f"invalid override path: {path}")


def set_by_path(config: dict[str, Any], path: str, value: Any) -> dict[str, Any]:
    """Return a deep copy of config with `value` set at the dotted/indexed
    path (e.g. 'financing.senior.interest_rate' or 'revenue[0].price').

    Raises ``InvalidPathError`` (a ValueError carrying ``path``) when the path
    does not resolve, so callers can surface a 400 instead of a 500."""
    out = copy.deepcopy(config)
    keys: list[Any] = []
    for name, idx in re.findall(r"(\w+)|\[(\d+)\]", path):
        keys.append(name if name else int(idx))
    if not keys:
        raise InvalidPathError(path)
    node: Any = out
    try:
        for k in keys[:-1]:
            node = node[k]
        node[keys[-1]] = value
    except (KeyError, IndexError, TypeError) as exc:
        raise InvalidPathError(path) from exc
    return out
