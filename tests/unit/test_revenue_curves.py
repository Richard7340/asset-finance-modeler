"""Tests for curve-driven arbitrage/ancillary revenue streams (Task 4)."""

from asset_finance_modeler.assets.infrastructure.engines.revenue import (
    _ancillary,
    _arbitrage,
    _merchant,
)
from asset_finance_modeler.assets.infrastructure.schema import (
    AncillaryStream,
    ArbitrageStream,
    MerchantStream,
)


def test_arbitrage_stream_curve_fields_optional() -> None:
    assert ArbitrageStream(avg_spread_eur_mwh=82).spread_curve_name is None
    assert ArbitrageStream(avg_spread_eur_mwh=82).spread_points is None
    assert (
        ArbitrageStream(avg_spread_eur_mwh=82, spread_curve_name="spread_da_es").spread_curve_name
        == "spread_da_es"
    )
    assert ArbitrageStream(avg_spread_eur_mwh=82, spread_points=[80.0, 90.0]).spread_points == [
        80.0,
        90.0,
    ]


def test_ancillary_stream_curve_fields_optional() -> None:
    assert AncillaryStream(fcr_eur_mw_yr=10_000).curve_points is None
    assert AncillaryStream(fcr_eur_mw_yr=10_000, curve_points=[1.0, 1.1]).curve_points == [
        1.0,
        1.1,
    ]


def _monthly_prod(years: int) -> dict[str, object]:
    periods = years * 12
    return {
        "production_mwh": [100.0] * periods,
        "capacity_mw": 10.0,
        "energy_capacity_mwh": 20.0,
    }


def test_arbitrage_curve_produces_non_flat_series() -> None:
    years = 30
    periods = years * 12
    ppy = 12
    prod = _monthly_prod(years)

    flat = _arbitrage(
        ArbitrageStream(avg_spread_eur_mwh=82),
        prod,
        capacity_mw=10.0,
        periods=periods,
        ppy=ppy,
    )
    curved = _arbitrage(
        ArbitrageStream(avg_spread_eur_mwh=82, spread_curve_name="spread_da_es"),
        prod,
        capacity_mw=10.0,
        periods=periods,
        ppy=ppy,
    )

    # Flat scalar spread => constant across all years (degradation is flat here).
    yearly_flat = [flat[y * ppy] for y in range(years)]
    assert all(v == yearly_flat[0] for v in yearly_flat)

    # Curved spread (spread_da_es) grows then decays => non-flat across years.
    yearly_curved = [curved[y * ppy] for y in range(years)]
    assert yearly_curved[6] > yearly_curved[0]
    assert yearly_curved[29] != yearly_curved[0]


def test_arbitrage_spread_points_used() -> None:
    years = 2
    periods = years * 12
    ppy = 12
    prod = _monthly_prod(years)

    scalar = _arbitrage(
        ArbitrageStream(avg_spread_eur_mwh=100.0),
        prod,
        capacity_mw=10.0,
        periods=periods,
        ppy=ppy,
    )
    points = _arbitrage(
        ArbitrageStream(avg_spread_eur_mwh=100.0, spread_points=[100.0, 200.0]),
        prod,
        capacity_mw=10.0,
        periods=periods,
        ppy=ppy,
    )

    # Year 0 (period 0): both use 100 spread => equal.
    assert points[0] == scalar[0]
    # Year 1 (period 12): points uses 200 => double the year-0 value.
    assert points[12] == points[0] * 2.0


def test_merchant_stream_curve_fields_optional() -> None:
    m = MerchantStream(base_price_eur_per_unit=36.0)
    assert m.price_curve_name is None
    assert m.price_points is None
    assert (
        MerchantStream(
            base_price_eur_per_unit=36.0, price_curve_name="solar_capture_es"
        ).price_curve_name
        == "solar_capture_es"
    )


def test_merchant_falls_back_to_base_escalation_when_no_curve() -> None:
    years = 2
    periods = years * 12
    ppy = 12
    prod = [1000.0] * periods
    series = _merchant(
        MerchantStream(
            base_price_eur_per_unit=50.0,
            volume_fraction=1.0,
            capture_ratio=0.85,
            escalation_pct_yr=0.0,
        ),
        prod,
        periods,
        ppy,
    )
    # 1000 * 1.0 * 50 * 0.85 = 42_500, flat (no escalation).
    assert series[0] == 42_500.0
    assert series[12] == 42_500.0


def test_merchant_price_points_drive_capture_directly() -> None:
    years = 2
    periods = years * 12
    ppy = 12
    prod = [1000.0] * periods
    series = _merchant(
        MerchantStream(
            base_price_eur_per_unit=50.0,  # ignored when curve present
            volume_fraction=1.0,
            capture_ratio=0.85,  # NOT re-applied on top of the curve
            escalation_pct_yr=0.0,
            price_points=[36.0, 30.0],
        ),
        prod,
        periods,
        ppy,
    )
    # Year 0 uses 36 directly; year 1 uses 30 directly.
    assert series[0] == 1000.0 * 36.0
    assert series[12] == 1000.0 * 30.0


def test_merchant_library_curve_non_flat_and_curve_driven() -> None:
    years = 30
    periods = years * 12
    ppy = 12
    prod = [1000.0] * periods
    series = _merchant(
        MerchantStream(
            base_price_eur_per_unit=36.0,
            volume_fraction=1.0,
            price_curve_name="solar_capture_es",
        ),
        prod,
        periods,
        ppy,
    )
    yearly = [series[y * ppy] for y in range(years)]
    # solar_capture_es starts at 36 and decays => non-flat, monotonically lower.
    assert yearly[0] == 1000.0 * 36.0
    assert yearly[29] < yearly[0]


def test_ancillary_curve_points_multiply_base() -> None:
    years = 2
    periods = years * 12
    ppy = 12

    flat = _ancillary(
        AncillaryStream(fcr_eur_mw_yr=12_000),
        capacity_mw=10.0,
        periods=periods,
        ppy=ppy,
    )
    curved = _ancillary(
        AncillaryStream(fcr_eur_mw_yr=12_000, curve_points=[1.0, 1.5]),
        capacity_mw=10.0,
        periods=periods,
        ppy=ppy,
    )

    assert curved[0] == flat[0]
    assert curved[12] == flat[12] * 1.5
