from asset_finance_modeler.core.scenario import Scenario

_DEFAULT_METRICS = [
    "revenue_y1",
    "revenue_end_period",
    "ebitda_margin_end",
    "active_customers_end",
    "cash_end",
    "runway_months",
    "ltv_cac_end",
    "enterprise_value",
]


def compare_scenarios(
    scenarios: list[Scenario],
    metrics: list[str] | None = None,
) -> dict[str, object]:
    """Return a comparison table.

    Output shape:
        {
            "scenarios": [name1, name2, ...],
            "metrics": {
                "revenue_y1": [val1, val2, ...],
                ...
            }
        }
    Each scenario must have a populated results_snapshot["summary"].
    """
    if not scenarios:
        return {"scenarios": [], "metrics": {}}

    selected = metrics if metrics is not None else _DEFAULT_METRICS
    names: list[str] = []
    metric_rows: dict[str, list[float | int | None]] = {m: [] for m in selected}

    for s in scenarios:
        summary = s.results_snapshot.get("summary")
        if not summary:
            raise ValueError(
                f"Scenario {s.id} ({s.name}) has no results_snapshot.summary — run it first"
            )
        names.append(s.name)
        for m in selected:
            metric_rows[m].append(summary.get(m))

    return {"scenarios": names, "metrics": metric_rows}
