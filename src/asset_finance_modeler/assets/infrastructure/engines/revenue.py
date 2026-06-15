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


def _curve_by_year(
    curve_name: str | None,
    points: list[float] | None,
    n_years: int,
) -> list[float] | None:
    """Resolve a per-year value series for a curve-driven price/value field.

    Precedence (same pattern as merchant/arbitrage): library curve > explicit
    points > None (caller falls back to the base × escalation formula). A curve
    embeds the consultant price path, so the caller MUST NOT re-apply escalation
    or capture on top of the returned series — only volume factors.
    """
    if curve_name is not None:
        return Curve.from_library(curve_name).to_list(n_years)
    if points is not None:
        return Curve.from_points(points).to_list(n_years)
    return None


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
            series = _certificate(stream, production_mwh, periods, ppy)
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
    """Curve-driven (preferred): production × volume_fraction × price_curve[year]
    (curve embeds escalation, NOT re-applied). Fallback: production ×
    volume_fraction × price × (1 + escalation)^(t/ppy)."""
    vf = cfg.volume_fraction
    n_years = (periods + ppy - 1) // ppy
    price_by_year = _curve_by_year(cfg.price_curve_name, cfg.price_points, n_years)
    if price_by_year is not None:
        return [production_mwh[t] * vf * price_by_year[t // ppy] for t in range(periods)]

    esc = cfg.escalation_pct_yr
    price = cfg.price_eur_per_unit
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
    """Per-period merchant revenue.

    Curve-driven (preferred when available): the realized capture price per
    year comes straight from a curve — a library curve (``price_curve_name``,
    e.g. ``solar_capture_es``) or explicit per-year points (``price_points`` /
    legacy ``price_curve``). The curve already embeds the capture effect and
    consultant view of price decay, so ``capture_ratio`` and ``escalation`` are
    NOT re-applied on top of it::

        revenue[t] = production_mwh[t] × volume_fraction × capture_price[year]

    Fallback (no curve): base price escalated, with capture ratio::

        revenue[t] = production_mwh[t] × volume_fraction × base_price
                     × capture_ratio × (1 + escalation)^(t/ppy)
    """
    vf = cfg.volume_fraction
    n_years = (periods + ppy - 1) // ppy

    # Per-year realized capture price: library curve > explicit points > None.
    capture_by_year: list[float] | None = None
    if cfg.price_curve_name is not None:
        capture_by_year = Curve.from_library(cfg.price_curve_name).to_list(n_years)
    elif cfg.price_points is not None:
        capture_by_year = Curve.from_points(cfg.price_points).to_list(n_years)
    elif cfg.price_curve is not None:
        capture_by_year = Curve.from_points(cfg.price_curve).to_list(n_years)

    if capture_by_year is not None:
        return [
            production_mwh[t] * vf * capture_by_year[t // ppy] for t in range(periods)
        ]

    esc = cfg.escalation_pct_yr
    price = cfg.base_price_eur_per_unit
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

    # P2-4: intra-year price-shape multiplier (BESS price_profile, normalised to
    # mean 1.0 so the annual total is preserved). Absent → all 1.0 (unchanged).
    price_mult = production_output.get("price_profile_mult") or [1.0] * periods

    return [
        base * spread_by_year[t // ppy] * degradation[t] * price_mult[t]
        for t in range(periods)
    ]


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
    """Curve-driven (preferred): price_curve[year] × capacity_mw / ppy.
    Fallback: eur_per_mw_yr × capacity_mw / ppy (flat)."""
    n_years = (periods + ppy - 1) // ppy
    price_by_year = _curve_by_year(cfg.price_curve_name, cfg.price_points, n_years)
    if price_by_year is not None:
        return [price_by_year[t // ppy] * capacity_mw / ppy for t in range(periods)]
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
    """Curve-driven (preferred): volume × volume_fraction × price_curve[year]
    (curve embeds escalation, NOT re-applied). Fallback: volume ×
    volume_fraction × price × (1+esc)^(t/ppy). Volume = production_kg when
    available (H2), else production_mwh (biomethane/generic commodity)."""
    vf = cfg.volume_fraction
    volume: list[float] = production_output.get("production_kg", production_mwh)

    n_years = (periods + ppy - 1) // ppy
    price_by_year = _curve_by_year(cfg.price_curve_name, cfg.price_points, n_years)
    if price_by_year is not None:
        return [volume[t] * vf * price_by_year[t // ppy] for t in range(periods)]

    esc = cfg.escalation_pct_yr
    price = cfg.price_eur_per_unit
    return [
        volume[t] * vf * price * (1.0 + esc) ** (t / ppy)
        for t in range(periods)
    ]


# ---------------------------------------------------------------------------
# Green Certificates
# ---------------------------------------------------------------------------


def _certificate(
    cfg: CertificateStream,
    production_mwh: list[float],
    periods: int,
    ppy: int,
) -> list[float]:
    """Curve-driven (preferred): production × eligible_fraction × price_curve[year].
    Fallback: production × eligible_fraction × price (flat)."""
    ef = cfg.eligible_fraction
    n_years = (periods + ppy - 1) // ppy
    price_by_year = _curve_by_year(cfg.price_curve_name, cfg.price_points, n_years)
    if price_by_year is not None:
        return [production_mwh[t] * ef * price_by_year[t // ppy] for t in range(periods)]
    price = cfg.price_eur_per_unit
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
    """Curve-driven (preferred): price_curve[year] × capacity_mw × occupancy
    (curve embeds escalation, NOT re-applied; occupancy is a volume factor).
    Fallback: price_per_unit × capacity_mw × occupancy × (1+esc)^(t/ppy)."""
    occ = cfg.occupancy_rate
    n_years = (periods + ppy - 1) // ppy
    price_by_year = _curve_by_year(cfg.price_curve_name, cfg.price_points, n_years)
    if price_by_year is not None:
        return [price_by_year[t // ppy] * capacity_mw * occ for t in range(periods)]
    esc = cfg.escalation_pct_yr
    base = cfg.price_per_unit_period * capacity_mw * occ
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
    """Curve-driven (preferred): price_curve[year] × capacity_mw_it.
    Fallback: price_per_mw_month × capacity_mw_it (flat)."""
    cap_it: float = float(production_output.get("capacity_mw_it", capacity_mw))
    n_years = (periods + ppy - 1) // ppy
    price_by_year = _curve_by_year(cfg.price_curve_name, cfg.price_points, n_years)
    if price_by_year is not None:
        return [price_by_year[t // ppy] * cap_it for t in range(periods)]
    per_period = cfg.price_per_mw_month * cap_it
    return [per_period] * periods
