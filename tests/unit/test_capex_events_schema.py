from asset_finance_modeler.assets.infrastructure.loader import load_preset
from asset_finance_modeler.assets.infrastructure.schema import CapexEvent


def test_capex_event_defaults() -> None:
    e = CapexEvent(year=15, amount=200.0)
    assert e.year == 15
    assert e.amount == 200.0
    assert e.resets_degradation is False
    assert e.label == ""
    e2 = CapexEvent(
        year=15, amount=200.0, resets_degradation=True, label="repowering BESS"
    )
    assert e2.resets_degradation is True
    assert e2.label == "repowering BESS"


def test_config_capex_events_default_empty() -> None:
    cfg = load_preset("bess_20mw_4h")
    assert cfg.capex_events == []


def test_config_accepts_capex_events() -> None:
    cfg = load_preset("bess_20mw_4h")
    data = cfg.model_dump()
    data["capex_events"] = [
        {"year": 15, "amount": 200.0, "resets_degradation": True, "label": "repower"}
    ]
    cfg2 = type(cfg).model_validate(data)
    assert len(cfg2.capex_events) == 1
    assert cfg2.capex_events[0].resets_degradation is True
