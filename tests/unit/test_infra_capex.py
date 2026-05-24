import pytest

from asset_finance_modeler.assets.infrastructure.engines.capex import compute_capex
from asset_finance_modeler.assets.infrastructure.schema import (
    BESSProduction,
    CAPEXBreakdown,
    InfraCapexItem,
    SolarProduction,
    WindProduction,
)


def test_solar_capex_wp():
    capex = CAPEXBreakdown(
        items=[InfraCapexItem(name="EPC", amount_per_unit=0.45, unit="Wp", depreciation_years=25)],
        contingency_pct=0.10,
    )
    prod = SolarProduction(capacity_mwp=50)
    out = compute_capex(capex, prod, periods=300, periods_per_year=12)
    raw = 0.45 * 50_000_000
    expected_total = raw * 1.10
    assert out["total_capex"] == pytest.approx(expected_total)
    assert out["capex_spend"][0] == pytest.approx(expected_total)
    assert sum(out["capex_spend"][1:]) == 0


def test_bess_capex_kwh():
    capex = CAPEXBreakdown(
        items=[InfraCapexItem(name="Battery", amount_per_unit=250, unit="kWh", depreciation_years=15)],
        contingency_pct=0,
    )
    prod = BESSProduction(power_mw=20, duration_hours=4)
    out = compute_capex(capex, prod, periods=180, periods_per_year=12)
    expected = 250 * 20 * 4 * 1000
    assert out["total_capex"] == pytest.approx(expected)


def test_capex_with_extras():
    capex = CAPEXBreakdown(
        items=[InfraCapexItem(name="EPC", amount_per_unit=800_000, unit="MW")],
        contingency_pct=0.05,
        development_cost=200_000,
        grid_connection_cost=500_000,
    )
    prod = SolarProduction(capacity_mwp=10)
    out = compute_capex(capex, prod, periods=120, periods_per_year=12)
    raw = 800_000 * 10
    expected = raw * 1.05 + 200_000 + 500_000
    assert out["total_capex"] == pytest.approx(expected)


def test_depreciation_present():
    capex = CAPEXBreakdown(
        items=[InfraCapexItem(name="EPC", amount_per_unit=1_000_000, unit="MW", depreciation_years=20)],
    )
    prod = SolarProduction(capacity_mwp=10)
    out = compute_capex(capex, prod, periods=240, periods_per_year=12)
    assert len(out["book_depreciation"]) == 240
    assert out["book_depreciation"][0] > 0
    assert sum(out["book_depreciation"]) == pytest.approx(out["total_capex"], rel=0.05)


def test_explicit_quantity():
    capex = CAPEXBreakdown(
        items=[InfraCapexItem(name="Custom", amount_per_unit=100, unit="unit", quantity=1000)],
        contingency_pct=0,
    )
    prod = SolarProduction(capacity_mwp=50)
    out = compute_capex(capex, prod, periods=120, periods_per_year=12)
    assert out["total_capex"] == pytest.approx(100_000)


# ---------------------------------------------------------------------------
# Additional tests
# ---------------------------------------------------------------------------


def test_capex_spend_length():
    capex = CAPEXBreakdown(
        items=[InfraCapexItem(name="EPC", amount_per_unit=1_000_000, unit="MW")],
    )
    prod = SolarProduction(capacity_mwp=10)
    out = compute_capex(capex, prod, periods=60, periods_per_year=12)
    assert len(out["capex_spend"]) == 60
    assert len(out["book_depreciation"]) == 60
    assert len(out["tax_depreciation"]) == 60
    assert len(out["fixed_assets_net"]) == 60


def test_fixed_assets_net_declining():
    capex = CAPEXBreakdown(
        items=[InfraCapexItem(name="EPC", amount_per_unit=1_000_000, unit="MW", depreciation_years=10)],
        contingency_pct=0,
    )
    prod = SolarProduction(capacity_mwp=5)
    out = compute_capex(capex, prod, periods=120, periods_per_year=12)
    net = out["fixed_assets_net"]
    assert net[0] < out["total_capex"]
    assert net[-1] >= 0.0
    # Should be non-increasing
    assert all(net[i] >= net[i + 1] for i in range(len(net) - 1))


def test_zero_contingency_no_extras():
    capex = CAPEXBreakdown(
        items=[InfraCapexItem(name="Turbines", amount_per_unit=1_500_000, unit="MW", quantity=10)],
        contingency_pct=0,
    )
    prod = SolarProduction(capacity_mwp=10)
    out = compute_capex(capex, prod, periods=120, periods_per_year=12)
    assert out["total_capex"] == pytest.approx(15_000_000)


def test_mw_unit_uses_capacity_mwp():
    capex = CAPEXBreakdown(
        items=[InfraCapexItem(name="Turbines", amount_per_unit=1_000_000, unit="MW")],
        contingency_pct=0,
    )
    prod = WindProduction(capacity_mw=30)
    out = compute_capex(capex, prod, periods=120, periods_per_year=12)
    assert out["total_capex"] == pytest.approx(30_000_000)


def test_tax_depreciation_length_matches_periods():
    capex = CAPEXBreakdown(
        items=[InfraCapexItem(name="EPC", amount_per_unit=1_000_000, unit="MW", depreciation_years=5)],
        contingency_pct=0,
    )
    prod = SolarProduction(capacity_mwp=10)
    out = compute_capex(capex, prod, periods=120, periods_per_year=12)
    assert len(out["tax_depreciation"]) == 120
