import pytest

from asset_finance_modeler.assets.saas.engines import CohortRevenueEngine
from asset_finance_modeler.assets.saas.schema import (
    AcquisitionConfig,
    PricingConfig,
    RetentionConfig,
    RevenueSource,
)


def _src(churn=0.02, price=300, new_units=None, avg_units=2.5):
    if new_units is None:
        new_units = 5.0
    return RevenueSource(
        name="subs",
        pricing=PricingConfig(per_unit_per_period=price, setup_one_time=1000),
        acquisition=AcquisitionConfig(
            new_units_per_period=new_units,
            avg_units_per_customer=avg_units,
            cac_per_customer=800,
        ),
        retention=RetentionConfig(monthly_churn_rate=churn),
    )


def test_no_churn_active_units_accumulate():
    eng = CohortRevenueEngine([_src(churn=0.0, new_units=2.0)], periods=4)
    out = eng.compute()
    assert out["active_units"] == pytest.approx([2.0, 4.0, 6.0, 8.0])


def test_with_churn_retention():
    eng = CohortRevenueEngine([_src(churn=0.10, new_units=10.0)], periods=3)
    out = eng.compute()
    assert out["active_units"][0] == pytest.approx(10.0)
    assert out["active_units"][1] == pytest.approx(19.0)
    assert out["active_units"][2] == pytest.approx(27.1)


def test_revenue_components():
    eng = CohortRevenueEngine([_src(churn=0.0, new_units=2.0, price=300, avg_units=2.5)], periods=3)
    out = eng.compute()
    assert out["subscription_revenue"][0] == pytest.approx(600.0)
    assert out["setup_revenue"][0] == pytest.approx(800.0)


def test_active_customers():
    eng = CohortRevenueEngine([_src(churn=0.0, new_units=5.0, avg_units=2.5)], periods=3)
    out = eng.compute()
    assert out["active_customers"] == pytest.approx([2.0, 4.0, 6.0])
