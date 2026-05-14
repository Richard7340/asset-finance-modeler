"""In-process smoke test exercising the MCP server registry end-to-end
without spawning a subprocess (which is brittle on macOS .venv hidden flag)."""
from asset_finance_modeler.mcp_server.registry import build_registry
from asset_finance_modeler.store.scenarios import SQLiteScenarioStore


def test_full_workflow_via_registry(tmp_path):
    store = SQLiteScenarioStore(str(tmp_path / "smoke.db"))
    store.initialize()
    reg = build_registry(store)

    # 1. Discovery
    models = reg["finance.simulate.list_models"].handler({})
    assert any(m["name"] == "gestnova" for m in models["models"])
    schema = reg["finance.simulate.describe_schema"].handler({"model": "gestnova"})
    assert "revenue" in schema["schema"]["properties"]
    presets = reg["finance.simulate.list_presets"].handler({"model": "saas"})
    assert any(p["key"] == "gestnova" for p in presets["presets"])

    # 2. Load baseline
    baseline = reg["finance.simulate.load_baseline"].handler(
        {"model": "gestnova", "preset": "gestnova"}
    )
    baseline_id = baseline["scenario_id"]

    # 3. Branch + run
    create = reg["finance.simulate.create_scenario"].handler
    pricing_200 = create({
        "name": "pricing-200",
        "base_scenario_id": baseline_id,
        "overrides": {"revenue.sources[0].pricing.per_unit_per_period": 200},
    })["scenario_id"]
    pricing_400 = create({
        "name": "pricing-400",
        "base_scenario_id": baseline_id,
        "overrides": {"revenue.sources[0].pricing.per_unit_per_period": 400},
    })["scenario_id"]

    run = reg["finance.simulate.run"].handler
    for sid in (baseline_id, pricing_200, pricing_400):
        run({"scenario_id": sid})

    # 4. Compare
    table = reg["finance.simulate.compare"].handler({
        "scenario_ids": [baseline_id, pricing_200, pricing_400]
    })["table"]
    assert len(table["scenarios"]) == 3
    revs = table["metrics"]["revenue_y1"]
    assert revs[1] < revs[0] < revs[2]

    # 5. Sensitivity
    sens = reg["finance.simulate.sensitivity_1d"].handler({
        "scenario_id": baseline_id,
        "variable": "revenue.sources[0].retention.monthly_churn_rate",
        "values": [0.01, 0.03, 0.05],
        "metric": "enterprise_value",
    })
    assert len(sens["points"]) == 3
    evs = [p["metric_value"] for p in sens["points"]]
    assert evs[0] > evs[2]  # lower churn → higher EV

    # 6. Export
    out_csv = tmp_path / "pnl.csv"
    export_result = reg["finance.simulate.export"].handler({
        "scenario_id": baseline_id,
        "format": "csv",
        "view": "pnl",
        "path": str(out_csv),
    })
    assert export_result["ok"] is True
    assert out_csv.exists()

    report = reg["finance.simulate.export"].handler({
        "scenario_id": baseline_id,
        "format": "markdown_report",
    })
    assert "content" in report

    # 7. Genealogy
    g = reg["finance.simulate.get_genealogy"].handler({"scenario_id": pricing_200})
    assert g["ancestors"][0]["name"] == "gestnova-baseline"

    # 8. External delegation flow
    fetch = reg["finance.simulate.fetch_external"].handler({
        "scenario_id": baseline_id,
        "field_path": "external_data.benchmarks.saas_churn_p50",
        "query": "SaaS B2B median monthly churn 2025",
    })
    assert "query" in fetch
    set_result = reg["finance.simulate.set_external"].handler({
        "scenario_id": baseline_id,
        "field_path": "external_data.benchmarks.saas_churn_p50",
        "value": 0.018,
        "source": "ChartMogul SaaS Benchmarks 2025",
    })
    assert set_result["ok"] is True

    # 9. Canonical protection
    delete = reg["finance.simulate.delete_scenario"].handler
    fail = delete({"scenario_id": baseline_id})
    assert "error" in fail
    ok = delete({"scenario_id": pricing_400})
    assert ok.get("ok") is True

    # 10. List scenarios
    listing = reg["finance.simulate.list_scenarios"].handler({})
    names = [s["name"] for s in listing["scenarios"]]
    assert "gestnova-baseline" in names
    # pricing_400 was deleted → not in default listing
    assert "pricing-400" not in names

    # 11. Track stubs return v2 error
    track = reg["finance.track.import_real_data"].handler({"source": "holded"})
    assert "v2" in track["error"].lower() or "not implemented" in track["error"].lower()
