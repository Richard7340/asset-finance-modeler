"""Privacy utilities for meta-learning anonymization."""
from __future__ import annotations

import hashlib
from typing import Any


PII_FIELDS = frozenset(
    {"user_id", "workspace_id", "email", "name", "company", "phone", "address"}
)


def anonymize_insight(insight: dict[str, Any]) -> dict[str, Any]:
    """Strip PII and hash identifiers for anonymous meta-learning."""
    clean: dict[str, Any] = {}
    for k, v in insight.items():
        if k in PII_FIELDS:
            continue
        if k.endswith("_id") and isinstance(v, str):
            clean[k] = hashlib.sha256(v.encode()).hexdigest()[:12]
        else:
            clean[k] = v
    return clean


def should_collect_meta_learning(tier: str, opt_out: bool) -> bool:
    """Determine if meta-learning should be collected for this workspace."""
    if tier == "enterprise":
        return True  # Enterprise always has meta-learning
    return not opt_out  # Others: respect opt-out preference
