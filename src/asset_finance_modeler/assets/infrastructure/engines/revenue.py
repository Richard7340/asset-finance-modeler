"""Revenue engines for infrastructure assets.

Dispatches each RevenueStream type to its computation formula and aggregates
per-period revenue across all streams.

Public interface
----------------
compute_revenue(streams, production_output, periods, periods_per_year) -> dict
"""

from __future__ import annotations

from typing import Any

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
from asset_finance_modeler.core.curves import Curve

__all__ = ["compute_revenue"]


# ---------------------------------------------------------------------------
# Public dispatcher
# ---------------------------------------------------------------------------


def compute_revenue(
    streams: list[Any],
    production_output: dict[str, Any],
    periods: int,
    periods_per_year: int,
) -> dict[str, Any]:
    """Compute per-period revenue for each stream and aggregate totals.

    Parameters
    ----------
    streams:
        List of RevenueStream config models.
    production_output:
        Dict returned by ``compute_production`` — must contain at minimum
        ``production_mwh`` (list[float]) and ``capacity_mw`` (float).
    periods:
        Total number of periods to model.
    periods_per_year:
        Number of periods per year (12 = monthly).

    Returns
    -------
    dict with keys:
        streams      : dict[str, list[float]]  — per-stream revenue series
        total_revenue: list[float]             — sum across all streams per period
    """
    ppy = periods_per_year
    production_mwh: list[float] = production_output.get("production_mwh", [0.0] * periods)
    capacity_mw: float = float(production_output.get("capacity_mw", 0.0))

    stream_results: dict[str, list[float]] = {}
    totals: list[float] = [0.0] * periods

    for stream in streams:
        if isinstance(stream, PPAStream):
            series = _ppa(stream, production_mwh, periods, ppy)
            key = stream.name
        elif isinstance(stream, MerchantStream):
            series = _merchant(stream, production_mwh, periods, ppy)
            key = stream.name
        elif isinstance(stream, ArbitrageStream):
            series = _arbitrage(stream, production_output, capacity_mw, periods, ppy)
            key = stream.name
        elif isinstance(stream, AncillaryStream):
            series = _ancillary(stream, capacity_mw, periods, ppy)
            key = stream.name
        elif isinstance(stream, CapacityStream):
            series = _capacity(stream, capacity_mw, periods, ppy)
            key = stream.name
        elif isinstance(stream, OfftakeStream):
            series = _offtake(stream, production_output, production_mwh, periods, ppy)
            key = stream.name
        elif isinstance(stream, CertificateStream):
            series = _certificate(stream, production_mwh, periods)
            key = stream.name
        elif isinstance(stream, RentalStream):
            series = _rental(stream, capacity_mw, periods, ppy)
            key = stream.name
        elif isinstance(stream, SLAStream):
            series = _sla(stream, production_output, capacity_mw, periods, ppy)
            key = stream.name
        else:
            raise TypeError(f"Unsupported revenue stream type: {type(stream)}")

        # Accumulate — multiple streams of same name get summed
        if key in stream_results:
            stream_results[key] = [stream_results[key][t] + series[t] for t in range(periods)]
        else:
            stream_results[key] = series

        for t in range(periods):
            totals[t] += series[t]

    return {
        "streams": stream_results,
        "total_revenue": totals,
    }


# ---------------------------------------------------------------------------
# PPA
# ---------------------------------------------------------------------------


def _ppa(
    cfg: PPAStream,
    production_mwh: list[float],
    periods: int,
    ppy: int,
) -> list[float]:
    """production_mwh[t] × volume_fraction × price × (1 + escalation)^(t/ppy)"""
    esc = cfg.escalation_pct_yr
    price = cfg.price_eur_per_unit
    vf = cfg.volume_fraction
    return [
        production_mwh[t] * vf * price * (1.0 + esc) ** (t / ppy)
        for t in range(periods)
    ]


# ---------------------------------------------------------------------------
# Merchant
# ---------------------------------------------------------------------------


def _merchant(
    cfg: MerchantStream,
    production_mwh: list[float],
    periods: int,
    ppy: int,
) -> list[float]:
    """production_mwh[t] × volume_fraction × base_price × capture_ratio × (1 + esc)^(t/ppy)"""
    esc = cfg.escalation_pct_yr
    price = cfg.base_price_eur_per_unit
    vf = cfg.volume_fraction
    cr = cfg.capture_ratio
    return [
        production_mwh[t] * vf * price * cr * (1.0 + esc) ** (t / ppy)
        for t in range(periods)
    ]


# ---------------------------------------------------------------------------
# Arbitrage (BESS)
# ---------------------------------------------------------------------------


