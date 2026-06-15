"""Production engines for infrastructure asset types.

Each technology has its own private function that computes per-period
production (with degradation applied) and returns a standardised dict.

Public interface
----------------
compute_production(config, degradation, periods, periods_per_year) -> dict
"""

from __future__ import annotations

from typing import Any

from asset_finance_modeler.assets.infrastructure.schema import (
    BESSProduction,
    BiomethaneProduction,
    DataCenterProduction,
    GenericProduction,
    H2Production,
    SolarProduction,
    WindProduction,
)

__all__ = ["compute_production"]

# Map each config class to its engine function (populated after function defs).
_ENGINES: dict[type, Any] = {}


def _profile_multipliers(
    profile: list[float] | None,
    periods: int,
    periods_per_year: int,
) -> list[float]:
    """Per-period multipliers from a seasonal/annual profile (P2-4).

    A profile is a per-period-within-year shape (e.g. 12 monthly factors). It is
    NORMALISED to mean 1.0 so it only reshapes the intra-year distribution — the
    annual total is preserved — and TILED across the horizon so the same shape
    repeats every year. A profile shorter/longer than ``periods_per_year`` is
    used cyclically by ``t % len(profile)``. ``None`` (the default) → all 1.0,
    i.e. unchanged legacy behaviour.
    """
    if not profile:
        return [1.0] * periods
    mean = sum(profile) / len(profile)
    if mean == 0:
        return [1.0] * periods
    norm = [p / mean for p in profile]
    m = len(norm)
    return [norm[t % m] for t in range(periods)]


# ---------------------------------------------------------------------------
# Public dispatcher
# ---------------------------------------------------------------------------


def compute_production(
    config: Any,
    degradation: list[float],
    periods: int,
    periods_per_year: int,
) -> dict[str, Any]:
    """Dispatch to the right technology engine and return production dict.

    Parameters
    ----------
    config:
        A production config model (SolarProduction, WindProduction, etc.).
    degradation:
        Pre-computed degradation factor per period (length == periods).
        Value 1.0 = full capacity; 0.995 = 0.5 % loss, etc.
    periods:
        Total number of periods to model.
    periods_per_year:
        How many periods make a year (12 for monthly, 4 for quarterly, …).

    Returns
    -------
    dict with at minimum:
        production_mwh : list[float]  — energy output per period
        capacity_mw    : float        — nameplate (for OPEX / revenue calcs)
    Plus technology-specific extras (energy_capacity_mwh, production_kg, …).
    """
    engine = _ENGINES.get(type(config))
    if engine is None:
        raise TypeError(f"Unsupported production config type: {type(config)}")
    return engine(config, degradation, periods, periods_per_year)


# ---------------------------------------------------------------------------
# Solar PV
# ---------------------------------------------------------------------------


def _solar(
    cfg: SolarProduction,
    degradation: list[float],
    periods: int,
    periods_per_year: int,
) -> dict[str, Any]:
    """
    annual_mwh = capacity_mwp × 1000 × specific_yield_kwh_kwp × performance_ratio / 1000
    monthly_mwh[t] = annual_mwh / periods_per_year × degradation[t]
    capacity_mw = capacity_mwp  (DC capacity proxy)
    """
    annual_mwh = (
        cfg.capacity_mwp
        * 1_000
        * cfg.specific_yield_kwh_kwp
        * cfg.performance_ratio
        / 1_000
    )
    base_per_period = annual_mwh / periods_per_year

    # P2-4: a seasonal irradiation profile reshapes the intra-year distribution
    # (normalised to mean 1.0 so the annual total is preserved).
    prof = _profile_multipliers(cfg.irradiation_profile, periods, periods_per_year)
    production_mwh = [
        base_per_period * degradation[t] * prof[t] for t in range(periods)
    ]

    return {
        "production_mwh": production_mwh,
        "capacity_mw": cfg.capacity_mwp,
    }


# ---------------------------------------------------------------------------
# Wind (onshore / offshore — same formula, different defaults)
# ---------------------------------------------------------------------------


