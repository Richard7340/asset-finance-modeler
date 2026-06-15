"""CAPEX engine for infrastructure assets.

Resolves equipment quantities from the production config, computes total CAPEX,
and dispatches per-item depreciation using ``core.depreciation.compute_depreciation``.

Public interface
----------------
compute_capex(config, production_config, periods, periods_per_year) -> dict
"""

from __future__ import annotations

from typing import Any

from asset_finance_modeler.assets.infrastructure.schema import (
    CAPEXBreakdown,
    InfraCapexItem,
)
from asset_finance_modeler.core.depreciation import compute_depreciation

__all__ = ["compute_capex"]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def compute_capex(
    config: CAPEXBreakdown,
    production_config: Any,
    periods: int,
    periods_per_year: int,
) -> dict[str, Any]:
    """Compute total CAPEX and per-period depreciation schedules.

    Parameters
    ----------
    config:
        CAPEXBreakdown instance with items, contingency, and extra cost fields.
    production_config:
        A production config model used to resolve missing item quantities.
    periods:
        Total number of periods to model.
    periods_per_year:
        Number of periods per year (12 = monthly).

    Returns
    -------
    dict with keys:
        total_capex       : float
        capex_spend       : list[float]  — all at period 0
        book_depreciation : list[float]
        tax_depreciation  : list[float]
        fixed_assets_net  : list[float]
    """
    ppy = periods_per_year

    # ------------------------------------------------------------------
    # Resolve quantities and compute raw equipment cost per item
    # ------------------------------------------------------------------
    equipment_cost: float = 0.0
    item_amounts: list[tuple[InfraCapexItem, float]] = []  # (item, absolute_amount)

    for item in config.items:
        qty = _resolve_quantity(item, production_config)
        amount = item.amount_per_unit * qty
        equipment_cost += amount
        item_amounts.append((item, amount))

    # ------------------------------------------------------------------
    # Total CAPEX
    # ------------------------------------------------------------------
    total_capex: float = (
        equipment_cost * (1.0 + config.contingency_pct)
        + config.development_cost
        + config.grid_connection_cost
        + config.land_acquisition
    )

    # ------------------------------------------------------------------
    # CAPEX spend — all at period 0 (construction assumed pre-operation)
    # ------------------------------------------------------------------
    capex_spend: list[float] = [total_capex] + [0.0] * (periods - 1)

    # ------------------------------------------------------------------
    # Depreciation — aggregate across items
    # Scale each item's depreciation by its share of total_capex so that
    # summed depreciation ≈ total_capex.
    # ------------------------------------------------------------------
    book_depr: list[float] = [0.0] * periods
    tax_depr: list[float] = [0.0] * periods

    if total_capex > 0:
        # Scaling factor: contingency and extra costs are spread proportionally
        scale = total_capex / equipment_cost if equipment_cost > 0 else 1.0

        for item, raw_amount in item_amounts:
            scaled_amount = raw_amount * scale
            dep = compute_depreciation(
                amount=scaled_amount,
                years=item.depreciation_years,
                method=item.depreciation_method,
                periods_per_year=ppy,
                macrs_class=item.macrs_class,
                residual_value_pct=item.residual_value_pct,
            )

            book_series = dep["book"]
            tax_series = dep["tax"]

            # Pad shorter series (e.g. MACRS 5yr) to match total periods
            book_series = _pad(book_series, periods)
            tax_series = _pad(tax_series, periods)

            for t in range(periods):
                book_depr[t] += book_series[t]
                tax_depr[t] += tax_series[t]

        # Add non-equipment costs (development, grid, land) to depreciation
        # using the first item's method as a proxy — or straight-line if no items.
        extra_cost = total_capex - equipment_cost * scale
        if extra_cost > 0 and item_amounts:
            first_item = item_amounts[0][0]
            extra_dep = compute_depreciation(
                amount=extra_cost,
                years=first_item.depreciation_years,
                method="straight_line",
                periods_per_year=ppy,
                residual_value_pct=0,
            )
            extra_book = _pad(extra_dep["book"], periods)
            extra_tax = _pad(extra_dep["tax"], periods)
            for t in range(periods):
                book_depr[t] += extra_book[t]
                tax_depr[t] += extra_tax[t]

    # ------------------------------------------------------------------
    # Fixed assets net (book value)
    # ------------------------------------------------------------------
    fixed_assets_net: list[float] = []
    running = total_capex
    for t in range(periods):
        running -= book_depr[t]
        fixed_assets_net.append(max(running, 0.0))

    return {
        "total_capex": total_capex,
        "capex_spend": capex_spend,
        "book_depreciation": book_depr,
        "tax_depreciation": tax_depr,
        "fixed_assets_net": fixed_assets_net,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_quantity(item: InfraCapexItem, production_config: Any) -> float:
    """Resolve item quantity from explicit value or production config attributes."""
    if item.quantity is not None:
        return float(item.quantity)

    unit = (item.unit or "").strip()

    if unit == "Wp":
        # Solar — capacity_mwp × 1_000_000
        capacity_mwp: float = float(getattr(production_config, "capacity_mwp", 1.0))
        return capacity_mwp * 1_000_000.0

    if unit == "kWh":
        # BESS — power_mw × duration_hours × 1000
        power_mw: float = float(getattr(production_config, "power_mw", 1.0))
        duration_hours: float = float(getattr(production_config, "duration_hours", 1.0))
        return power_mw * duration_hours * 1_000.0

    if unit == "MW":
        cap = _capacity_mw(production_config)
        return cap if cap is not None else 1.0

    # Fallback — use whatever MW-equivalent capacity is available
    cap = _capacity_mw(production_config)
    return cap if cap is not None else 1.0


def _capacity_mw(production_config: Any) -> float | None:
    """Resolve a canonical MW capacity from any production config.

    Each technology names its capacity differently; this maps them all to a
    common MW figure so a ``unit="MW"`` capex item resolves to the real plant
    size rather than silently falling back to ``1.0``:

      * solar           → ``capacity_mwp``
      * wind / generic  → ``capacity_mw``
      * BESS            → ``power_mw``
      * hydrogen        → ``electrolyzer_mw``
      * data center     → ``it_capacity_mw`` (IT load — the capex sizing basis)
      * biomethane      → ``capacity_nm3_h × 0.01`` (10 kWh/Nm3 = 0.01 MWh/Nm3)
    """
    for attr in ("capacity_mw", "capacity_mwp", "power_mw", "electrolyzer_mw", "it_capacity_mw"):
        val = getattr(production_config, attr, None)
        if val is not None:
            return float(val)

    nm3_h = getattr(production_config, "capacity_nm3_h", None)
    if nm3_h is not None:
        return float(nm3_h) * 0.01

    return None


def _pad(series: list[float], length: int) -> list[float]:
    """Extend a series to *length* by appending zeros."""
    if len(series) >= length:
        return series[:length]
    return series + [0.0] * (length - len(series))
