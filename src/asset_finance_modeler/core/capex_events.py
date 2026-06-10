from __future__ import annotations


def apply_capex_events(
    capex_spend: list[float],
    events: list[tuple[int, float]],
    periods_per_year: int,
) -> list[float]:
    """Return a copy of capex_spend with each event's amount added at its
    period. Each event is (year, amount); period = year * periods_per_year.
    Events whose period falls outside the horizon are ignored."""
    out = list(capex_spend)
    n = len(out)
    for year, amount in events:
        t = year * periods_per_year
        if 0 <= t < n:
            out[t] += amount
    return out


def apply_degradation_resets(
    base_curve: list[float],
    reset_periods: list[int],
) -> list[float]:
    """Return a copy of base_curve where, at each reset period r, capacity
    returns to base_curve[0] and follows the same degradation shape again:
    for t >= r (until the next reset), multiplier = base_curve[t - r]."""
    out = list(base_curve)
    n = len(base_curve)
    for r in sorted(reset_periods):
        if r < 0 or r >= n:
            continue
        for t in range(r, n):
            offset = t - r
            out[t] = base_curve[offset] if offset < n else base_curve[-1]
    return out
