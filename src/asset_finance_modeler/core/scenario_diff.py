"""Scenario diff engine — compares two scenario result dicts.

Produces:
- Input deltas: which overrides/inputs differ between the two scenarios.
- KPI changes: how summary metrics moved with direction (improved/worsened).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class InputDelta:
    field_path: str
    value_a: Any
    value_b: Any
    change: float | None  # numeric difference if both are numbers


@dataclass
class KPIDelta:
    metric: str
    value_a: float
    value_b: float
    change: float
    change_pct: float
    direction: str  # "improved", "worsened", "unchanged", or "changed" (unknown polarity)


@dataclass
class DiffResult:
    scenario_a_id: str
    scenario_b_id: str
    scenario_a_name: str
    scenario_b_name: str
    input_deltas: list[InputDelta] = field(default_factory=list)
    kpi_deltas: list[KPIDelta] = field(default_factory=list)
    summary: str = ""  # narrative one-liner


# Metrics where higher = better
_HIGHER_IS_BETTER: frozenset[str] = frozenset({
    "revenue_y1",
    "ebitda_margin_end",
    "enterprise_value",
    "irr_project",
    "irr_equity",
    "cash_end",
})

# Metrics where lower = better
_LOWER_IS_BETTER: frozenset[str] = frozenset({
    "total_capex",
    "lcoe",
    "payback_years",
})


def diff_scenarios(
    scenario_a: dict[str, Any],
    scenario_b: dict[str, Any],
    scenario_a_id: str = "A",
    scenario_b_id: str = "B",
    scenario_a_name: str = "Scenario A",
    scenario_b_name: str = "Scenario B",
) -> DiffResult:
    """Compare two scenario result dicts and return a structured DiffResult.

    Parameters
    ----------
    scenario_a, scenario_b:
        Dicts as returned by ``results_snapshot``.  Expected top-level keys:
        ``inputs_resolved``, ``summary``, and optionally ``project_kpis``.
    scenario_a_id, scenario_b_id:
        Short identifiers (used in the result struct).
    scenario_a_name, scenario_b_name:
        Human-readable labels used in the narrative summary.

    Returns
    -------
    DiffResult
    """
    # 1. Input deltas from inputs_resolved
    input_deltas = _diff_inputs(
        scenario_a.get("inputs_resolved", {}),
        scenario_b.get("inputs_resolved", {}),
    )

    # 2. KPI deltas — merge summary + project_kpis for each scenario
    summary_a: dict[str, Any] = dict(scenario_a.get("summary", {}))
    summary_b: dict[str, Any] = dict(scenario_b.get("summary", {}))

    kpis_a = scenario_a.get("project_kpis", {})
    kpis_b = scenario_b.get("project_kpis", {})
    if isinstance(kpis_a, dict):
        summary_a = {**summary_a, **kpis_a}
    if isinstance(kpis_b, dict):
        summary_b = {**summary_b, **kpis_b}

    kpi_deltas = _diff_kpis(summary_a, summary_b)

    # 3. Narrative summary
    improved = [d for d in kpi_deltas if d.direction == "improved"]
    worsened = [d for d in kpi_deltas if d.direction == "worsened"]
    parts: list[str] = []
    if improved:
        parts.append(f"{len(improved)} metrics improved")
    if worsened:
        parts.append(f"{len(worsened)} metrics worsened")
    parts.append(f"{len(input_deltas)} inputs changed")
    narrative = f"{scenario_b_name} vs {scenario_a_name}: {', '.join(parts)}."

    return DiffResult(
        scenario_a_id=scenario_a_id,
        scenario_b_id=scenario_b_id,
        scenario_a_name=scenario_a_name,
        scenario_b_name=scenario_b_name,
        input_deltas=input_deltas,
        kpi_deltas=kpi_deltas,
        summary=narrative,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _diff_inputs(
    inputs_a: dict[str, Any],
    inputs_b: dict[str, Any],
    prefix: str = "",
) -> list[InputDelta]:
    """Recursively compare two inputs dicts and return a flat list of deltas."""
    deltas: list[InputDelta] = []
    all_keys = sorted(set(inputs_a.keys()) | set(inputs_b.keys()))
    for key in all_keys:
        path = f"{prefix}.{key}" if prefix else key
        val_a = inputs_a.get(key)
        val_b = inputs_b.get(key)
        if isinstance(val_a, dict) and isinstance(val_b, dict):
            deltas.extend(_diff_inputs(val_a, val_b, path))
        elif isinstance(val_a, list) and isinstance(val_b, list):
            if val_a != val_b:
                deltas.append(InputDelta(field_path=path, value_a=val_a, value_b=val_b, change=None))
        elif val_a != val_b:
            change: float | None = None
            if isinstance(val_a, (int, float)) and isinstance(val_b, (int, float)):
                change = float(val_b) - float(val_a)
            deltas.append(InputDelta(field_path=path, value_a=val_a, value_b=val_b, change=change))
    return deltas


def _diff_kpis(
    summary_a: dict[str, Any],
    summary_b: dict[str, Any],
) -> list[KPIDelta]:
    """Compare numeric KPIs between two summary dicts."""
    deltas: list[KPIDelta] = []
    all_keys = sorted(set(summary_a.keys()) | set(summary_b.keys()))
    for key in all_keys:
        val_a = summary_a.get(key)
        val_b = summary_b.get(key)
        if not isinstance(val_a, (int, float)) or not isinstance(val_b, (int, float)):
            continue
        if val_a == val_b:
            continue
        change = float(val_b) - float(val_a)
        change_pct = change / abs(float(val_a)) if val_a != 0 else 0.0

        if key in _HIGHER_IS_BETTER:
            direction = "improved" if change > 0 else "worsened"
        elif key in _LOWER_IS_BETTER:
            direction = "improved" if change < 0 else "worsened"
        else:
            direction = "changed"

        deltas.append(KPIDelta(
            metric=key,
            value_a=float(val_a),
            value_b=float(val_b),
            change=change,
            change_pct=change_pct,
            direction=direction,
        ))
    return deltas
