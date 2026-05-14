from datetime import date

import pytest
from pydantic import ValidationError

from asset_finance_modeler.assets.saas.schema import HorizonConfig, ModelMeta


def test_horizon_basic():
    h = HorizonConfig(periods=60, frequency="M")
    assert h.periods == 60
    assert h.frequency == "M"


def test_horizon_invalid_frequency():
    with pytest.raises(ValidationError):
        HorizonConfig(periods=60, frequency="X")  # type: ignore[arg-type]


def test_model_meta_minimal():
    m = ModelMeta(
        name="gestnova",
        horizon=HorizonConfig(periods=60, frequency="M"),
        start_date=date(2026, 5, 1),
        initial_cash=100_000,
    )
    assert m.base_currency == "EUR"
    assert m.inflation_annual == 0.025
    assert m.fx_rates == {}


def test_model_meta_with_fx():
    m = ModelMeta(
        name="gestnova",
        horizon=HorizonConfig(periods=60, frequency="M"),
        start_date=date(2026, 5, 1),
        initial_cash=100_000,
        fx_rates={"USD": 1.08},
    )
    assert m.fx_rates["USD"] == 1.08
