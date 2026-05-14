from asset_finance_modeler.core.scenario import Scenario, new_scenario_id, run_scenario_saas


def sensitivity_1d(
    base_scenario: Scenario,
    variable: str,
    values: list[float],
    metric: str,
) -> dict[str, object]:
    """Run base_scenario with `variable` overridden across `values`, return
    list of {value, metric_value} points."""
    points: list[dict[str, float]] = []
    for value in values:
        # Compose: base overrides + the variable being swept
        merged = dict(base_scenario.overrides)
        merged[variable] = value
        run_s = Scenario(
            id=new_scenario_id(),
            name=f"sens-{variable}-{value}",
            base_model=base_scenario.base_model,
            overrides=merged,
        )
        results = run_scenario_saas(run_s)
        if metric not in results.summary:
            raise KeyError(f"metric {metric!r} not found in summary; available: {list(results.summary)}")
        points.append({"value": value, "metric_value": results.summary[metric]})

    return {"variable": variable, "metric": metric, "points": points}
