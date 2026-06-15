from asset_finance_modeler.assets.infrastructure.loader import load_preset
from asset_finance_modeler.web_api.introspect import schema_tree, set_by_path


def test_schema_tree_flattens_nested_and_lists():
    cfg = {"production": {"capacity_mwp": 4.76}, "revenue": [{"price_eur_per_unit": 43.0}], "financing": {"senior": {"interest_rate": 0.032}}}
    leaves = {l["path"]: l for l in schema_tree(cfg)}
    assert "production.capacity_mwp" in leaves
    assert "revenue[0].price_eur_per_unit" in leaves
    assert "financing.senior.interest_rate" in leaves
    assert leaves["production.capacity_mwp"]["type"] == "number"
    assert leaves["production.capacity_mwp"]["section"] == "production"


def test_optional_curve_fields_surface_even_when_none():
    # A None leaf that is NOT a known-optional curve field stays hidden.
    cfg = {"production": {"irradiation_profile": None, "capacity_mwp": 4.76}}
    leaves = {l["path"]: l for l in schema_tree(cfg)}
    assert "production.irradiation_profile" not in leaves

    # But the known-optional curve fields surface even when None, so the
    # platform can attach a library curve via the API.
    cfg2 = {
        "revenue": [
            {"type": "merchant", "price_curve_name": None, "price_points": None},
        ]
    }
    leaves2 = {l["path"]: l for l in schema_tree(cfg2)}
    assert "revenue[0].price_curve_name" in leaves2
    assert leaves2["revenue[0].price_curve_name"]["value"] is None
    assert leaves2["revenue[0].price_curve_name"]["type"] == "text"


def test_standalone_solar_exposes_merchant_curve_field():
    # The solar preset's merchant stream has no curve set; the platform still
    # needs to see the slot to attach one. model_dump() yields None there.
    cfg = load_preset("solar_pv_50mw_spain").model_dump()
    leaves = {l["path"] for l in schema_tree(cfg)}
    # revenue[1] is the merchant stream.
    assert "revenue[1].price_curve_name" in leaves


def test_set_by_path_nested_and_indexed():
    cfg = {"production": {"capacity_mwp": 4.76}, "revenue": [{"price_eur_per_unit": 43.0}]}
    out = set_by_path(cfg, "revenue[0].price_eur_per_unit", 50.0)
    assert out["revenue"][0]["price_eur_per_unit"] == 50.0
    assert cfg["revenue"][0]["price_eur_per_unit"] == 43.0   # input not mutated
    out2 = set_by_path(cfg, "production.capacity_mwp", 5.0)
    assert out2["production"]["capacity_mwp"] == 5.0
