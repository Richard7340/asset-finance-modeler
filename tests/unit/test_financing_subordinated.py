from asset_finance_modeler.assets.infrastructure.schema import (
    ProjectFinanceConfig,
    SubordinatedDebtConfig,
)


def test_financing_accepts_subordinated_optional() -> None:
    f = ProjectFinanceConfig()
    assert f.subordinated is None
    sub = SubordinatedDebtConfig(principal=1841.0, interest_rate=0.085, tenor_years=7)
    f2 = ProjectFinanceConfig(subordinated=sub)
    assert f2.subordinated is not None
    assert f2.subordinated.interest_rate == 0.085
    assert f2.subordinated.amortization == "french"
    assert f2.subordinated.principal == 1841.0
    assert f2.subordinated.grace_period_months == 0
    assert f2.subordinated.drawdown_period == 0
