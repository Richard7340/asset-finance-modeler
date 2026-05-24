"""
Asset degradation curves.

Each function returns a list of multipliers (one per period) in the range
[0.0, 1.0] that scale the nominal production output of an asset over time.

Supported models
----------------
* **time_based** — linear calendar degradation (e.g. solar panels 0.5 %/yr).
* **cycle_based** — combined cycle-fade + calendar-fade with an end-of-life
  floor (e.g. BESS capacity fade per charge/discharge cycle).
* **usage_based** — efficiency loss proportional to operating hours
  (e.g. electrolyser membranes losing efficiency per 1 000 h).
* **none** — no degradation; returns a flat list of 1.0.
"""

from __future__ import annotations


def degradation_time_based(
    periods: int,
    annual_rate: float,
    periods_per_year: int,
) -> list[float]:
    """Linear time-based degradation.

    Parameters
    ----------
    periods:
        Total number of model periods (e.g. 240 for 20 years monthly).
    annual_rate:
        Fractional capacity loss per year (e.g. 0.005 for 0.5 %/yr).
    periods_per_year:
        Number of periods in one year (12 for monthly, 1 for annual, etc.).

    Returns
    -------
    list[float]
        Multipliers for period t=0, 1, …, periods-1.
        Period 0 always returns 1.0.
    """
    return [
        max(0.0, 1.0 - annual_rate * t / periods_per_year)
        for t in range(periods)
    ]


def degradation_cycle_based(
    periods: int,
    cycles_per_period: float,
    fade_per_cycle: float,
    calendar_fade_annual: float,
    periods_per_year: int,
    eol_pct: float = 0.70,
) -> list[float]:
    """Combined cycle + calendar degradation with end-of-life floor.

    Capacity falls by ``cycles_per_period * fade_per_cycle`` (cycle stress)
    plus ``calendar_fade_annual / periods_per_year`` (calendar ageing) each
    period.  Values are clamped to ``eol_pct`` so the asset never degrades
    below its end-of-life rated capacity.

    Parameters
    ----------
    periods:
        Total number of model periods.
    cycles_per_period:
        Average charge/discharge cycles completed per period.
    fade_per_cycle:
        Fractional capacity lost per full cycle (e.g. 0.00005).
    calendar_fade_annual:
        Annual fractional capacity lost through calendar ageing alone
        (e.g. 0.02 for 2 %/yr).
    periods_per_year:
        Number of periods in one year.
    eol_pct:
        End-of-life capacity floor as a fraction of nameplate (default 0.70).

    Returns
    -------
    list[float]
        Multipliers, each >= eol_pct.  Period 0 returns 1.0.
    """
    result: list[float] = []
    capacity = 1.0
    calendar_per_period = calendar_fade_annual / periods_per_year
    cycle_loss_per_period = cycles_per_period * fade_per_cycle

    for _ in range(periods):
        result.append(max(eol_pct, capacity))
        capacity -= cycle_loss_per_period + calendar_per_period

    return result


def degradation_usage_based(
    periods: int,
    hours_per_period: float,
    loss_per_1000h: float,
) -> list[float]:
    """Efficiency degradation proportional to cumulative operating hours.

    Parameters
    ----------
    periods:
        Total number of model periods.
    hours_per_period:
        Operating hours logged per period (e.g. 720 h/month).
    loss_per_1000h:
        Fractional efficiency loss per 1 000 operating hours
        (e.g. 0.001 for 0.1 % per 1 000 h).

    Returns
    -------
    list[float]
        Monotonically non-increasing multipliers in [0.0, 1.0].
        Period 0 returns 1.0.
    """
    result: list[float] = []
    efficiency = 1.0
    loss_per_period = hours_per_period / 1_000.0 * loss_per_1000h

    for _ in range(periods):
        result.append(efficiency)
        efficiency = max(0.0, efficiency - loss_per_period)

    return result


def degradation_none(periods: int) -> list[float]:
    """No degradation — returns a flat list of 1.0 multipliers.

    Parameters
    ----------
    periods:
        Total number of model periods.

    Returns
    -------
    list[float]
        ``[1.0] * periods``
    """
    return [1.0] * periods
