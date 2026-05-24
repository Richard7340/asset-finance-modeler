"""Accelerated and standard depreciation methods for project finance modeling.

Provides four depreciation schedules (straight-line, declining balance, MACRS,
sum-of-years-digits) plus a unified dispatcher that returns both book and tax
depreciation vectors.

All functions return a list of per-period depreciation amounts.  Periods are
typically months (periods_per_year=12), but the API is period-agnostic.
"""

from __future__ import annotations

# IRS MACRS percentage tables (half-year convention, GDS property classes).
# Each entry is the annual depreciation percentage for that recovery year.
# Source: IRS Publication 946, Appendix A (Rev. 2023).
# Minimum shortfall (in currency units) worth absorbing into the last period.
# Below this threshold the discrepancy is pure floating-point noise.
_SHORTFALL_THRESHOLD: float = 0.01

MACRS_TABLES: dict[int, list[float]] = {
    5: [20.00, 32.00, 19.20, 11.52, 11.52, 5.76],
    7: [14.29, 24.49, 17.49, 12.49, 8.93, 8.92, 8.93, 4.46],
    15: [
        5.00, 9.50, 8.55, 7.70, 6.93, 6.23, 5.90, 5.90,
        5.91, 5.90, 5.91, 5.90, 5.91, 5.90, 5.91, 2.95,
    ],
    20: [
        3.750, 7.219, 6.677, 6.177, 5.713, 5.285, 4.888, 4.522,
        4.462, 4.461, 4.462, 4.461, 4.462, 4.461, 4.462, 4.461,
        4.462, 4.461, 4.462, 4.461, 2.231,
    ],
}


def depreciate_straight_line(
    amount: float,
    life_periods: int,
    residual_pct: float = 0,
) -> list[float]:
    """Straight-line depreciation spread equally over *life_periods* periods.

    Args:
        amount: Gross asset cost (purchase price).
        life_periods: Total number of periods over which to depreciate.
        residual_pct: Salvage / residual value as a fraction of *amount*
            (0 = fully depreciated, 0.10 = 10 % salvage).

    Returns:
        List of length *life_periods* with identical per-period amounts.
    """
    depreciable = amount * (1 - residual_pct)
    per_period = depreciable / life_periods
    return [per_period] * life_periods


def depreciate_declining_balance(
    amount: float,
    life_periods: int,
    factor: float = 2.0,
    residual_pct: float = 0,
) -> list[float]:
    """Double (or N×) declining-balance depreciation.

    Applies *factor* / *life_periods* to the remaining book value each period.
    Automatically switches to straight-line in the period where straight-line
    would yield a larger deduction, ensuring full recovery of the depreciable
    base by the end of the schedule.

    Args:
        amount: Gross asset cost.
        life_periods: Total number of periods.
        factor: Acceleration factor (2.0 = double declining balance,
            1.5 = 150 % declining balance, etc.).
        residual_pct: Salvage value fraction (floor — book value never drops
            below ``amount * residual_pct``).

    Returns:
        List of per-period depreciation amounts of length *life_periods*.
    """
    residual = amount * residual_pct
    depreciable = amount - residual
    rate = factor / life_periods
    result: list[float] = []
    book_value = amount

    for i in range(life_periods):
        remaining_periods = life_periods - i
        db_dep = book_value * rate
        # Switch to straight-line when it gives a larger deduction.
        sl_dep = (book_value - residual) / remaining_periods if remaining_periods > 0 else 0
        dep = max(db_dep, sl_dep)
        # Clamp to avoid going below residual.
        if book_value - dep < residual:
            dep = book_value - residual
        dep = max(dep, 0.0)
        result.append(dep)
        book_value -= dep

    # Absorb floating-point shortfall (should be < 1 cent normally).
    shortfall = depreciable - sum(result)
    if shortfall > _SHORTFALL_THRESHOLD and result:
        result[-1] += shortfall

    return result


