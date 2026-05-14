import json

import pytest

from asset_finance_modeler.core.scenario import Scenario, new_scenario_id, run_scenario_saas
from asset_finance_modeler.store.compare import compare_scenarios
from asset_finance_modeler.store.exports import (
    to_csv,
    to_json,
    to_markdown_report,
    to_xlsx,
)
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore
from asset_finance_modeler.store.sensitivity import sensitivity_1d


def _persist_with_results(store, scenario):
    results = run_scenario_saas(scenario)
    scenario.results_snapshot = {"summary": dict(results.summary)}
    store.save(scenario)
    return scenario, results


def test_full_workflow(tmp_path):
    # 1. Set up store
    store = SQLiteScenarioStore(str(tmp_path / "scenarios.db"))
    store.initialize()

    # 2. Create baseline
    baseline = Scenario(
        id=new_scenario_id(), name="gestnova-baseline", base_model="gestnova",
        is_canonical=True, tags=["baseline"], notes="Initial baseline",
    )
    baseline, base_results = _persist_with_results(store, baseline)

    # 3. Branch: lower pricing
    lower_price = Scenario(
        id=new_scenario_id(), name="pricing-250", base_model="gestnova",
        parent_scenario_id=baseline.id,
        overrides={"revenue.sources[0].pricing.per_unit_per_period": 250},
        tags=["pricing", "downside"],
    )
    lower_price, _ = _persist_with_results(store, lower_price)

    # 4. Branch from lower_price: also reduce infra cost
    aggressive = Scenario(
        id=new_scenario_id(), name="pricing-250+infra-reduced", base_model="gestnova",
        parent_scenario_id=lower_price.id,
        overrides={
            "revenue.sources[0].pricing.per_unit_per_period": 250,
            "operating_expenses.infra_fixed_eur": 600,
        },
    )
    aggressive, _ = _persist_with_results(store, aggressive)

    # 5. Genealogy
    ancestors = store.get_ancestors(aggressive.id)
    assert [a.name for a in ancestors] == ["pricing-250", "gestnova-baseline"]
    descendants = store.get_descendants(baseline.id)
    descendant_names = {d.name for d in descendants}
    assert descendant_names == {"pricing-250", "pricing-250+infra-reduced"}

    # 6. Compare three scenarios
    all_three = [store.get(baseline.id), store.get(lower_price.id), store.get(aggressive.id)]
    table = compare_scenarios(all_three)
    assert table["scenarios"] == ["gestnova-baseline", "pricing-250", "pricing-250+infra-reduced"]
    # Baseline revenue should be highest
    revs = table["metrics"]["revenue_y1"]
    assert revs[0] > revs[1]

    # 7. Sensitivity sweep around aggressive
    sens = sensitivity_1d(
        store.get(aggressive.id),
        variable="revenue.sources[0].acquisition.cac_per_customer",
        values=[400, 600, 800, 1000, 1200],
        metric="ltv_cac_end",
    )
    assert len(sens["points"]) == 5
    # Higher CAC should reduce LTV/CAC ratio
    first_ltv_cac = sens["points"][0]["metric_value"]
    last_ltv_cac = sens["points"][-1]["metric_value"]
    assert first_ltv_cac > last_ltv_cac

    # 8. Export all formats from baseline
    to_csv(base_results, view="pnl", path=str(tmp_path / "pnl.csv"))
    to_csv(base_results, view="cashflow", path=str(tmp_path / "cf.csv"))
    to_xlsx(base_results, path=str(tmp_path / "model.xlsx"))
    payload = to_json(base_results)
    parsed = json.loads(payload)
    report = to_markdown_report(base_results)

    assert (tmp_path / "pnl.csv").exists()
    assert (tmp_path / "cf.csv").exists()
    assert (tmp_path / "model.xlsx").exists()
    assert "summary" in parsed
    assert "# " in report

    # 9. Canonical protection
    with pytest.raises(PermissionError):
        store.delete(baseline.id)

    # 10. Delete non-canonical works
    store.delete(aggressive.id)
    assert store.get(aggressive.id).is_deleted is True
