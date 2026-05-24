import pytest

from asset_finance_modeler.core.depreciation import (
    compute_depreciation,
    depreciate_declining_balance,
    depreciate_macrs,
    depreciate_soyd,
    depreciate_straight_line,
)


def test_straight_line_basic():
    dep = depreciate_straight_line(amount=120_000, life_periods=12, residual_pct=0)
    assert len(dep) == 12
    assert dep[0] == pytest.approx(10_000)
    assert sum(dep) == pytest.approx(120_000)


def test_straight_line_with_residual():
    dep = depreciate_straight_line(amount=100_000, life_periods=10, residual_pct=0.10)
    assert sum(dep) == pytest.approx(90_000)
    assert dep[0] == pytest.approx(9_000)


def test_macrs_5year():
    dep = depreciate_macrs(amount=100_000, macrs_class=5, periods_per_year=12)
    total = sum(dep)
    assert total == pytest.approx(100_000, abs=1)
    assert dep[0] > dep[-1]
    assert len(dep) == 72


def test_macrs_7year():
    dep = depreciate_macrs(amount=200_000, macrs_class=7, periods_per_year=12)
    total = sum(dep)
    assert total == pytest.approx(200_000, abs=1)
    assert len(dep) == 96


def test_declining_balance():
    dep = depreciate_declining_balance(
        amount=100_000, life_periods=60, factor=2.0, residual_pct=0.10,
    )
    assert len(dep) == 60
    assert dep[0] > dep[59]
    cumulative = sum(dep)
    assert cumulative == pytest.approx(90_000, abs=100)


def test_soyd():
    dep = depreciate_soyd(amount=100_000, life_periods=24, residual_pct=0)
    assert len(dep) == 24
    assert dep[0] > dep[23]
    assert sum(dep) == pytest.approx(100_000, abs=1)


def test_compute_depreciation_dispatches():
    result = compute_depreciation(
        amount=120_000, years=10, method="straight_line",
        periods_per_year=12, residual_value_pct=0,
    )
    assert "book" in result
    assert "tax" in result
    assert len(result["book"]) == 120
    assert sum(result["book"]) == pytest.approx(120_000)


def test_compute_depreciation_macrs_gives_different_tax():
    result = compute_depreciation(
        amount=100_000, years=20, method="macrs",
        periods_per_year=12, macrs_class=5, residual_value_pct=0,
    )
    assert len(result["book"]) == 240
    assert len(result["tax"]) == 72
    assert sum(result["book"]) == pytest.approx(100_000, abs=1)
    assert sum(result["tax"]) == pytest.approx(100_000, abs=1)


def test_compute_depreciation_unknown_method_raises():
    with pytest.raises(ValueError, match="Unknown depreciation method"):
        compute_depreciation(
            amount=100_000, years=10, method="magic",
            periods_per_year=12,
        )
