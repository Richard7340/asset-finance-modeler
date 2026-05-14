import pytest

from asset_finance_modeler.assets.saas.engines import CapExEngine
from asset_finance_modeler.assets.saas.schema import CapExItem


def test_capex_no_items():
    eng = CapExEngine(items=[], periods=12, periods_per_year=12)
    out = eng.compute()
    assert out["capex_spend"] == [0] * 12
    assert out["depreciation"] == [0] * 12


def test_capex_single_laptop_fleet():
    item = CapExItem(name="laptops", amount=12_000, period=0, depreciation_years=3)
    eng = CapExEngine(items=[item], periods=48, periods_per_year=12)
    out = eng.compute()
    assert out["capex_spend"][0] == 12_000
    assert out["depreciation"][0] == pytest.approx(12_000 / 36)
    assert out["depreciation"][35] == pytest.approx(12_000 / 36)
    assert out["depreciation"][36] == pytest.approx(0)
    assert out["fixed_assets_net"][0] == pytest.approx(12_000 - 12_000 / 36)
    assert out["fixed_assets_net"][35] == pytest.approx(0, abs=0.01)