def _wind(
    cfg: WindProduction,
    degradation: list[float],
    periods: int,
    periods_per_year: int,
) -> dict[str, Any]:
    """
    hours_per_period = 8760 / periods_per_year
    monthly_mwh[t] = capacity_mw × cf × availability × (1 − wake_losses) × hours × degradation[t]
    """
    hours = 8_760 / periods_per_year
    base_per_period = (
        cfg.capacity_mw
        * cfg.capacity_factor
        * cfg.availability
        * (1.0 - cfg.wake_losses)
        * hours
    )

    # P2-4: a seasonal production profile reshapes the intra-year distribution
    # (normalised to mean 1.0 so the annual total is preserved).
    prof = _profile_multipliers(cfg.production_profile, periods, periods_per_year)
    production_mwh = [
        base_per_period * degradation[t] * prof[t] for t in range(periods)
    ]

    return {
        "production_mwh": production_mwh,
        "capacity_mw": cfg.capacity_mw,
    }


# ---------------------------------------------------------------------------
# BESS (Battery Energy Storage System)
# ---------------------------------------------------------------------------


def _bess(
    cfg: BESSProduction,
    degradation: list[float],
    periods: int,
    periods_per_year: int,
) -> dict[str, Any]:
    """
    energy_cap_mwh = power_mw × duration_hours
    daily_discharge = energy_cap × dod × rte × cycles_per_day
    monthly_mwh[t] = daily_discharge × (365 / periods_per_year) × degradation[t]
    capacity_mw = power_mw
    """
    energy_cap_mwh = cfg.power_mw * cfg.duration_hours
    daily_discharge = (
        energy_cap_mwh
        * cfg.depth_of_discharge
        * cfg.round_trip_efficiency
        * cfg.cycles_per_day
    )
    days_per_period = 365.0 / periods_per_year
    base_per_period = daily_discharge * days_per_period

    production_mwh = [base_per_period * degradation[t] for t in range(periods)]

    out = {
        "production_mwh": production_mwh,
        "capacity_mw": cfg.power_mw,
        "energy_capacity_mwh": energy_cap_mwh,
        # Surface the configured battery params so the arbitrage revenue engine
        # honors them instead of falling back to hardcoded defaults (FIX 1).
        "depth_of_discharge": cfg.depth_of_discharge,
        "round_trip_efficiency": cfg.round_trip_efficiency,
        # P3-5: cycles_per_day is owned by BESS production (single source of
        # truth). The arbitrage revenue stream reads THIS value instead of its
        # own field, so the two can never silently diverge.
        "cycles_per_day": cfg.cycles_per_day,
    }
    # P2-4: surface a per-period price-shape multiplier so the arbitrage revenue
    # engine reshapes the intra-year spread (normalised to mean 1.0 → preserves
    # the annual revenue total). Only emitted when a profile is configured — when
    # absent the key is omitted entirely so the production dict (and anything
    # iterating its series, e.g. the construction-window zeroing) is byte-
    # identical to legacy behaviour.
    if cfg.price_profile:
        out["price_profile_mult"] = _profile_multipliers(
            cfg.price_profile, periods, periods_per_year
        )
    return out


# ---------------------------------------------------------------------------
# Green Hydrogen (electrolysis)
# ---------------------------------------------------------------------------


def _h2(
    cfg: H2Production,
    degradation: list[float],
    periods: int,
    periods_per_year: int,
) -> dict[str, Any]:
    """
    hours = 8760 / periods_per_year
    mwh_input[t] = electrolyzer_mw × availability × hours          (electricity consumed)
    kg_per_period[t] = mwh_input × 1000 / efficiency_kwh_per_kg × degradation[t]
    production_mwh = electricity consumed (not produced — negative for grid)
    capacity_mw = electrolyzer_mw
    """
    hours = 8_760 / periods_per_year
    mwh_per_period_base = cfg.electrolyzer_mw * cfg.availability * hours

    production_kg: list[float] = []
    production_mwh: list[float] = []

    for t in range(periods):
        mwh = mwh_per_period_base  # electricity consumed — degradation affects conversion
        kg = mwh * 1_000 / cfg.efficiency_kwh_per_kg * degradation[t]
        production_kg.append(kg)
        production_mwh.append(mwh)

    return {
        "production_mwh": production_mwh,
        "capacity_mw": cfg.electrolyzer_mw,
        "production_kg": production_kg,
    }


