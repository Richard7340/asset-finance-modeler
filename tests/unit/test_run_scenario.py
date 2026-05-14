from asset_finance_modeler.core.scenario import Scenario, new_scenario_id, run_scenario_saas


def test_run_scenario_baseline_no_overrides():
    s = Scenario(id=new_scenario_id(), name="baseline", base_model="gestnova", overrides={})
    results = run_scenario_saas(s)
    assert results.summary["revenue_y1"] > 0
    # Snapshot fields populated
    assert "revenue" in results.pnl


def test_run_scenario_with_override_changes_revenue():
    base = Scenario(id=new_scenario_id(), name="baseline", base_model="gestnova", overrides={})
    base_results = run_scenario_saas(base)

    cheaper = Scenario(
        id=new_scenario_id(),
        name="pricing-200",
        base_model="gestnova",
        overrides={"revenue.sources[0].pricing.per_unit_per_period": 200},
    )
    cheap_results = run_scenario_saas(cheaper)

    # Lower price → lower revenue
    assert cheap_results.summary["revenue_end_period"] < base_results.summary["revenue_end_period"]


def test_run_scenario_changes_horizon():
    s = Scenario(
        id=new_scenario_id(),
        name="short-horizon",
        base_model="gestnova",
        overrides={"meta.horizon.periods": 12},
    )
    results = run_scenario_saas(s)
    assert len(results.pnl["revenue"]) == 12
