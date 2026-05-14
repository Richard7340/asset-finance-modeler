import math

import pytest

from asset_finance_modeler.core.statements import (
    BalanceBuilder,
    compute_runway,
    compute_unit_economics,
)


def test_balance_identity_holds():
    bal = BalanceBuilder(
        cash=[100, 150],
        ar_balance=[20, 30],
        fixed_assets_net=[10, 8],
        debt_outstanding=[50, 45],
        ap_balance=[15, 18],
        equity_initial=65,
    ).build()
    assert bal["equity"][0] == pytest.approx(65)
    for t in range(2):
        assets = bal["total_assets"][t]
        liab = bal["total_liabilities"][t]
        eq = bal["equity"][t]
        assert assets == pytest.approx(liab + eq)


def test_unit_economics_basic():
    metrics = compute_unit_economics(
        revenue=[1000, 1100, 1200, 1300, 1400, 1500, 1600, 1700, 1800, 1900, 2000, 2100],
        cogs=[300, 330, 360, 390, 420, 450, 480, 510, 540, 570, 600, 630],
        cac_spend=[400, 400, 400, 400, 400, 400, 400, 400, 400, 400, 400, 400],
        active_customers=[10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21],
        new_customers=[2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
        monthly_churn=0.02,
        periods_per_year=12,
    )
    assert metrics["arpu"][0] == pytest.approx(100.0)
    assert metrics["gross_margin"][0] == pytest.approx(0.7)
    assert metrics["cac"][0] == pytest.approx(200.0)
    assert metrics["ltv"][0] == pytest.approx(3500.0)
    assert metrics["ltv_cac"][0] == pytest.approx(17.5)


def test_runway_until_cash_zero():
    assert compute_runway([100, 80, 60, 40, 20, -10]) == 5
    assert compute_runway([100, 90, 80]) == math.inf
    assert compute_runway([-10]) == 0
