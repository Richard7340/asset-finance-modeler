from asset_finance_modeler.intelligence.knowledge.loader import KBLoader


def test_load_intents():
    loader = KBLoader()
    intents = loader.load_intents()
    assert len(intents) >= 7
    solar = [i for i in intents if i.asset_type == "solar_pv"]
    assert len(solar) == 1
    assert "FV" in solar[0].patterns


def test_load_questions_solar():
    loader = KBLoader()
    questions = loader.load_questions("solar_pv")
    assert len(questions) >= 5
    assert questions[0].order <= questions[1].order


def test_load_questions_generic_fallback():
    loader = KBLoader()
    questions = loader.load_questions("unknown_type")
    assert len(questions) >= 2


def test_load_benchmarks():
    loader = KBLoader()
    benchmarks = loader.load_benchmarks()
    assert len(benchmarks) >= 3
    solar_capex = [b for b in benchmarks if b.field == "capex_per_kwp_eur"]
    assert len(solar_capex) >= 1


def test_load_concepts():
    loader = KBLoader()
    concepts = loader.load_concepts()
    assert len(concepts) >= 5


def test_load_validations():
    loader = KBLoader()
    rules = loader.load_validations()
    assert len(rules) >= 3


def test_load_quick_starts():
    loader = KBLoader()
    presets = loader.load_quick_starts()
    solar_es = [p for p in presets if p.asset_type == "solar_pv" and p.region == "ES"]
    assert len(solar_es) >= 1
    assert "production.capacity_mwp" in solar_es[0].defaults


def test_detect_asset_type():
    loader = KBLoader()
    assert loader.detect_asset_type("tengo una planta solar de 50MW") == "solar_pv"
    assert loader.detect_asset_type("quiero evaluar un BESS") == "bess"
    assert loader.detect_asset_type("algo desconocido") is None


def test_find_benchmark():
    loader = KBLoader()
    bm = loader.find_benchmark("capex_per_kwp_eur", "solar_pv", "ES")
    assert bm is not None
    assert bm.value == 550
