from typing import Literal

import numpy_financial as npf


def compute_dcf(
    fcf_series: list[float],
    wacc_annual: float,
    terminal_growth: float,
    periods_per_year: int,
    terminal_method: Literal["gordon", "exit_multiple"] = "gordon",
    exit_arr: float | None = None,
    exit_multiple_arr: float | None = None,
    exit_ebitda: float | None = None,
    exit_multiple_ebitda: float | None = None,
) -> dict[str, float]:
    n = len(fcf_series)
    if n == 0:
        raise ValueError("fcf_series must be non-empty")
    period_rate = (1 + wacc_annual) ** (1 / periods_per_year) - 1

    pv_explicit = 0.0
    for t, fcf in enumerate(fcf_series, start=1):
        pv_explicit += fcf / ((1 + period_rate) ** t)

    if terminal_method == "gordon":
        if wacc_annual <= terminal_growth:
            raise ValueError("Gordon requires wacc > terminal_growth")
        period_growth = (1 + terminal_growth) ** (1 / periods_per_year) - 1
        fcf_terminal_next = fcf_series[-1] * (1 + period_growth)
        terminal_value = fcf_terminal_next / (period_rate - period_growth)
    elif terminal_method == "exit_multiple":
        if exit_arr is not None and exit_multiple_arr is not None:
            terminal_value = exit_arr * exit_multiple_arr
        elif exit_ebitda is not None and exit_multiple_ebitda is not None:
            terminal_value = exit_ebitda * exit_multiple_ebitda
        else:
            raise ValueError(
                "exit_multiple needs exit_arr+exit_multiple_arr or exit_ebitda+exit_multiple_ebitda"
            )
    else:
        raise ValueError(f"Unknown terminal_method: {terminal_method}")

    pv_terminal = terminal_value / ((1 + period_rate) ** n)
    enterprise_value = pv_explicit + pv_terminal

    return {
        "pv_explicit": pv_explicit,
        "terminal_value": terminal_value,
        "pv_terminal": pv_terminal,
        "enterprise_value": enterprise_value,
    }


def compute_sensitivity_grid(
    fcf_series: list[float],
    wacc_values: list[float],
    growth_values: list[float],
    periods_per_year: int,
    terminal_method: Literal["gordon", "exit_multiple"] = "gordon",
    exit_arr: float | None = None,
    exit_multiple_arr: float | None = None,
) -> list[list[float]]:
    grid: list[list[float]] = []
    for wacc in wacc_values:
        row: list[float] = []
        for g in growth_values:
            try:
                ev = compute_dcf(
                    fcf_series=fcf_series,
                    wacc_annual=wacc,
                    terminal_growth=g,
                    periods_per_year=periods_per_year,
                    terminal_method=terminal_method,
                    exit_arr=exit_arr,
                    exit_multiple_arr=exit_multiple_arr,
                )["enterprise_value"]
            except ValueError:
                ev = float("nan")
            row.append(ev)
        grid.append(row)
    return grid


def compute_irr(cashflows: list[float], periods_per_year: int) -> float:
    period_irr = npf.irr(cashflows)
    if period_irr is None or not isinstance(period_irr, float):
        return 0.0
    return (1 + period_irr) ** periods_per_year - 1


def compute_lcoe(total_costs_pv: float, total_energy_pv: float) -> float:
    if total_energy_pv <= 0:
        return float("inf")
    return total_costs_pv / total_energy_pv


def compute_lcos(total_costs_pv: float, total_energy_discharged_pv: float) -> float:
    if total_energy_discharged_pv <= 0:
        return float("inf")
    return total_costs_pv / total_energy_discharged_pv


def compute_discounted_payback(
    cashflows: list[float], discount_rate: float, periods_per_year: int,
) -> float:
    period_rate = (1 + discount_rate) ** (1 / periods_per_year) - 1
    cumulative = 0.0
    for t, cf in enumerate(cashflows):
        cumulative += cf / ((1 + period_rate) ** t)
        if cumulative >= 0 and t > 0:
            return float(t) / periods_per_year
    return float("inf")
