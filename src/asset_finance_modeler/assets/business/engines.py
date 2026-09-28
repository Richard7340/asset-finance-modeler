from __future__ import annotations

from typing import Any


def indice_ipc(curva: list[float] | None, years: int) -> list[float] | None:
    """Indice de precios acumulado por anio (anio 1 = 1.0) a partir de la
    inflacion de cada anio; el ultimo valor de la curva sigue."""
    if not curva:
        return None
    idx, acum = [], 1.0
    for y in range(years):
        idx.append(acum)
        acum *= 1.0 + float(curva[min(y, len(curva) - 1)])
    return idx


def importe_de_linea(ln: dict[str, Any], y: int, rate: float, indice: list[float] | None = None) -> float:
    """El importe de una línea el año y (0 = el primero), 28-sep:
    - `curva` (importes por año, los del usuario, nominales): tal cual; pasado
      el último año, ese importe crece a `rate`.
    - `crecimientos` (subida de cada año): se encadenan desde year1_amount; el
      último sigue. Con IPC, la subida es real y va encima.
    - si no: year1_amount crece a `rate` (y el IPC encima), como siempre."""
    curva = ln.get("curva")
    if curva:
        if y < len(curva):
            return float(curva[y])
        return float(curva[-1]) * (1.0 + rate) ** (y - len(curva) + 1)
    base = float(ln["year1_amount"])
    crec = ln.get("crecimientos")
    if crec:
        f = 1.0
        for k in range(1, y + 1):
            f *= 1.0 + float(crec[min(k - 1, len(crec) - 1)])
        return base * f * (indice[y] if indice else 1.0)
    return base * (1.0 + rate) ** y * (indice[y] if indice else 1.0)


def revenue_series(lines: list[dict[str, Any]], years: int, indice: list[float] | None = None) -> list[float]:
    """Annual total revenue = sum over lines of year1_amount * (1+growth)^(y).

    Year index ``y=0`` is year 1 (no growth applied yet). Con ``indice`` (curva
    de IPC), el crecimiento de la linea es REAL y encima va el IPC de cada anio.
    """
    out: list[float] = []
    for y in range(years):
        total = 0.0
        for ln in lines:
            total += importe_de_linea(ln, y, float(ln.get("growth_pct_yr", 0.0)), indice)
        out.append(total)
    return out


def opex_series(
    fixed_lines: list[dict[str, Any]],
    variable_pct: float,
    revenue: list[float],
    escalation_pct_yr: float,
    years: int,
    indice: list[float] | None = None,
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
            if indice:
                # Con curva de IPC: el IPC del anio y, si la linea tiene su
                # propio crecimiento, ese crecimiento real encima.
                fixed += importe_de_linea(ln, y, float(g or 0.0), indice)
                continue
            rate = escalation_pct_yr if g is None else float(g)
            fixed += importe_de_linea(ln, y, rate)
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


def line_series(cfg: dict[str, Any], years: int) -> dict[str, dict[str, list[float]]]:
    """Cada ingreso y cada gasto por separado, por año (las mismas fórmulas que
    revenue_series / opex_series): para anotar lo real de cada línea (IBI,
    comunidad, mantenimiento…) y compararlo con su previsión (26-sep)."""
    revenue = cfg.get("revenue") or []
    inf = cfg.get("inflacion") or {}
    idx = indice_ipc(inf.get("curva"), years) if inf else None
    idx_i = idx if idx and inf.get("aplicar_a", "todo") in ("todo", "ingresos") else None
    idx_g = idx if idx and inf.get("aplicar_a", "todo") in ("todo", "gastos") else None
    ingresos: dict[str, list[float]] = {}
    for ln in revenue:
        g = float(ln.get("growth_pct_yr", 0.0))
        ingresos[str(ln["name"])] = [importe_de_linea(ln, y, g, idx_i) for y in range(years)]
    total = revenue_series(revenue, years, idx_i)
    opex = cfg.get("opex") or {}
    esc = float(opex.get("escalation_pct_yr", 0.0))
    gastos: dict[str, list[float]] = {}
    cogs_pct = float((cfg.get("cogs") or {}).get("pct_of_revenue", 0.0))
    if cogs_pct:
        gastos["Coste de ventas"] = [cogs_pct * r for r in total]
    for ln in opex.get("fixed_lines") or []:
        g = ln.get("growth_pct_yr")
        if idx_g:
            gastos[str(ln["name"])] = [importe_de_linea(ln, y, float(g or 0.0), idx_g) for y in range(years)]
            continue
        rate = esc if g is None else float(g)
        gastos[str(ln["name"])] = [importe_de_linea(ln, y, rate) for y in range(years)]
    var_pct = float(opex.get("variable_pct_of_revenue", 0.0))
    if var_pct:
        gastos["Gastos variables"] = [var_pct * r for r in total]
    return {"ingresos": ingresos, "gastos": gastos}
