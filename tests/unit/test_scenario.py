from datetime import datetime

import pytest

from asset_finance_modeler.core.scenario import Scenario, apply_overrides, new_scenario_id


def test_new_scenario_id_format():
    sid = new_scenario_id()
    assert sid.startswith("scn-")
    assert len(sid) > 10


def test_new_scenario_id_unique():
    ids = {new_scenario_id() for _ in range(50)}
    assert len(ids) == 50


def test_apply_overrides_scalar():
    base = {"revenue": {"price": 300}}
    result = apply_overrides(base, {"revenue.price": 250})
    assert result["revenue"]["price"] == 250
    # base must not be mutated
    assert base["revenue"]["price"] == 300


def test_apply_overrides_array_index():
    base = {"revenue": {"sources": [{"name": "subs", "price": 300}]}}
    result = apply_overrides(base, {"revenue.sources[0].price": 250})
    assert result["revenue"]["sources"][0]["price"] == 250


def test_apply_overrides_multiple_paths():
    base = {"a": {"b": 1}, "c": {"d": 2}}
    result = apply_overrides(base, {"a.b": 10, "c.d": 20})
    assert result["a"]["b"] == 10
    assert result["c"]["d"] == 20


def test_apply_overrides_invalid_path_raises():
    base = {"a": 1}
    with pytest.raises(KeyError):
        apply_overrides(base, {"nonexistent.path": 5})


def test_scenario_minimal_construction():
    s = Scenario(
        id="scn-abc",
        name="test",
        base_model="gestnova",
        overrides={},
    )
    assert s.parent_scenario_id is None
    assert s.tags == []
    assert s.is_canonical is False
    assert s.notes == ""


def test_scenario_with_snapshots():
    s = Scenario(
        id="scn-abc",
        name="pricing-250",
        base_model="gestnova",
        parent_scenario_id="scn-baseline",
        overrides={"revenue.sources[0].pricing.per_unit_per_period": 250},
        inputs_snapshot={"resolved": True},
        results_snapshot={"revenue_y1": 196000},
        created_at=datetime(2026, 5, 14, 22, 0, 0),
        tags=["pricing", "downside"],
        notes="Lower price test",
    )
    assert s.overrides["revenue.sources[0].pricing.per_unit_per_period"] == 250
    assert "pricing" in s.tags


def test_apply_overrides_invalid_path_hints_top_keys():
    base = {"capital": {"capex_schedule": []}}
    with pytest.raises(KeyError) as exc:
        apply_overrides(base, {"capex.items[0].amount_per_unit": 5})
    assert "capital" in str(exc.value)
    assert "describe_schema" in str(exc.value)
