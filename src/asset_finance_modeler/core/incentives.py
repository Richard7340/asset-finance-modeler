from typing import Any


def compute_incentives(
    items: list[dict[str, Any]],
    periods: int,
    periods_per_year: int,
    production_per_period: list[float] | None = None,
    revenue_per_period: list[float] | None = None,
    total_capex: float = 0,
) -> dict[str, list[float]]:
    tax_credits = [0.0] * periods
    subsidies = [0.0] * periods
    grants = [0.0] * periods

    for item in items:
        itype = item["type"]
        value = item["value"]
        duration_years = item.get("duration_years")
        start_year = item.get("start_year", 0)
        start_period = start_year * periods_per_year
        end_period = periods
        if duration_years is not None:
            end_period = min(start_period + duration_years * periods_per_year, periods)

        if itype == "capex_grant":
            if start_period < periods:
                grants[start_period] += total_capex * value

        elif itype == "tax_credit":
            if start_period < periods:
                tax_credits[start_period] += total_capex * value

        elif itype == "production_subsidy":
            if production_per_period is None:
                continue
            for t in range(start_period, end_period):
                if t < periods:
                    subsidies[t] += production_per_period[t] * value

        elif itype == "feed_in_tariff":
            if production_per_period is None:
                continue
            for t in range(start_period, end_period):
                if t < periods:
                    subsidies[t] += production_per_period[t] * value

        elif itype in ("carbon_credit", "rfnbo_premium"):
            if production_per_period is None:
                continue
            for t in range(start_period, end_period):
                if t < periods:
                    subsidies[t] += production_per_period[t] * value

    total = [tax_credits[t] + subsidies[t] + grants[t] for t in range(periods)]
    return {
        "tax_credits": tax_credits,
        "subsidies": subsidies,
        "grants": grants,
        "total": total,
    }