# ---------------------------------------------------------------------------
# Biomethane
# ---------------------------------------------------------------------------


def _biomethane(
    cfg: BiomethaneProduction,
    degradation: list[float],
    periods: int,
    periods_per_year: int,
) -> dict[str, Any]:
    """
    hours = operating_hours_yr / periods_per_year
    nm3[t] = capacity_nm3_h × hours × methane_content × upgrading_efficiency × degradation[t]
    mwh[t] ≈ nm3 × 0.01  (10 kWh/Nm³ = 0.01 MWh/Nm³)
    capacity_mw = capacity_nm3_h × 0.01
    """
    hours_per_period = cfg.operating_hours_yr / periods_per_year
    base_nm3 = (
        cfg.capacity_nm3_h
        * hours_per_period
        * cfg.methane_content
        * cfg.upgrading_efficiency
    )

    production_nm3: list[float] = []
    production_mwh: list[float] = []

    for t in range(periods):
        nm3 = base_nm3 * degradation[t]
        mwh = nm3 * 0.01  # 10 kWh/Nm³ → 0.01 MWh/Nm³
        production_nm3.append(nm3)
        production_mwh.append(mwh)

    capacity_mw = cfg.capacity_nm3_h * 0.01

    return {
        "production_mwh": production_mwh,
        "capacity_mw": capacity_mw,
        "production_nm3": production_nm3,
    }


# ---------------------------------------------------------------------------
# Data Center
# ---------------------------------------------------------------------------


def _datacenter(
    cfg: DataCenterProduction,
    degradation: list[float],
    periods: int,
    periods_per_year: int,
) -> dict[str, Any]:
    """
    Data centres are consumers, not producers — production_mwh = 0 for all periods.
    total_mw = it_capacity_mw × pue         (total facility power draw)
    rack_count = it_capacity_mw × 1000 / rack_density_kw
    capacity_mw = total_mw
    capacity_mw_it = it_capacity_mw

    P3-4 — OPEX vs revenue basis (deliberate, documented choice):
      * ``capacity_mw`` (= facility MW = it × PUE) is the OPEX basis: fixed O&M
        and cooling/insurance scale with the TOTAL facility/cooling load, which
        is the standard data-centre operating-cost driver.
      * ``capacity_mw_it`` (= IT MW) is the SLA REVENUE basis: colocation/SLA is
        billed per sellable IT MW.
    The two bases differ by PUE and that asymmetry is intentional (a higher PUE
    means more cooling overhead → higher O&M for the same sellable IT-MW), not a
    bug. See docs/superpowers/modeling_assumptions.md.
    """
    total_mw = cfg.it_capacity_mw * cfg.pue
    rack_count = cfg.it_capacity_mw * 1_000 / cfg.rack_density_kw

    return {
        "production_mwh": [0.0] * periods,
        "capacity_mw": total_mw,
        "capacity_mw_it": cfg.it_capacity_mw,
        "rack_count": rack_count,
    }


# ---------------------------------------------------------------------------
# Generic
# ---------------------------------------------------------------------------


def _generic(
    cfg: GenericProduction,
    degradation: list[float],
    periods: int,
    periods_per_year: int,
) -> dict[str, Any]:
    """
    output[t] = units × output_per_unit_per_period × degradation[t]
    capacity_mw = units  (unitless proxy)
    """
    base = cfg.units * cfg.output_per_unit_per_period
    production_mwh = [base * degradation[t] for t in range(periods)]

    return {
        "production_mwh": production_mwh,
        "capacity_mw": cfg.units,
    }


# ---------------------------------------------------------------------------
# Populate dispatch registry (must be after all engine functions are defined)
# ---------------------------------------------------------------------------

_ENGINES.update(
    {
        SolarProduction: _solar,
        WindProduction: _wind,
        BESSProduction: _bess,
        H2Production: _h2,
        BiomethaneProduction: _biomethane,
        DataCenterProduction: _datacenter,
        GenericProduction: _generic,
    }
)
