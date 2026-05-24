# tests/unit/test_resolved_input.py
import pytest
from asset_finance_modeler.core.resolved_input import InsufficientDataError, ResolvedInput

def test_resolved_input_user_source():
    ri = ResolvedInput(field_path="production.capacity_mwp", value=50.0,
                       source="user", provenance="User @ 2026-05-25T10:00", confidence=1.0)
    assert ri.source == "user"
    assert ri.confidence == 1.0
    assert ri.benchmark_id is None

def test_resolved_input_benchmark_source():
    ri = ResolvedInput(field_path="capex.items[0].amount_per_unit", value=550.0,
                       source="benchmark", provenance="Lazard LCOE v17.0",
                       confidence=0.92, benchmark_id="bm-solar-capex-es-2026")
    assert ri.benchmark_id == "bm-solar-capex-es-2026"

def test_resolved_input_to_dict():
    ri = ResolvedInput(field_path="production.capacity_mwp", value=50.0,
                       source="user", provenance="User", confidence=1.0)
    d = ri.to_dict()
    assert d["field_path"] == "production.capacity_mwp"
    assert d["value"] == 50.0
    assert d["source"] == "user"

def test_insufficient_data_error():
    err = InsufficientDataError(missing_fields=["production.capacity_mwp", "capex.items[0].amount_per_unit"])
    assert len(err.missing_fields) == 2
    assert "production.capacity_mwp" in str(err)

def test_insufficient_data_error_empty():
    err = InsufficientDataError(missing_fields=[])
    assert len(err.missing_fields) == 0
