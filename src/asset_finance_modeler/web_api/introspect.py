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


# Editable leaves that exist in a config but move NO KPI (no engine reads them).
# Surfacing them would show a user an input that silently does nothing, so they
# are hidden from the schema tree (E4). Matched on the leaf name only. These are
# inert across every asset type that carries them.
_INERT_LEAF_FIELDS = frozenset(
    {
        "mra_eur",  # financing.reserves.* — never consumed
        "working_capital_eur",  # financing.reserves.* — never consumed
        "target_irr",  # financing.equity.* — no hurdle/waterfall consumer
        "r_and_d_deduction_pct",  # taxes.* — declared but never applied
        "uptime_target",  # SLA stream — cosmetic, no KPI impact
    }
)

# ``meta.inflation_annual`` is LIVE for SaaS (it escalates the scalar fixed-opex
# buckets) but inert on infra/business, which reuse the shared ModelMeta yet
# never read it. So it is hidden unless the tree is built for a SaaS model.
_SAAS_ONLY_LEAF_FIELDS = frozenset({"inflation_annual"})


# Optional config BLOCKS that are frequently None in a preset but the engine
# DOES consume when present (mezzanine is auto-sized into the debt stack). Like
# the curve fields, we surface the block's editable leaves even when None so the
# platform can attach/enable it via the API (A4). Maps the leaf key (under
# ``financing``) to the default field values to expose. Editing any leaf
# instantiates the block (the override path then resolves).
def _mezzanine_defaults() -> dict[str, Any]:
    from asset_finance_modeler.assets.infrastructure.schema import (  # noqa: PLC0415
        MezzanineDebtConfig,
    )

    return MezzanineDebtConfig().model_dump()


_OPTIONAL_CONFIG_BLOCKS: dict[str, Any] = {"mezzanine": _mezzanine_defaults}


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


def schema_tree(
    config: dict[str, Any], _path: str = "", *, asset_type: str | None = None
) -> list[dict[str, Any]]:
    """Flatten a model config dict into editable input leaves with dotted/
    indexed paths and inferred types. Lists of dicts -> indexed paths; scalar
    leaves carry value+type+section. Skips None, nested empty containers, and
    leaves that move no KPI (see ``_INERT_LEAF_FIELDS`` / ``_SAAS_ONLY_LEAF_FIELDS``).

    ``asset_type`` (e.g. "saas") keeps fields that are live for that asset type
    but inert elsewhere (currently ``meta.inflation_annual``)."""
    leaves: list[dict[str, Any]] = []
    for key, val in config.items():
        path = f"{_path}.{key}" if _path else key
        # Hide editable-but-inert leaves so no surfaced input does nothing (E4).
        if key in _INERT_LEAF_FIELDS:
            continue
        if key in _SAAS_ONLY_LEAF_FIELDS and asset_type != "saas":
            continue
        if isinstance(val, dict):
            leaves.extend(schema_tree(val, path, asset_type=asset_type))
        elif isinstance(val, list):
            for i, item in enumerate(val):
                ip = f"{path}[{i}]"
                if isinstance(item, dict):
                    leaves.extend(schema_tree(item, ip, asset_type=asset_type))
                elif not isinstance(item, list):
                    leaves.append(_leaf(ip, item))
        elif val is not None:
            leaves.append(_leaf(path, val))
        elif key in _KNOWN_OPTIONAL_CURVE_FIELDS:
            # Surface a known-optional curve slot even when None so the platform
            # can attach a curve. Carry value=None; type "text" (curve name or
            # JSON points list both edit as text).
            leaves.append(_leaf(path, None))
        elif key in _OPTIONAL_CONFIG_BLOCKS:
            # Surface an optional config block (e.g. financing.mezzanine) even
            # when None so it is editable via the API (A4). Expand its default
            # field values as leaves; editing any of them enables the block.
            defaults = _OPTIONAL_CONFIG_BLOCKS[key]()
            leaves.extend(schema_tree(defaults, path, asset_type=asset_type))
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
            # Instantiate an optional config block on first write into it: a
            # preset renders ``financing.mezzanine`` as None, but an override
            # into it must enable the block (A4). Seed it with its defaults so
            # the remaining keys resolve and the engine consumes it.
            if (
                isinstance(node, dict)
                and node.get(k) is None
                and k in _OPTIONAL_CONFIG_BLOCKS
            ):
                node[k] = _OPTIONAL_CONFIG_BLOCKS[k]()
            node = node[k]
        leaf = keys[-1]
        # Reject a typo'd LEAF key on a dict parent: the leaf must already exist
        # (A2). Otherwise ``node[leaf] = value`` silently ADDS a key the engine
        # never reads, so the override 200s with no effect. ``model_dump()``
        # renders every schema field (incl. optional curve slots that are None),
        # so legitimate settable leaves are present and still accepted. List
        # indices fall through to the IndexError guard below.
        if isinstance(node, dict) and leaf not in node:
            raise InvalidPathError(path)
        node[leaf] = value
    except (KeyError, IndexError, TypeError) as exc:
        raise InvalidPathError(path) from exc
    return out
