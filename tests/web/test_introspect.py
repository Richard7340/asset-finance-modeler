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


def test_inert_infra_inputs_hidden_from_schema_tree():
    """E4: editable leaves that move no KPI are not exposed in the schema tree,
    so a user is never shown an input that does nothing."""
    cfg = load_preset("solar_pv_50mw_spain").model_dump()
    paths = {l["path"] for l in schema_tree(cfg)}
    for inert in (
        "financing.reserves.mra_eur",
        "financing.reserves.working_capital_eur",
        "financing.equity.target_irr",
        # distribution_lock_years ya no es inerte (26-sep): retrasa el reparto al socio.
        "taxes.r_and_d_deduction_pct",
        "meta.inflation_annual",  # SaaS-only field, inert on infra
    ):
        assert inert not in paths, inert
    # A live input in the same sections is still exposed (we hid leaves, not nodes).
    assert "financing.reserves.dsra_months" in paths


def test_inert_sla_uptime_target_hidden():
    """The SLA stream's uptime_target moves no KPI → hidden."""
    cfg = load_preset("datacenter_10mw_tier3").model_dump()
    paths = {l["path"] for l in schema_tree(cfg)}
    assert not any(p.endswith(".uptime_target") for p in paths), [
        p for p in paths if "uptime_target" in p
    ]


def test_inflation_annual_visible_for_saas():
    """meta.inflation_annual IS live for SaaS (escalates fixed opex) → exposed."""
    cfg = {"meta": {"name": "x", "inflation_annual": 0.025}}
    paths = {l["path"] for l in schema_tree(cfg, asset_type="saas")}
    assert "meta.inflation_annual" in paths
    # ... but hidden for the default (non-SaaS) tree.
    paths2 = {l["path"] for l in schema_tree(cfg)}
    assert "meta.inflation_annual" not in paths2


def test_set_by_path_nested_and_indexed():
    cfg = {"production": {"capacity_mwp": 4.76}, "revenue": [{"price_eur_per_unit": 43.0}]}
    out = set_by_path(cfg, "revenue[0].price_eur_per_unit", 50.0)
    assert out["revenue"][0]["price_eur_per_unit"] == 50.0
    assert cfg["revenue"][0]["price_eur_per_unit"] == 43.0   # input not mutated
    out2 = set_by_path(cfg, "production.capacity_mwp", 5.0)
    assert out2["production"]["capacity_mwp"] == 5.0


def test_set_by_path_rejects_nonexistent_leaf():
    """A2: a typo'd LEAF key (valid parent, no such leaf) must raise, not be
    silently accepted (which would 200 with no effect)."""
    import pytest  # noqa: PLC0415

    from asset_finance_modeler.web_api.introspect import InvalidPathError  # noqa: PLC0415

    cfg = {"financing": {"senior": {"interest_rate": 0.032}}, "meta": {"name": "x"}}
    with pytest.raises(InvalidPathError):
        set_by_path(cfg, "financing.senior.bogus", 0.05)
    with pytest.raises(InvalidPathError):
        set_by_path(cfg, "meta.tax_rate", 0.25)
    # an existing leaf still works
    out = set_by_path(cfg, "financing.senior.interest_rate", 0.05)
    assert out["financing"]["senior"]["interest_rate"] == 0.05


def test_set_by_path_allows_optional_curve_leaf_currently_none():
    """A2 must NOT break attaching a curve to a stream whose curve field is
    currently None — the key exists in model_dump() so it is settable."""
    cfg = load_preset("solar_pv_50mw_spain").model_dump()
    out = set_by_path(cfg, "revenue[1].price_curve_name", "merchant_es_baseload")
    # find the merchant stream and confirm the curve name landed
    assert out["revenue"][1]["price_curve_name"] == "merchant_es_baseload"
