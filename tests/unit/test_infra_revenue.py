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


def test_arbitrage_cycles_single_source_of_truth():
    """P3-5: BESS production cycles_per_day is the single source of truth.

    The ArbitrageStream's own cycles_per_day must NOT silently override the
    battery's configured cycles — when BESS production provides cycles, the
    arbitrage revenue keys off the production value so the two cannot diverge.
    """
    from asset_finance_modeler.assets.infrastructure.engines.production import (
        compute_production,
    )
    from asset_finance_modeler.assets.infrastructure.schema import (
        ArbitrageStream,
        BESSProduction,
    )

    deg = [1.0] * 12
    bess_cfg = BESSProduction(power_mw=20, duration_hours=4, cycles_per_day=0.9)
    prod = compute_production(bess_cfg, deg, 12, 12)

    # Arbitrage stream left at its default (1.5) — must be ignored in favour of
    # the production's 0.9, so revenue matches the 0.9 case, not 1.5.
    arb_default = [ArbitrageStream(avg_spread_eur_mwh=40)]
    arb_matching = [ArbitrageStream(avg_spread_eur_mwh=40, cycles_per_day=0.9)]
    rev_default = compute_revenue(arb_default, prod, 12, 12)["total_revenue"][0]
    rev_matching = compute_revenue(arb_matching, prod, 12, 12)["total_revenue"][0]
    assert rev_default == pytest.approx(rev_matching)


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


# ---------------------------------------------------------------------------
# FIX 3: tenor_years on contracted streams (PPA / Offtake)
# ---------------------------------------------------------------------------


def test_ppa_tenor_reverts_to_zero_when_no_merchant():
    """A PPA with tenor_years=3 over a 5-year horizon: years 1-3 contracted,
    years 4-5 revert to 0 (no merchant fallback stream present)."""
    streams = [
        PPAStream(price_eur_per_unit=50.0, volume_fraction=1.0,
                  escalation_pct_yr=0, tenor_years=3)
    ]
    prod = {"production_mwh": [1000.0] * 60, "capacity_mw": 10}
    out = compute_revenue(streams, prod, periods=60, periods_per_year=12)
    rev = out["total_revenue"]
    # Year 1 (period 0) contracted: 1000 * 1.0 * 50
    assert rev[0] == pytest.approx(50_000)
    # Last month of year 3 (period 35) still contracted
    assert rev[35] == pytest.approx(50_000)
    # Year 4 (period 36) reverts to 0 (no merchant)
    assert rev[36] == pytest.approx(0.0)
    assert rev[59] == pytest.approx(0.0)


def test_ppa_tenor_geq_horizon_unchanged():
    """tenor_years >= horizon → identical to the no-tenor behaviour (regression
    guard: default tenor 15 over a 1-year horizon must not change anything)."""
    streams_long = [
        PPAStream(price_eur_per_unit=50.0, volume_fraction=1.0,
                  escalation_pct_yr=0.02, tenor_years=100)
    ]
    prod = {"production_mwh": [1000.0] * 24, "capacity_mw": 10}
    out = compute_revenue(streams_long, prod, periods=24, periods_per_year=12)
    rev = out["total_revenue"]
    # 2-year horizon, tenor 100 -> escalation applies normally, never truncated
    assert rev[0] == pytest.approx(50_000)
    assert rev[12] == pytest.approx(50_000 * 1.02)


def test_ppa_tenor_reverts_to_merchant_price():
    """After the PPA tenor expires, the contracted volume is sold at the
    merchant per-year price (a merchant stream exists in the model)."""
    streams = [
        PPAStream(price_eur_per_unit=50.0, volume_fraction=0.7,
                  escalation_pct_yr=0, tenor_years=2),
        MerchantStream(base_price_eur_per_unit=30.0, volume_fraction=0.3,
                       capture_ratio=1.0, escalation_pct_yr=0),
    ]
    prod = {"production_mwh": [1000.0] * 48, "capacity_mw": 10}
    out = compute_revenue(streams, prod, periods=48, periods_per_year=12)
    ppa = out["streams"]["PPA"]
    # Years 1-2 contracted: 1000 * 0.7 * 50 = 35000
    assert ppa[0] == pytest.approx(35_000)
    assert ppa[23] == pytest.approx(35_000)
    # Year 3 onward: PPA volume reverts to merchant price 30 -> 1000 * 0.7 * 30
    assert ppa[24] == pytest.approx(21_000)
    assert ppa[47] == pytest.approx(21_000)


def test_offtake_tenor_reverts_to_zero():
    """H2/biomethane offtake reverts to 0 after tenor (no merchant fallback)."""
    streams = [
        OfftakeStream(price_eur_per_unit=5.0, volume_fraction=1.0,
                      escalation_pct_yr=0, tenor_years=1)
    ]
    prod = {"production_mwh": [2000.0] * 36, "capacity_mw": 20}
    out = compute_revenue(streams, prod, periods=36, periods_per_year=12)
    rev = out["total_revenue"]
    assert rev[0] == pytest.approx(10_000)
    assert rev[11] == pytest.approx(10_000)
    assert rev[12] == pytest.approx(0.0)
