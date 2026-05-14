import pytest
from pydantic import ValidationError

from asset_finance_modeler.assets.saas.schema import (
    AcquisitionConfig,
    PricingConfig,
    RetentionConfig,
    RevenueConfig,
    RevenueSource,
)


def test_pricing_basic():
    p = PricingConfig(per_unit_per_period=300, setup_one_time=1000)
    assert p.per_unit_per_period == 300
    assert p.price_escalation_annual == 0


def test_acquisition_basic():
    a = AcquisitionConfig(
        new_units_per_period=[1, 2, 3, 4, 5],
        avg_units_per_customer=2.5,
        cac_per_customer=800,
    )
    assert a.cac_payback_target_months == 12


def test_retention_default_grr():
    r = RetentionConfig(monthly_churn_rate=0.02)
    assert r.gross_revenue_retention == 1.0


def test_retention_churn_out_of_range():
    with pytest.raises(ValidationError):
        RetentionConfig(monthly_churn_rate=1.5)


def test_revenue_source_complete():
    s = RevenueSource(
        name="agent_subscriptions",
        pricing=PricingConfig(per_unit_per_period=300),
        acquisition=AcquisitionConfig(
            new_units_per_period=5,
            avg_units_per_customer=2.5,
            cac_per_customer=800,
        ),
        retention=RetentionConfig(monthly_churn_rate=0.02),
    )
    assert s.name == "agent_subscriptions"


def test_revenue_config_requires_at_least_one_source():
    with pytest.raises(ValidationError):
        RevenueConfig(sources=[])
