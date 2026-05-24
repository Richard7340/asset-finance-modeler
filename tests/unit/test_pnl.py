import pytest

from asset_finance_modeler.core.statements import PnLBuilder


def test_pnl_basic_no_loss_carryforward():
    pnl = PnLBuilder(
        revenue=[1000, 1500, 2000],
        cogs=[300, 400, 500],
        opex=[500, 500, 500],
        depreciation=[50, 50, 50],
        interest_expense=[20, 20, 20],
        corporate_tax_rate=0.25,
        carryforward_enabled=False,
    ).build()
    assert pnl["gross_profit"][0] == 700
    assert pnl["ebitda"][0] == 200
    assert pnl["ebit"][0] == 150
    assert pnl["ebt"][0] == 130
    assert pnl["tax"][0] == pytest.approx(32.5)
    assert pnl["net_income"][0] == pytest.approx(97.5)


def test_pnl_negative_ebt_no_tax_no_carryforward():
    pnl = PnLBuilder(
        revenue=[100],
        cogs=[50],
        opex=[200],
        depreciation=[0],
        interest_expense=[0],
        corporate_tax_rate=0.25,
        carryforward_enabled=False,
    ).build()
    assert pnl["tax"][0] == 0
    assert pnl["net_income"][0] == -150


def test_pnl_loss_carryforward_consumes_against_future_profit():
    pnl = PnLBuilder(
        revenue=[100, 1000],
        cogs=[0, 100],
        opex=[200, 200],
        depreciation=[0, 0],
        interest_expense=[0, 0],
        corporate_tax_rate=0.25,
        carryforward_enabled=True,
    ).build()
    assert pnl["tax"][0] == 0
    assert pnl["tax"][1] == pytest.approx(150)
    assert pnl["net_income"][1] == pytest.approx(550)


def test_pnl_with_tax_depreciation_dta():
    """When tax depreciation > book depreciation, DTA is created."""
    pnl = PnLBuilder(
        revenue=[100_000] * 12,
        cogs=[20_000] * 12,
        opex=[30_000] * 12,
        depreciation=[5_000] * 12,
        interest_expense=[2_000] * 12,
        corporate_tax_rate=0.25,
        tax_depreciation=[15_000] * 12,
    ).build()
    assert "tax_depreciation" in pnl
    assert "dta_dtl" in pnl
    assert pnl["dta_dtl"][0] > 0
    assert pnl["tax"][0] < (100_000 - 20_000 - 30_000 - 5_000 - 2_000) * 0.25


def test_pnl_without_tax_depreciation_unchanged():
    """When no tax_depreciation provided, behavior is identical to original."""
    pnl = PnLBuilder(
        revenue=[100_000] * 6,
        cogs=[20_000] * 6,
        opex=[30_000] * 6,
        depreciation=[5_000] * 6,
        interest_expense=[2_000] * 6,
        corporate_tax_rate=0.25,
    ).build()
    assert "dta_dtl" not in pnl or all(d == 0 for d in pnl.get("dta_dtl", []))
