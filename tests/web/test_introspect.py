from asset_finance_modeler.web_api.introspect import schema_tree, set_by_path


def test_schema_tree_flattens_nested_and_lists():
    cfg = {"production": {"capacity_mwp": 4.76}, "revenue": [{"price_eur_per_unit": 43.0}], "financing": {"senior": {"interest_rate": 0.032}}}
    leaves = {l["path"]: l for l in schema_tree(cfg)}
    assert "production.capacity_mwp" in leaves
    assert "revenue[0].price_eur_per_unit" in leaves
    assert "financing.senior.interest_rate" in leaves
    assert leaves["production.capacity_mwp"]["type"] == "number"
    assert leaves["production.capacity_mwp"]["section"] == "production"


def test_set_by_path_nested_and_indexed():
    cfg = {"production": {"capacity_mwp": 4.76}, "revenue": [{"price_eur_per_unit": 43.0}]}
    out = set_by_path(cfg, "revenue[0].price_eur_per_unit", 50.0)
    assert out["revenue"][0]["price_eur_per_unit"] == 50.0
    assert cfg["revenue"][0]["price_eur_per_unit"] == 43.0   # input not mutated
    out2 = set_by_path(cfg, "production.capacity_mwp", 5.0)
    assert out2["production"]["capacity_mwp"] == 5.0
