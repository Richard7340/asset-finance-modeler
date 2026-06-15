"""Arbitrage DoD/RTE honoring + exact first-principles units (FIX 1).

Locks two correctness properties of the BESS arbitrage revenue:

1. Changing the BESS preset's depth_of_discharge / round_trip_efficiency
   MUST change arbitrage revenue (it previously did not — the engine always
   used the hardcoded 0.90/0.88 defaults because ``_bess`` never emitted
   those keys into production_output).
2. An exact first-principles value: arbitrage Y1 equals
   energy_capacity × DoD × RTE × cycles × days × spread × capture × deg.
   This locks the units (there was historically a units bug here).
"""

import pytest

from asset_finance_modeler.assets.infrastructure.engines.production import _bess
from asset_finance_modeler.assets.infrastructure.engines.revenue import _arbitrage
from asset_finance_modeler.assets.infrastructure.schema import (
    ArbitrageStream,
    BESSProduction,
)


def test_bess_emits_dod_and_rte() -> None:
    """_bess must surface DoD/RTE so _arbitrage can honor them."""
    cfg = BESSProduction(power_mw=10.0, duration_hours=4.0,
                         depth_of_discharge=0.80, round_trip_efficiency=0.85)
    out = _bess(cfg, [1.0] * 12, 12, 12)
    assert out["depth_of_discharge"] == 0.80
    assert out["round_trip_efficiency"] == 0.85


def test_arbitrage_honors_dod_rte_from_production() -> None:
    """Different DoD/RTE in production_output => different arbitrage revenue."""
    ppy = 12
    periods = 12
    cycles = 1.0

    def prod(dod: float, rte: float) -> dict[str, object]:
        return {
            "production_mwh": [100.0] * periods,
            "capacity_mw": 10.0,
            "energy_capacity_mwh": 40.0,
            "depth_of_discharge": dod,
            "round_trip_efficiency": rte,
        }

    stream = ArbitrageStream(avg_spread_eur_mwh=80.0, cycles_per_day=cycles,
                             spread_capture_ratio=1.0)

    low = _arbitrage(stream, prod(0.80, 0.85), 10.0, periods, ppy)
    high = _arbitrage(stream, prod(0.90, 0.88), 10.0, periods, ppy)

    # Lower DoD×RTE => lower revenue (the bug made these identical).
    assert low[0] < high[0]
    # Exact ratio matches the DoD×RTE ratio.
    assert low[0] / high[0] == pytest.approx((0.80 * 0.85) / (0.90 * 0.88))


def test_arbitrage_exact_first_principles_y1() -> None:
    """Y1 arbitrage == energy_cap × DoD × RTE × cycles × days × spread × capture."""
    ppy = 12
    periods = 12
    energy_cap = 40.0
    dod = 0.80
    rte = 0.85
    cycles = 0.9
    spread = 82.0
    capture = 0.80
    days = 365.0 / ppy

    prod = {
        "production_mwh": [100.0] * periods,
        "capacity_mw": 10.0,
        "energy_capacity_mwh": energy_cap,
        "depth_of_discharge": dod,
        "round_trip_efficiency": rte,
    }
    stream = ArbitrageStream(avg_spread_eur_mwh=spread, cycles_per_day=cycles,
                             spread_capture_ratio=capture)

    series = _arbitrage(stream, prod, 10.0, periods, ppy)
    # First month, degradation = 1.0 (base period).
    expected = energy_cap * dod * rte * cycles * days * spread * capture
    assert abs(series[0] - expected) < 1e-9
