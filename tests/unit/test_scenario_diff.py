from asset_finance_modeler.core.scenario_diff import DiffResult, diff_scenarios


def _scenario_a():
    return {
        "summary": {"revenue_y1": 3_000_000, "total_capex": 22_000_000,
                     "enterprise_value": 15_000_000, "irr_project": 0.085,
                     "cash_end": 5_000_000, "lcoe": 42.5},
        "inputs_resolved": {
            "production": {"capacity_mwp": 50},
            "capex": {"items": [{"amount_per_unit": 0.45}]},
            "financing": {"max_leverage": 0.75},
        },
        "project_kpis": {"irr_equity": 0.12, "dscr_min": 1.32},
    }


def _scenario_b():
    return {
        "summary": {"revenue_y1": 3_200_000, "total_capex": 24_000_000,
                     "enterprise_value": 16_000_000, "irr_project": 0.078,
                     "cash_end": 4_500_000, "lcoe": 45.0},
        "inputs_resolved": {
            "production": {"capacity_mwp": 60},
            "capex": {"items": [{"amount_per_unit": 0.50}]},
            "financing": {"max_leverage": 0.80},
        },
        "project_kpis": {"irr_equity": 0.14, "dscr_min": 1.18},
    }


def test_diff_returns_diff_result():
    result = diff_scenarios(_scenario_a(), _scenario_b())
    assert isinstance(result, DiffResult)


def test_diff_finds_input_deltas():
    result = diff_scenarios(_scenario_a(), _scenario_b())
    paths = [d.field_path for d in result.input_deltas]
    assert "production.capacity_mwp" in paths
    cap_delta = [d for d in result.input_deltas if d.field_path == "production.capacity_mwp"][0]
    assert cap_delta.value_a == 50
    assert cap_delta.value_b == 60
    assert cap_delta.change == 10


def test_diff_finds_kpi_deltas():
    result = diff_scenarios(_scenario_a(), _scenario_b())
    metrics = {d.metric for d in result.kpi_deltas}
    assert "revenue_y1" in metrics
    assert "irr_project" in metrics


def test_diff_revenue_improved():
    result = diff_scenarios(_scenario_a(), _scenario_b())
    rev = [d for d in result.kpi_deltas if d.metric == "revenue_y1"][0]
    assert rev.direction == "improved"
    assert rev.change == 200_000


def test_diff_irr_worsened():
    result = diff_scenarios(_scenario_a(), _scenario_b())
    irr = [d for d in result.kpi_deltas if d.metric == "irr_project"][0]
    assert irr.direction == "worsened"


def test_diff_lcoe_worsened():
    result = diff_scenarios(_scenario_a(), _scenario_b())
    lcoe = [d for d in result.kpi_deltas if d.metric == "lcoe"][0]
    assert lcoe.direction == "worsened"  # higher LCOE is worse


def test_diff_summary_narrative():
    result = diff_scenarios(_scenario_a(), _scenario_b(),
                            scenario_a_name="Base", scenario_b_name="Optimistic")
    assert "Optimistic vs Base" in result.summary
    assert "inputs changed" in result.summary


def test_diff_identical_scenarios():
    a = _scenario_a()
    result = diff_scenarios(a, a)
    assert len(result.input_deltas) == 0
    assert len(result.kpi_deltas) == 0


def test_diff_with_missing_kpis():
    a = {"summary": {"revenue_y1": 1_000_000}, "inputs_resolved": {}}
    b = {"summary": {"revenue_y1": 1_200_000}, "inputs_resolved": {}}
    result = diff_scenarios(a, b)
    assert len(result.kpi_deltas) == 1
