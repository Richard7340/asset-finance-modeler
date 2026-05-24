from asset_finance_modeler.intelligence.benchmarks.cache import BenchmarkCache
from asset_finance_modeler.intelligence.benchmarks.engine import BenchmarkEngine
from asset_finance_modeler.intelligence.knowledge.loader import KBLoader


def test_benchmark_found_in_kb():
    engine = BenchmarkEngine(KBLoader())
    result = engine.search("capex_per_kwp_eur", "solar_pv", "ES")
    assert result is not None
    assert result.value == 550
    assert result.confidence >= 0.85
    assert "Lazard" in result.source

def test_benchmark_not_found():
    engine = BenchmarkEngine(KBLoader())
    result = engine.search("nonexistent_field", "solar_pv", "ES")
    assert result is None

def test_benchmark_result_has_methodology():
    engine = BenchmarkEngine(KBLoader())
    result = engine.search("capex_per_kwp_eur", "solar_pv", "ES")
    assert result is not None
    assert result.methodology != ""

def test_cache_set_and_get(tmp_path):
    cache = BenchmarkCache(str(tmp_path / "cache.db"))
    cache.set("test_key", {"value": 42, "source": "test"})
    result = cache.get("test_key")
    assert result is not None
    assert result["value"] == 42

def test_cache_miss(tmp_path):
    cache = BenchmarkCache(str(tmp_path / "cache.db"))
    assert cache.get("nonexistent") is None

def test_cache_overwrite(tmp_path):
    cache = BenchmarkCache(str(tmp_path / "cache.db"))
    cache.set("key", {"v": 1})
    cache.set("key", {"v": 2})
    assert cache.get("key")["v"] == 2
