from asset_finance_modeler.intelligence.recall import ScenarioRecall


def test_index_and_search():
    recall = ScenarioRecall()
    recall.index_scenario("scn-1", "Solar Sevilla 50MW", "FV utility-scale en Andalucía",
                          "solar_pv", ["renewable", "spain"],
                          {"revenue_y1": 3_000_000, "irr_project": 0.085})
    results = recall.search("planta solar en España")
    assert len(results) >= 1
    assert results[0].scenario_id == "scn-1"


def test_multiple_scenarios():
    recall = ScenarioRecall()
    recall.index_scenario("scn-1", "Solar Sevilla", "", "solar_pv", [], {"irr": 0.08})
    recall.index_scenario("scn-2", "BESS Madrid", "", "bess", [], {"irr": 0.10})
    recall.index_scenario("scn-3", "Wind Galicia", "", "wind", [], {"irr": 0.07})
    results = recall.search("batería almacenamiento")
    assert results[0].scenario_id == "scn-2"


def test_search_empty():
    recall = ScenarioRecall()
    results = recall.search("anything")
    assert results == []


def test_count():
    recall = ScenarioRecall()
    assert recall.count == 0
    recall.index_scenario("scn-1", "Test", "", "solar_pv", [], {})
    assert recall.count == 1


def test_search_by_kpi():
    recall = ScenarioRecall()
    recall.index_scenario("scn-1", "High IRR Project", "", "solar_pv", [],
                          {"irr_project": 0.15, "enterprise_value": 20_000_000})
    recall.index_scenario("scn-2", "Low IRR Project", "", "solar_pv", [],
                          {"irr_project": 0.05, "enterprise_value": 5_000_000})
    results = recall.search("high return project IRR 15%")
    assert results[0].scenario_id == "scn-1"


def test_top_k_limit():
    recall = ScenarioRecall()
    for i in range(10):
        recall.index_scenario(f"scn-{i}", f"Project {i}", "", "solar_pv", [], {})
    results = recall.search("project", top_k=3)
    assert len(results) == 3
