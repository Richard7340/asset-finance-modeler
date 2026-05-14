import pytest

from asset_finance_modeler.core.scenario import Scenario, new_scenario_id, run_scenario_saas
from asset_finance_modeler.store.compare import compare_scenarios


def _persisted_results(scenario: Scenario) -> Scenario:
    """Run and stash summary into results_snapshot."""
    results = run_scenario_saas(scenario)
    scenario.results_snapshot = {"summary": dict(results.summary)}
    return scenario


def test_compare_two_scenarios_returns_delta_table():
    base = _persisted_results(Scenario(
        id=new_scenario_id(), name="baseline", base_model="gestnova", overrides={},
    ))
    cheaper = _persisted_results(Scenario(
        id=new_scenario_id(), name="pricing-200", base_model="gestnova",
        overrides={"revenue.sources[0].pricing.per_unit_per_period": 200},
    ))
    table = compare_scenarios([base, cheaper])

    assert table["scenarios"] == ["baseline", "pricing-200"]
    assert "revenue_y1" in table["metrics"]
    # Cheaper price → lower revenue
    base_rev = table["metrics"]["revenue_y1"][0]
    cheap_rev = table["metrics"]["revenue_y1"][1]
    assert cheap_rev < base_rev


def test_compare_with_metric_filter():
    a = _persisted_results(Scenario(
        id=new_scenario_id(), name="a", base_model="gestnova", overrides={},
    ))
    table = compare_scenarios([a], metrics=["revenue_y1", "cash_end"])
    assert set(table["metrics"].keys()) == {"revenue_y1", "cash_end"}


def test_compare_missing_results_raises():
    s = Scenario(id=new_scenario_id(), name="x", base_model="gestnova", overrides={})
    with pytest.raises(ValueError, match="results_snapshot"):
        compare_scenarios([s])
