from asset_finance_modeler.intelligence.learning import MetaLearner


def _solar_results():
    return {
        "summary": {"total_capex": 22_500_000, "revenue_y1": 3_200_000},
        "project_kpis": {
            "irr_project": 0.085, "irr_equity": 0.14,
            "dscr_min": 1.28, "dscr_avg": 1.45,
            "lcoe": 38.5, "payback_years": 8.2,
        },
    }


def test_extract_dscr_insight():
    learner = MetaLearner()
    insights = learner.extract_insights("scn-1", "solar_pv", _solar_results())
    dscr = [i for i in insights if i.metric == "dscr_min"]
    assert len(dscr) == 1
    assert dscr[0].actual_value == 1.28
    assert "1.30" in dscr[0].observation


def test_extract_irr_insights():
    learner = MetaLearner()
    insights = learner.extract_insights("scn-1", "solar_pv", _solar_results())
    irr_p = [i for i in insights if i.metric == "irr_project"]
    assert len(irr_p) == 1
    assert "above" in irr_p[0].observation
    irr_e = [i for i in insights if i.metric == "irr_equity"]
    assert len(irr_e) == 1
    assert "exceeds" in irr_e[0].observation


def test_extract_lcoe():
    learner = MetaLearner()
    insights = learner.extract_insights("scn-1", "solar_pv", _solar_results())
    lcoe = [i for i in insights if i.metric == "lcoe"]
    assert len(lcoe) == 1
    assert lcoe[0].actual_value == 38.5


def test_extract_payback():
    learner = MetaLearner()
    insights = learner.extract_insights("scn-1", "solar_pv", _solar_results())
    pb = [i for i in insights if i.metric == "payback_years"]
    assert len(pb) == 1
    assert pb[0].actual_value == 8.2


def test_preset_comparison():
    learner = MetaLearner()
    preset = {"irr_project": 0.07, "dscr_min": 1.30}
    insights = learner.extract_insights("scn-1", "solar_pv", _solar_results(), preset_defaults=preset)
    vs_preset = [i for i in insights if "vs_preset" in i.metric]
    assert len(vs_preset) >= 1


def test_accumulates_insights():
    learner = MetaLearner()
    learner.extract_insights("scn-1", "solar_pv", _solar_results())
    learner.extract_insights("scn-2", "bess", _solar_results())
    assert len(learner.all_insights) >= 8


def test_filter_by_asset_type():
    learner = MetaLearner()
    learner.extract_insights("scn-1", "solar_pv", _solar_results())
    learner.extract_insights("scn-2", "bess", _solar_results())
    solar = learner.insights_for_asset("solar_pv")
    bess = learner.insights_for_asset("bess")
    assert all(i.asset_type == "solar_pv" for i in solar)
    assert all(i.asset_type == "bess" for i in bess)


def test_clear():
    learner = MetaLearner()
    learner.extract_insights("scn-1", "solar_pv", _solar_results())
    assert len(learner.all_insights) > 0
    learner.clear()
    assert len(learner.all_insights) == 0


def test_empty_results():
    learner = MetaLearner()
    insights = learner.extract_insights("scn-1", "solar_pv", {"summary": {}, "project_kpis": {}})
    assert len(insights) == 0