def depreciate_macrs(
    amount: float,
    macrs_class: int,
    periods_per_year: int = 12,
) -> list[float]:
    """MACRS depreciation per IRS GDS half-year convention.

    The IRS annual percentage tables are spread evenly across the sub-annual
    periods within each recovery year.

    Args:
        amount: Gross asset cost (basis).
        macrs_class: Recovery period class (one of 5, 7, 15, 20).
        periods_per_year: Sub-annual periods (12 = monthly, 4 = quarterly).

    Returns:
        List of per-period amounts whose length equals
        ``len(MACRS_TABLES[macrs_class]) * periods_per_year``.

    Raises:
        ValueError: If *macrs_class* is not in :data:`MACRS_TABLES`.
    """
    if macrs_class not in MACRS_TABLES:
        raise ValueError(
            f"Unsupported MACRS class: {macrs_class}. "
            f"Use one of {sorted(MACRS_TABLES)}"
        )
    annual_pcts = MACRS_TABLES[macrs_class]
    result: list[float] = []
    for pct in annual_pcts:
        annual_dep = amount * pct / 100
        per_period = annual_dep / periods_per_year
        result.extend([per_period] * periods_per_year)
    return result


def depreciate_soyd(
    amount: float,
    life_periods: int,
    residual_pct: float = 0,
) -> list[float]:
    """Sum-of-years-digits (SOYD) depreciation.

    Assigns a fraction ``(N - t) / SYD`` of the depreciable base to each
    period *t* (0-indexed), where *N* is *life_periods* and *SYD* is the
    sum of digits 1 through *N*.

    Args:
        amount: Gross asset cost.
        life_periods: Total number of periods.
        residual_pct: Salvage value fraction.

    Returns:
        List of per-period depreciation amounts of length *life_periods*,
        front-loaded (largest in period 0).
    """
    depreciable = amount * (1 - residual_pct)
    total_digits = life_periods * (life_periods + 1) // 2
    return [
        depreciable * (life_periods - t) / total_digits
        for t in range(life_periods)
    ]


def compute_depreciation(
    amount: float,
    years: int,
    method: str,
    periods_per_year: int = 12,
    macrs_class: int | None = None,
    residual_value_pct: float = 0,
) -> dict[str, list[float]]:
    """Unified dispatcher returning both book and tax depreciation vectors.

    Book depreciation is always straight-line over the full asset life.
    Tax depreciation uses the chosen *method*.

    Args:
        amount: Gross asset cost.
        years: Useful life in years (book depreciation period).
        method: One of ``"straight_line"``, ``"declining_balance"``,
            ``"macrs"``, ``"soyd"``.
        periods_per_year: Sub-annual periods (12 = monthly).
        macrs_class: Required when *method* is ``"macrs"``.
        residual_value_pct: Salvage value fraction (ignored for MACRS —
            IRS tables already assume zero salvage).

    Returns:
        Dict with keys ``"book"`` and ``"tax"``, each a list of per-period
        depreciation amounts.  ``"book"`` always has length
        ``years * periods_per_year``; ``"tax"`` length depends on *method*.

    Raises:
        ValueError: For unknown *method* or missing *macrs_class*.
    """
    life_periods = years * periods_per_year
    book = depreciate_straight_line(amount, life_periods, residual_value_pct)

    if method == "straight_line":
        tax: list[float] = list(book)
    elif method == "declining_balance":
        tax = depreciate_declining_balance(
            amount, life_periods, 2.0, residual_value_pct
        )
    elif method == "macrs":
        if macrs_class is None:
            raise ValueError("macrs_class required for MACRS depreciation")
        tax = depreciate_macrs(amount, macrs_class, periods_per_year)
    elif method == "soyd":
        tax = depreciate_soyd(amount, life_periods, residual_value_pct)
    else:
        raise ValueError(f"Unknown depreciation method: {method!r}")

    return {"book": book, "tax": tax}
