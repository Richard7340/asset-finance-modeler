from asset_finance_modeler.core.scenario import Scenario, new_scenario_id


def test_scenario_lifecycle_defaults():
    s = Scenario(id=new_scenario_id(), name="X", base_model="bess_20mw_4h")
    assert s.lifecycle == "opportunity"
    assert s.commissioning_date is None
    assert s.base_locked is False
    assert s.tracking_frequency is None


def test_scenario_lifecycle_operational():
    from datetime import UTC, datetime

    s = Scenario(
        id=new_scenario_id(),
        name="Planta",
        base_model="solar_pv_50mw_spain",
        lifecycle="operational",
        commissioning_date=datetime(2026, 1, 1, tzinfo=UTC),
        base_locked=True,
        tracking_frequency="monthly",
    )
    assert s.lifecycle == "operational"
    assert s.commissioning_date.year == 2026
    assert s.base_locked is True
    assert s.tracking_frequency == "monthly"
