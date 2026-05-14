import pytest

from asset_finance_modeler.core.scenario import Scenario, new_scenario_id
from asset_finance_modeler.store.sensitivity import sensitivity_1d


def test_sensitivity_pricing_revenue():
    base = Scenario(id=new_scenario_id(), name="b", base_model="gestnova", overrides={})
    out = sensitivity_1d(
        base,
        variable="revenue.sources[0].pricing.per_unit_per_period",
        values=[200, 250, 300, 350],
        metric="revenue_y1",
    )
    assert len(out["points"]) == 4
    # Monotonic: higher price → higher revenue
    revenues = [p["metric_value"] for p in out["points"]]
    assert revenues == sorted(revenues)


def test_sensitivity_churn_runway():
    base = Scenario(id=new_scenario_id(), name="b", base_model="gestnova", overrides={})
    out = sensitivity_1d(
        base,
        variable="revenue.sources[0].retention.monthly_churn_rate",
        values=[0.01, 0.05, 0.10],
        metric="enterprise_value",
    )
    # Higher churn → lower EV
    evs = [p["metric_value"] for p in out["points"]]
    assert evs[0] > evs[2]


def test_sensitivity_invalid_metric_raises():
    base = Scenario(id=new_scenario_id(), name="b", base_model="gestnova", overrides={})
    with pytest.raises(KeyError):
        sensitivity_1d(
            base,
            variable="revenue.sources[0].pricing.per_unit_per_period",
            values=[200, 250],
            metric="nonexistent_metric",
        )
