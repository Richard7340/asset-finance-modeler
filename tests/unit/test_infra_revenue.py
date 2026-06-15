import pytest

from asset_finance_modeler.assets.infrastructure.engines.revenue import compute_revenue
from asset_finance_modeler.assets.infrastructure.schema import (
    AncillaryStream,
    ArbitrageStream,
    CapacityStream,
    CertificateStream,
    MerchantStream,
    OfftakeStream,
    PPAStream,
    RentalStream,
    SLAStream,
)


def test_ppa_revenue():
    streams = [PPAStream(price_eur_per_unit=45.0, volume_fraction=1.0, escalation_pct_yr=0)]
    prod = {"production_mwh": [5000.0] * 12, "capacity_mw": 50}
    out = compute_revenue(streams, prod, periods=12, periods_per_year=12)
    assert out["total_revenue"][0] == pytest.approx(225_000)
    assert "PPA" in out["streams"]


def test_merchant_revenue_with_capture():
    streams = [
        MerchantStream(
            base_price_eur_per_unit=50.0,
            volume_fraction=1.0,
            capture_ratio=0.85,
            escalation_pct_yr=0,
        )
    ]
    prod = {"production_mwh": [1000.0] * 12, "capacity_mw": 10}
    out = compute_revenue(streams, prod, periods=12, periods_per_year=12)
    assert out["total_revenue"][0] == pytest.approx(42_500)


def test_capacity_revenue():
    streams = [CapacityStream(eur_per_mw_yr=35_000)]
    prod = {"production_mwh": [0.0] * 12, "capacity_mw": 20}
    out = compute_revenue(streams, prod, periods=12, periods_per_year=12)
    assert out["total_revenue"][0] == pytest.approx(35_000 * 20 / 12, rel=0.01)


def test_multiple_streams():
    streams = [
        PPAStream(price_eur_per_unit=45.0, volume_fraction=0.7, escalation_pct_yr=0),
        MerchantStream(base_price_eur_per_unit=50.0, volume_fraction=0.3, capture_ratio=0.90, escalation_pct_yr=0),
    ]
    prod = {"production_mwh": [1000.0] * 12, "capacity_mw": 10}
    out = compute_revenue(streams, prod, periods=12, periods_per_year=12)
    ppa_rev = 1000 * 0.7 * 45
    merchant_rev = 1000 * 0.3 * 50 * 0.90
    assert out["total_revenue"][0] == pytest.approx(ppa_rev + merchant_rev)


def test_escalation():
    streams = [PPAStream(price_eur_per_unit=100.0, volume_fraction=1.0, escalation_pct_yr=0.02)]
    prod = {"production_mwh": [1000.0] * 24, "capacity_mw": 10}
    out = compute_revenue(streams, prod, periods=24, periods_per_year=12)
    assert out["total_revenue"][12] > out["total_revenue"][0]


# ---------------------------------------------------------------------------
# Additional tests
# ---------------------------------------------------------------------------


def test_ppa_zero_production():
    streams = [PPAStream(price_eur_per_unit=50.0, volume_fraction=1.0, escalation_pct_yr=0)]
    prod = {"production_mwh": [0.0] * 12, "capacity_mw": 10}
    out = compute_revenue(streams, prod, periods=12, periods_per_year=12)
    assert all(v == 0.0 for v in out["total_revenue"])


def test_streams_dict_keys():
    streams = [
        PPAStream(price_eur_per_unit=45.0),
        AncillaryStream(fcr_eur_mw_yr=10_000),
    ]
    prod = {"production_mwh": [1000.0] * 12, "capacity_mw": 10}
    out = compute_revenue(streams, prod, periods=12, periods_per_year=12)
    assert "PPA" in out["streams"]
    assert "Ancillary Services" in out["streams"]


def test_capacity_stream_constant_per_period():
    streams = [CapacityStream(eur_per_mw_yr=12_000)]
    prod = {"production_mwh": [0.0] * 12, "capacity_mw": 5}
    out = compute_revenue(streams, prod, periods=12, periods_per_year=12)
    # All periods should be equal (no escalation)
    assert all(v == pytest.approx(out["total_revenue"][0]) for v in out["total_revenue"])


def test_certificate_stream():
    streams = [CertificateStream(price_eur_per_unit=5.0, eligible_fraction=0.8)]
    prod = {"production_mwh": [1000.0] * 12, "capacity_mw": 10}
    out = compute_revenue(streams, prod, periods=12, periods_per_year=12)
    assert out["total_revenue"][0] == pytest.approx(1000 * 0.8 * 5.0)