def _arbitrage(
    cfg: ArbitrageStream,
    production_output: dict[str, Any],
    capacity_mw: float,
    periods: int,
    ppy: int,
) -> list[float]:
    """
    energy_cap_mwh = production_output.get("energy_capacity_mwh", capacity_mw)
    Use production_mwh / base_mwh as degradation proxy when no energy_capacity.
    revenue[t] = energy_cap × dod × rte × cycles_per_day × (365/ppy) × spread × capture × deg[t]
    """
    production_mwh: list[float] = production_output.get("production_mwh", [0.0] * periods)
    energy_cap: float = float(production_output.get("energy_capacity_mwh", capacity_mw))

    # Pull degradation from production if BESS provided it; otherwise compute from mwh ratio
    if "energy_capacity_mwh" in production_output and production_mwh and production_mwh[0] > 0:
        base_mwh = production_mwh[0]
        degradation = [mwh / base_mwh if base_mwh > 0 else 1.0 for mwh in production_mwh]
    else:
        degradation = [1.0] * periods

    # Default BESS params — use schema defaults if not in production_output
    dod: float = float(production_output.get("depth_of_discharge", 0.90))
    rte: float = float(production_output.get("round_trip_efficiency", 0.88))
    cycles: float = cfg.cycles_per_day
    days = 365.0 / ppy

    n_years = (periods + ppy - 1) // ppy

    # Per-year spread: library curve > explicit points > flat scalar.
    if cfg.spread_curve_name is not None:
        spread_by_year = Curve.from_library(cfg.spread_curve_name).to_list(n_years)
    elif cfg.spread_points is not None:
        spread_by_year = Curve.from_points(cfg.spread_points).to_list(n_years)
    else:
        spread_by_year = [cfg.avg_spread_eur_mwh] * n_years

    # Constant part of the revenue formula (spread applied per-period below).
    base = energy_cap * dod * rte * cycles * days * cfg.spread_capture_ratio

    return [base * spread_by_year[t // ppy] * degradation[t] for t in range(periods)]


# ---------------------------------------------------------------------------
# Ancillary Services
# ---------------------------------------------------------------------------


def _ancillary(
    cfg: AncillaryStream,
    capacity_mw: float,
    periods: int,
    ppy: int,
) -> list[float]:
    """(fcr + afrr + mfrr) × capacity_mw / ppy, optionally scaled by a per-year multiplier."""
    annual = (cfg.fcr_eur_mw_yr + cfg.afrr_eur_mw_yr + cfg.mfrr_eur_mw_yr) * capacity_mw
    per_period = annual / ppy

    if cfg.curve_points is not None:
        multiplier = Curve.from_points(cfg.curve_points)
        return [per_period * multiplier.at(t // ppy) for t in range(periods)]

    return [per_period] * periods


# ---------------------------------------------------------------------------
# Capacity Payment
# ---------------------------------------------------------------------------


def _capacity(
    cfg: CapacityStream,
    capacity_mw: float,
    periods: int,
    ppy: int,
) -> list[float]:
    """eur_per_mw_yr × capacity_mw / ppy"""
    per_period = cfg.eur_per_mw_yr * capacity_mw / ppy
    return [per_period] * periods


# ---------------------------------------------------------------------------
# Offtake (H2 / Biomethane / generic commodity)
# ---------------------------------------------------------------------------


def _offtake(
    cfg: OfftakeStream,
    production_output: dict[str, Any],
    production_mwh: list[float],
    periods: int,
    ppy: int,
) -> list[float]:
    """
    If production_kg available: production_kg[t] × volume_fraction × price × (1+esc)^(t/ppy)
    Else: like PPA using production_mwh
    """
    esc = cfg.escalation_pct_yr
    price = cfg.price_eur_per_unit
    vf = cfg.volume_fraction

    if "production_kg" in production_output:
        prod_kg: list[float] = production_output["production_kg"]
        return [
            prod_kg[t] * vf * price * (1.0 + esc) ** (t / ppy)
            for t in range(periods)
        ]
    else:
        return [
            production_mwh[t] * vf * price * (1.0 + esc) ** (t / ppy)
            for t in range(periods)
        ]


# ---------------------------------------------------------------------------
# Green Certificates
# ---------------------------------------------------------------------------


def _certificate(
    cfg: CertificateStream,
    production_mwh: list[float],
    periods: int,
) -> list[float]:
    """production_mwh[t] × eligible_fraction × price"""
    price = cfg.price_eur_per_unit
    ef = cfg.eligible_fraction
    return [production_mwh[t] * ef * price for t in range(periods)]


# ---------------------------------------------------------------------------
# Rental
# ---------------------------------------------------------------------------


def _rental(
    cfg: RentalStream,
    capacity_mw: float,
    periods: int,
    ppy: int,
) -> list[float]:
    """price_per_unit × capacity_mw × occupancy × (1+esc)^(t/ppy)"""
    esc = cfg.escalation_pct_yr
    base = cfg.price_per_unit_period * capacity_mw * cfg.occupancy_rate
    return [base * (1.0 + esc) ** (t / ppy) for t in range(periods)]


# ---------------------------------------------------------------------------
# SLA Hosting (Data Center)
# ---------------------------------------------------------------------------


def _sla(
    cfg: SLAStream,
    production_output: dict[str, Any],
    capacity_mw: float,
    periods: int,
    ppy: int,
) -> list[float]:
    """price_per_mw_month × capacity_mw_it (or capacity_mw)"""
    cap_it: float = float(production_output.get("capacity_mw_it", capacity_mw))
    per_period = cfg.price_per_mw_month * cap_it
    return [per_period] * periods
