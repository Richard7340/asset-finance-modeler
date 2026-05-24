import pytest

from asset_finance_modeler.assets.infrastructure.engines.opex import compute_opex
from asset_finance_modeler.assets.infrastructure.schema import InfraOPEXConfig, MaintenanceEvent


def test_fixed_om():
    cfg = InfraOPEXConfig(om_fixed_eur_per_mw_yr=12_000, opex_escalation_pct_yr=0)
    out = compute_opex(
        cfg,
        capacity_mw=50,
        total_capex=20_000_000,
        production_mwh=[5000] * 12,
        periods=12,
        periods_per_year=12,
    )
    assert out["fixed_om"][0] == pytest.approx(50_000)


def test_variable_om():
    cfg = InfraOPEXConfig(om_variable_eur_per_mwh=2.5)
    out = compute_opex(
        cfg,
        capacity_mw=50,
        total_capex=0,
        production_mwh=[5000] * 12,
        periods=12,
        periods_per_year=12,
    )
    assert out["variable_om"][0] == pytest.approx(12_500)


def test_insurance():
    cfg = InfraOPEXConfig(insurance_pct_capex=0.005)
    out = compute_opex(
        cfg,
        capacity_mw=50,
        total_capex=20_000_000,
        production_mwh=[0] * 12,
        periods=12,
        periods_per_year=12,
    )
    assert out["insurance"][0] == pytest.approx(100_000 / 12, rel=0.01)


def test_maintenance_event():
    cfg = InfraOPEXConfig(major_maintenance=[MaintenanceEvent(name="Inverter", period=5, cost=500_000)])
    out = compute_opex(
        cfg,
        capacity_mw=50,
        total_capex=0,
        production_mwh=[0] * 12,
        periods=12,
        periods_per_year=12,
    )
    assert out["maintenance"][5] == pytest.approx(500_000)
    assert out["maintenance"][0] == 0


def test_recurring_maintenance():
    cfg = InfraOPEXConfig(
        major_maintenance=[
            MaintenanceEvent(name="Filter", period=6, cost=10_000, recurring_interval=6)
        ]
    )
    out = compute_opex(
        cfg,
        capacity_mw=10,
        total_capex=0,
        production_mwh=[0] * 24,
        periods=24,
        periods_per_year=12,
    )
    assert out["maintenance"][6] == pytest.approx(10_000)
    assert out["maintenance"][12] == pytest.approx(10_000)
    assert out["maintenance"][18] == pytest.approx(10_000)


def test_total_opex():
    cfg = InfraOPEXConfig(om_fixed_eur_per_mw_yr=12_000, insurance_pct_capex=0.005, opex_escalation_pct_yr=0)
    out = compute_opex(
        cfg,
        capacity_mw=50,
        total_capex=10_000_000,
        production_mwh=[5000] * 12,
        periods=12,
        periods_per_year=12,
    )
    expected = (
        out["fixed_om"][0]
        + out["variable_om"][0]
        + out["insurance"][0]
        + out["land"][0]
        + out["management"][0]
        + out["other"][0]
        + out["maintenance"][0]
    )
    assert out["total_opex"][0] == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Additional tests
# ---------------------------------------------------------------------------


def test_land_lease_escalated():
    cfg = InfraOPEXConfig(land_lease_eur_yr=12_000, opex_escalation_pct_yr=0.02)
    out = compute_opex(
        cfg,
        capacity_mw=10,
        total_capex=0,
        production_mwh=[0] * 24,
        periods=24,
        periods_per_year=12,
    )
    assert out["land"][12] > out["land"][0]


def test_management_fee():
    cfg = InfraOPEXConfig(management_fee_eur_yr=60_000, opex_escalation_pct_yr=0)
    out = compute_opex(
        cfg,
        capacity_mw=10,
        total_capex=0,
        production_mwh=[0] * 12,
        periods=12,
        periods_per_year=12,
    )
    assert out["management"][0] == pytest.approx(5_000)


def test_other_fixed():
    cfg = InfraOPEXConfig(other_fixed_eur_yr=24_000)
    out = compute_opex(
        cfg,
        capacity_mw=10,
        total_capex=0,
        production_mwh=[0] * 12,
        periods=12,
        periods_per_year=12,
    )
    assert out["other"][0] == pytest.approx(2_000)
    assert all(v == pytest.approx(2_000) for v in out["other"])


def test_maintenance_not_fired_beyond_periods():
    cfg = InfraOPEXConfig(major_maintenance=[MaintenanceEvent(name="Big overhaul", period=50, cost=1_000_000)])
    out = compute_opex(
        cfg,
        capacity_mw=10,
        total_capex=0,
        production_mwh=[0] * 12,
        periods=12,
        periods_per_year=12,
    )
    assert all(v == 0.0 for v in out["maintenance"])


def test_multiple_maintenance_events_same_period():
    cfg = InfraOPEXConfig(
        major_maintenance=[
            MaintenanceEvent(name="A", period=3, cost=100_000),
            MaintenanceEvent(name="B", period=3, cost=200_000),
        ]
    )
    out = compute_opex(
        cfg,
        capacity_mw=10,
        total_capex=0,
        production_mwh=[0] * 12,
        periods=12,
        periods_per_year=12,
    )
    assert out["maintenance"][3] == pytest.approx(300_000)


def test_zero_capex_zero_insurance():
    cfg = InfraOPEXConfig(insurance_pct_capex=0.01)
    out = compute_opex(
        cfg,
        capacity_mw=50,
        total_capex=0,
        production_mwh=[0] * 12,
        periods=12,
        periods_per_year=12,
    )
    assert all(v == 0.0 for v in out["insurance"])


def test_output_keys_present():
    cfg = InfraOPEXConfig()
    out = compute_opex(
        cfg,
        capacity_mw=10,
        total_capex=0,
        production_mwh=[0] * 12,
        periods=12,
        periods_per_year=12,
    )
    for key in ("fixed_om", "variable_om", "insurance", "land", "management", "other", "maintenance", "total_opex"):
        assert key in out
        assert len(out[key]) == 12
