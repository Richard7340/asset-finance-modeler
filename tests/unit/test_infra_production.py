import pytest

from asset_finance_modeler.assets.infrastructure.engines.production import compute_production
from asset_finance_modeler.assets.infrastructure.schema import (
    BESSProduction,
    BiomethaneProduction,
    DataCenterProduction,
    GenericProduction,
    H2Production,
    SolarProduction,
    WindProduction,
)


def test_solar_production():
    cfg = SolarProduction(capacity_mwp=50)
    deg = [1.0] * 240
    out = compute_production(cfg, deg, periods=240, periods_per_year=12)
    expected = 50 * 1000 * 1500 * 0.82 / 1000 / 12  # monthly MWh
    assert out["production_mwh"][0] == pytest.approx(expected, rel=0.01)
    assert out["capacity_mw"] == pytest.approx(50)
    assert len(out["production_mwh"]) == 240


def test_solar_with_degradation():
    cfg = SolarProduction(capacity_mwp=10)
    deg = [1.0] * 12 + [0.995] * 12
    out = compute_production(cfg, deg, periods=24, periods_per_year=12)
    assert out["production_mwh"][12] < out["production_mwh"][0]


def test_wind_production():
    cfg = WindProduction(capacity_mw=30)
    deg = [1.0] * 120
    out = compute_production(cfg, deg, periods=120, periods_per_year=12)
    hours = 8760 / 12
    expected = 30 * 0.28 * 0.97 * (1 - 0.05) * hours
    assert out["production_mwh"][0] == pytest.approx(expected, rel=0.01)


def test_bess_production():
    cfg = BESSProduction(power_mw=20, duration_hours=4, cycles_per_day=1.5)
    deg = [1.0] * 120
    out = compute_production(cfg, deg, periods=120, periods_per_year=12)
    assert out["production_mwh"][0] > 0
    assert out["capacity_mw"] == 20
    assert "energy_capacity_mwh" in out


def test_h2_production():
    cfg = H2Production(electrolyzer_mw=10)
    deg = [1.0] * 120
    out = compute_production(cfg, deg, periods=120, periods_per_year=12)
    assert "production_kg" in out
    assert out["production_kg"][0] > 0


def test_biomethane_production():
    cfg = BiomethaneProduction(capacity_nm3_h=500)
    deg = [1.0] * 60
    out = compute_production(cfg, deg, periods=60, periods_per_year=12)
    assert "production_nm3" in out
    assert out["production_nm3"][0] > 0


def test_datacenter_production():
    cfg = DataCenterProduction(it_capacity_mw=10, pue=1.3)
    deg = [1.0] * 60
    out = compute_production(cfg, deg, periods=60, periods_per_year=12)
    assert out["capacity_mw"] == pytest.approx(13.0)
    assert "capacity_mw_it" in out


def test_generic_production():
    cfg = GenericProduction(units=100, output_per_unit_per_period=50)
    deg = [1.0] * 60
    out = compute_production(cfg, deg, periods=60, periods_per_year=12)
    assert out["production_mwh"][0] == pytest.approx(5000)


# ---------------------------------------------------------------------------
# Additional edge-case tests
# ---------------------------------------------------------------------------


def test_solar_returns_correct_length():
    cfg = SolarProduction(capacity_mwp=100)
    deg = [1.0] * 60
    out = compute_production(cfg, deg, periods=60, periods_per_year=12)
    assert len(out["production_mwh"]) == 60


def test_wind_degradation_applied():
    cfg = WindProduction(capacity_mw=10)
    deg = [1.0] * 12 + [0.99] * 12
    out = compute_production(cfg, deg, periods=24, periods_per_year=12)
    assert out["production_mwh"][12] < out["production_mwh"][0]


def test_bess_energy_capacity():
    cfg = BESSProduction(power_mw=20, duration_hours=4)
    deg = [1.0] * 12
    out = compute_production(cfg, deg, periods=12, periods_per_year=12)
    assert out["energy_capacity_mwh"] == pytest.approx(80.0)


def test_h2_production_mwh_is_electricity_consumed():
    cfg = H2Production(electrolyzer_mw=10, availability=0.95)
    deg = [1.0] * 12
    out = compute_production(cfg, deg, periods=12, periods_per_year=12)
    # electricity consumed per period: 10 MW * 0.95 * (8760/12) hours
    hours = 8760 / 12
    expected_mwh = 10 * 0.95 * hours
    assert out["production_mwh"][0] == pytest.approx(expected_mwh, rel=0.01)


def test_biomethane_mwh_approx():
    cfg = BiomethaneProduction(capacity_nm3_h=500)
    deg = [1.0] * 12
    out = compute_production(cfg, deg, periods=12, periods_per_year=12)
    # mwh ≈ nm3 × 0.01
    assert abs(out["production_mwh"][0] - out["production_nm3"][0] * 0.01) < 1e-6


def test_datacenter_rack_count():
    cfg = DataCenterProduction(it_capacity_mw=10, rack_density_kw=10)
    deg = [1.0] * 12
    out = compute_production(cfg, deg, periods=12, periods_per_year=12)
    assert out["rack_count"] == pytest.approx(1000.0)


def test_datacenter_production_mwh_all_zeros():
    cfg = DataCenterProduction(it_capacity_mw=5, pue=1.2)
    deg = [1.0] * 12
    out = compute_production(cfg, deg, periods=12, periods_per_year=12)
    assert all(v == 0.0 for v in out["production_mwh"])


def test_generic_degradation_applied():
    cfg = GenericProduction(units=100, output_per_unit_per_period=50)
    deg = [1.0] * 12 + [0.98] * 12
    out = compute_production(cfg, deg, periods=24, periods_per_year=12)
    assert out["production_mwh"][12] < out["production_mwh"][0]
