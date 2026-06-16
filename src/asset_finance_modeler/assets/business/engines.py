from __future__ import annotations

from typing import Any


def revenue_series(lines: list[dict[str, Any]], years: int) -> list[float]:
    """Annual total revenue = sum over lines of year1_amount * (1+growth)^(y).

    Year index ``y=0`` is year 1 (no growth applied yet).
    """
    out: list[float] = []
    for y in range(years):
        total = 0.0
        for ln in lines:
            base = float(ln["year1_amount"])
            g = float(ln.get("growth_pct_yr", 0.0))
            total += base * (1.0 + g) ** y
        out.append(total)
    return out


def opex_series(
    fixed_lines: list[dict[str, Any]],
    variable_pct: float,
    revenue: list[float],
    escalation_pct_yr: float,
    years: int,
) -> list[float]:
    """Annual opex = sum(fixed_lines escalated) + variable_pct * revenue[y].

    Each fixed line grows by its own ``growth_pct_yr`` when set (E2); a line that
    leaves it unset (None / absent) falls back to the shared ``escalation_pct_yr``
    — mirroring the per-line growth already honored on the revenue side.
    """
    out: list[float] = []
    for y in range(years):
        fixed = 0.0
        for ln in fixed_lines:
            g = ln.get("growth_pct_yr")
            rate = escalation_pct_yr if g is None else float(g)
            fixed += float(ln["year1_amount"]) * (1.0 + rate) ** y
        var = variable_pct * (revenue[y] if y < len(revenue) else 0.0)
        out.append(fixed + var)
    return out


def pnl_rows(
    revenue: list[float],
    cogs_pct: float,
    opex: list[float],
    dep: list[float],
    interest: list[float],
    tax_rate: float,
) -> dict[str, list[float]]:
    """Build the income-statement rows from annual inputs.

    Tax applies to positive EBT only (no carryforward here; the model layer
    can add it).
    """
    n = len(revenue)

    def at(xs: list[float], i: int) -> float:
        return xs[i] if i < len(xs) else 0.0

    rows: dict[str, list[float]] = {
        k: []
        for k in (
            "revenue",
            "cogs",
            "gross_profit",
            "opex",
            "ebitda",
            "depreciation",
            "ebit",
            "interest_expense",
            "ebt",
            "tax",
            "net_income",
        )
    }
    for i in range(n):
        rev = revenue[i]
        cogs = rev * cogs_pct
        gp = rev - cogs
        ox = at(opex, i)
        ebitda = gp - ox
        d = at(dep, i)
        ebit = ebitda - d
        intr = at(interest, i)
        ebt = ebit - intr
        tax = max(0.0, ebt) * tax_rate
        ni = ebt - tax
        for k, v in (
            ("revenue", rev),
            ("cogs", cogs),
            ("gross_profit", gp),
            ("opex", ox),
            ("ebitda", ebitda),
            ("depreciation", d),
            ("ebit", ebit),
            ("interest_expense", intr),
            ("ebt", ebt),
            ("tax", tax),
            ("net_income", ni),
        ):
            rows[k].append(v)
    return rows
