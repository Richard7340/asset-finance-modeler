from asset_finance_modeler.assets.business.engines import (
    opex_series,
    pnl_rows,
    revenue_series,
)


def test_revenue_series_lines_and_growth() -> None:
    lines = [
        {"name": "A", "year1_amount": 100.0, "growth_pct_yr": 0.10},
        {"name": "B", "year1_amount": 50.0, "growth_pct_yr": 0.0},
    ]
    rev = revenue_series(lines, years=3)
    assert rev[0] == 150.0
    assert abs(rev[1] - (110.0 + 50.0)) < 1e-9
    assert abs(rev[2] - (121.0 + 50.0)) < 1e-9


def test_opex_series_fixed_and_variable() -> None:
    rev = [1000.0, 1000.0]
    ox = opex_series([{"name": "P", "year1_amount": 100.0}], 0.05, rev, 0.0, 2)
    assert ox == [150.0, 150.0]  # 100 fixed + 5% of 1000


def test_opex_series_per_line_growth_overrides_escalation() -> None:
    """E2: each fixed opex line escalates by its own ``growth_pct_yr`` when set,
    falling back to the shared escalation otherwise (mirrors the revenue side)."""
    rev = [0.0, 0.0, 0.0]
    lines = [
        {"name": "fast", "year1_amount": 100.0, "growth_pct_yr": 0.20},
        {"name": "default", "year1_amount": 100.0},  # no growth → use escalation
    ]
    ox = opex_series(lines, 0.0, rev, escalation_pct_yr=0.05, years=3)
    # y=0: 100 + 100 = 200
    assert abs(ox[0] - 200.0) < 1e-9
    # y=1: 100*1.20 + 100*1.05 = 120 + 105 = 225
    assert abs(ox[1] - 225.0) < 1e-9
    # y=2: 100*1.20^2 + 100*1.05^2 = 144 + 110.25 = 254.25
    assert abs(ox[2] - 254.25) < 1e-9


def test_pnl_rows_basic() -> None:
    rows = pnl_rows(
        revenue=[150.0, 160.0],
        cogs_pct=0.4,
        opex=[60.0, 61.0],
        dep=[10.0, 10.0],
        interest=[5.0, 4.0],
        tax_rate=0.25,
    )
    assert abs(rows["gross_profit"][0] - 90.0) < 1e-9  # 150*0.6
    assert abs(rows["ebitda"][0] - 30.0) < 1e-9  # 90-60
    assert abs(rows["ebit"][0] - 20.0) < 1e-9  # 30-10
    assert abs(rows["ebt"][0] - 15.0) < 1e-9  # 20-5
    assert abs(rows["tax"][0] - 3.75) < 1e-9  # 15*0.25
    assert abs(rows["net_income"][0] - 11.25) < 1e-9
