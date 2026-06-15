"""OPEX engine for infrastructure assets.

Computes all operating cost categories per period, including fixed O&M,
variable O&M, insurance, land lease, management fees, other fixed costs,
and scheduled maintenance events (including recurring ones).

Public interface
----------------
compute_opex(config, capacity_mw, total_capex, production_mwh, periods, periods_per_year) -> dict
"""

from __future__ import annotations

from typing import Any

from asset_finance_modeler.assets.infrastructure.schema import InfraOPEXConfig

__all__ = ["compute_opex"]


def compute_opex(
    config: InfraOPEXConfig,
    capacity_mw: float,
    total_capex: float,
    production_mwh: list[float],
    periods: int,
    periods_per_year: int,
    production_config: Any | None = None,
) -> dict[str, list[float]]:
    """Compute per-period OPEX broken down by category.

    Parameters
    ----------
    config:
        InfraOPEXConfig instance with all cost parameters.
    capacity_mw:
        Installed capacity in MW — used for fixed O&M and other MW-based costs.
    total_capex:
        Total CAPEX in EUR — used to compute insurance.
    production_mwh:
        Per-period energy output in MWh — used for variable O&M.
    periods:
        Total number of periods to model.
    periods_per_year:
        Number of periods per year (12 = monthly).

    Returns
    -------
    dict with keys:
        fixed_om     : list[float]
        variable_om  : list[float]
        insurance    : list[float]
        land         : list[float]
        management   : list[float]
        other        : list[float]
        maintenance  : list[float]
        total_opex   : list[float]
    """
    ppy = periods_per_year
    esc = config.opex_escalation_pct_yr

    # ------------------------------------------------------------------
    # Fixed O&M  — escalated
    # ------------------------------------------------------------------
    fixed_om_annual = config.om_fixed_eur_per_mw_yr * capacity_mw
    fixed_om = [
        (fixed_om_annual / ppy) * (1.0 + esc) ** (t / ppy)
        for t in range(periods)
    ]

    # ------------------------------------------------------------------
    # Variable O&M  — proportional to production, no escalation
    # ------------------------------------------------------------------
    variable_om = [
        config.om_variable_eur_per_mwh * production_mwh[t]
        for t in range(periods)
    ]

    # ------------------------------------------------------------------
    # Insurance  — flat fraction of total CAPEX, no escalation
    # ------------------------------------------------------------------
    insurance_per_period = config.insurance_pct_capex * total_capex / ppy
    insurance = [insurance_per_period] * periods

    # ------------------------------------------------------------------
    # Land lease  — escalated
    # ------------------------------------------------------------------
    land = [
        (config.land_lease_eur_yr / ppy) * (1.0 + esc) ** (t / ppy)
        for t in range(periods)
    ]

    # ------------------------------------------------------------------
    # Management fee  — escalated
    # ------------------------------------------------------------------
    management = [
        (config.management_fee_eur_yr / ppy) * (1.0 + esc) ** (t / ppy)
        for t in range(periods)
    ]

    # ------------------------------------------------------------------
    # Other fixed  — flat, no escalation
    # ------------------------------------------------------------------
    other_per_period = config.other_fixed_eur_yr / ppy
    other = [other_per_period] * periods

    # ------------------------------------------------------------------
    # Maintenance events  (one-off + recurring)
    # ------------------------------------------------------------------
    maintenance: list[float] = [0.0] * periods

    for event in config.major_maintenance:
        # Collect all periods where this event fires
        event_periods: list[int] = []

        # First occurrence
        if 0 <= event.period < periods:
            event_periods.append(event.period)

        # Recurring occurrences
        if event.recurring_interval is not None and event.recurring_interval > 0:
            next_period = event.period + event.recurring_interval
            while next_period < periods:
                event_periods.append(next_period)
                next_period += event.recurring_interval

        for ep in event_periods:
            maintenance[ep] += event.cost

    # ------------------------------------------------------------------
    # Electricity cost  — variable, driven by energy consumed.
    # Technologies whose production config exposes ``electricity_cost_eur_mwh``
    # (notably green hydrogen, whose ``production_mwh`` is the electricity it
    # *consumes*) pay for that energy. Was previously ignored, giving H2 an
    # unrealistically high IRR. No escalation here — price is a real input.
    # ------------------------------------------------------------------
    elec_cost = float(getattr(production_config, "electricity_cost_eur_mwh", 0.0) or 0.0)
    electricity = [elec_cost * production_mwh[t] for t in range(periods)]

    # ------------------------------------------------------------------
    # Total OPEX
    # ------------------------------------------------------------------
    total_opex = [
        fixed_om[t]
        + variable_om[t]
        + insurance[t]
        + land[t]
        + management[t]
        + other[t]
        + maintenance[t]
        + electricity[t]
        for t in range(periods)
    ]

    return {
        "fixed_om": fixed_om,
        "variable_om": variable_om,
        "insurance": insurance,
        "land": land,
        "management": management,
        "other": other,
        "maintenance": maintenance,
        "electricity": electricity,
        "total_opex": total_opex,
    }
