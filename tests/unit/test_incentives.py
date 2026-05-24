import pytest

from asset_finance_modeler.core.incentives import compute_incentives


def test_capex_grant():
    result = compute_incentives(
        items=[{"type": "capex_grant", "value": 0.30, "duration_years": None, "start_year": 0}],
        periods=120, periods_per_year=12,
        total_capex=10_000_000,
    )
    assert result["total"][0] == pytest.approx(3_000_000)
    assert sum(result["total"][1:]) == 0


def test_production_subsidy():
    production = [1000.0] * 120
    result = compute_incentives(
        items=[{"type": "production_subsidy", "value": 25.0, "duration_years": 5, "start_year": 0}],
        periods=120, periods_per_year=12,
        production_per_period=production,
    )
    assert result["total"][0] == pytest.approx(25_000)
    assert result["total"][59] == pytest.approx(25_000)
    assert result["total"][60] == 0


def test_tax_credit():
    result = compute_incentives(
        items=[{"type": "tax_credit", "value": 0.26, "duration_years": None, "start_year": 0}],
        periods=120, periods_per_year=12,
        total_capex=10_000_000,
    )
    assert result["tax_credits"][0] == pytest.approx(2_600_000)


def test_multiple_incentives():
    production = [1000.0] * 60
    result = compute_incentives(
        items=[
            {"type": "capex_grant", "value": 0.10, "duration_years": None, "start_year": 0},
            {"type": "production_subsidy", "value": 10.0, "duration_years": 3, "start_year": 0},
        ],
        periods=60, periods_per_year=12,
        total_capex=5_000_000, production_per_period=production,
    )
    assert result["total"][0] == pytest.approx(500_000 + 10_000)
    assert result["total"][36] == pytest.approx(0)


def test_no_incentives():
    result = compute_incentives(items=[], periods=12, periods_per_year=12)
    assert result["total"] == [0.0] * 12