def test_sla_stream_uses_capacity_mw_it():
    streams = [SLAStream(price_per_mw_month=1000.0)]
    prod = {"production_mwh": [0.0] * 12, "capacity_mw": 13.0, "capacity_mw_it": 10.0}
    out = compute_revenue(streams, prod, periods=12, periods_per_year=12)
    assert out["total_revenue"][0] == pytest.approx(1000.0 * 10.0)


def test_total_revenue_is_sum_of_streams():
    streams = [
        PPAStream(price_eur_per_unit=45.0, volume_fraction=0.6, escalation_pct_yr=0),
        CapacityStream(eur_per_mw_yr=20_000),
    ]
    prod = {"production_mwh": [500.0] * 12, "capacity_mw": 10}
    out = compute_revenue(streams, prod, periods=12, periods_per_year=12)
    for t in range(12):
        stream_sum = sum(v[t] for v in out["streams"].values())
        assert out["total_revenue"][t] == pytest.approx(stream_sum)


# ---------------------------------------------------------------------------
# Tests for previously uncovered stream types
# ---------------------------------------------------------------------------


def test_arbitrage_stream():
    streams = [ArbitrageStream(avg_spread_eur_mwh=40, cycles_per_day=1.5, spread_capture_ratio=0.75)]
    prod = {"production_mwh": [5000.0] * 12, "capacity_mw": 20, "energy_capacity_mwh": 80}
    out = compute_revenue(streams, prod, periods=12, periods_per_year=12)
    assert out["total_revenue"][0] > 0


def test_ancillary_stream():
    streams = [AncillaryStream(fcr_eur_mw_yr=25000, afrr_eur_mw_yr=10000)]
    prod = {"production_mwh": [0.0] * 12, "capacity_mw": 20}
    out = compute_revenue(streams, prod, periods=12, periods_per_year=12)
    expected_monthly = (25000 + 10000) * 20 / 12
    assert out["total_revenue"][0] == pytest.approx(expected_monthly, rel=0.05)


def test_offtake_stream_with_kg():
    streams = [OfftakeStream(price_eur_per_unit=5.0, volume_fraction=1.0, escalation_pct_yr=0)]
    prod = {"production_mwh": [0.0] * 12, "production_kg": [10000.0] * 12, "capacity_mw": 10}
    out = compute_revenue(streams, prod, periods=12, periods_per_year=12)
    assert out["total_revenue"][0] == pytest.approx(50000)


def test_certificate_stream_new():
    streams = [CertificateStream(price_eur_per_unit=3.0, eligible_fraction=0.8)]
    prod = {"production_mwh": [10000.0] * 12, "capacity_mw": 50}
    out = compute_revenue(streams, prod, periods=12, periods_per_year=12)
    assert out["total_revenue"][0] == pytest.approx(24000)


def test_sla_stream():
    streams = [SLAStream(price_per_mw_month=150000)]
    prod = {"production_mwh": [0.0] * 12, "capacity_mw": 13, "capacity_mw_it": 10}
    out = compute_revenue(streams, prod, periods=12, periods_per_year=12)
    assert out["total_revenue"][0] == pytest.approx(1500000)


def test_rental_stream():
    streams = [RentalStream(price_per_unit_period=5000, occupancy_rate=0.95, escalation_pct_yr=0)]
    prod = {"production_mwh": [0.0] * 12, "capacity_mw": 10}
    out = compute_revenue(streams, prod, periods=12, periods_per_year=12)
    assert out["total_revenue"][0] == pytest.approx(47500)


def test_bess_price_profile_reshapes_arbitrage_revenue():
    # P2-4: a BESS price_profile reshapes the intra-year arbitrage spread.
    from asset_finance_modeler.assets.infrastructure.engines.production import (
        compute_production,
    )
    from asset_finance_modeler.assets.infrastructure.schema import (
        ArbitrageStream,
        BESSProduction,
    )

    deg = [1.0] * 12
    profile = [0.5, 1.5] * 6  # mean 1.0
    base_cfg = BESSProduction(power_mw=20, duration_hours=4, cycles_per_day=1.5)
    shaped_cfg = BESSProduction(
        power_mw=20, duration_hours=4, cycles_per_day=1.5, price_profile=profile
    )
    arb = [ArbitrageStream(avg_spread_eur_mwh=40)]

    base_out = compute_production(base_cfg, deg, 12, 12)
    shaped_out = compute_production(shaped_cfg, deg, 12, 12)
    base_rev = compute_revenue(arb, base_out, 12, 12)["total_revenue"]
    shaped_rev = compute_revenue(arb, shaped_out, 12, 12)["total_revenue"]

    # Period 0 down (×0.5), period 1 up (×1.5); annual total preserved.
    assert shaped_rev[0] < base_rev[0]
    assert shaped_rev[1] > base_rev[1]
    assert sum(shaped_rev) == pytest.approx(sum(base_rev), rel=1e-9)
