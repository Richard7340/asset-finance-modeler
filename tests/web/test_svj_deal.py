from asset_finance_modeler.deals.svj import build_svj_xlsx, run_svj, svj_input_spec


def test_svj_input_spec_exposes_full_tree():
    leaves = svj_input_spec()
    paths = {leaf["path"] for leaf in leaves}
    # Full FV + BESS preset trees plus the debt/valuation stack.
    assert len(leaves) > 100
    assert any(p.startswith("fv.") for p in paths)
    assert any(p.startswith("bess.") for p in paths)
    assert {"senior.interest_rate", "subordinated.interest_rate", "wacc"} <= paths


def test_svj_legacy_drivers_still_run():
    # The 6 original drivers remain valid override keys (backward compat).
    base = run_svj({})["kpis"]
    # Project-NPV drivers.
    for key, val in (
        ("spread_capture", 0.95),
        ("ancillary_base", 80000),
        ("bess_capex_eur_kwh", 150),
        ("fv_ppa_price", 55),
    ):
        assert run_svj({key: val})["kpis"]["npv_hybrid"] != base["npv_hybrid"]
    # Subordinated-debt drivers move investor metrics.
    assert run_svj({"sub_rate": 0.10})["kpis"]["moic_sub"] != base["moic_sub"]
    assert run_svj({"sub_tenor_years": 9})["kpis"]["moic_sub"] != base["moic_sub"]


def test_run_svj_reproduces_validated_kpis():
    r = run_svj({})
    k = r["kpis"]
    assert 0.7e6 < k["npv_hybrid"] < 1.4e6
    assert 1.25 < k["moic_sub"] < 1.45
    assert k["npv_fv"] < 0 < k["npv_bess"]
    assert len(r["cashflows"]["years"]) == 30
    assert len(r["curves"]["spread"]) == 30
    assert "bridge" in r and "dscr_profile" in r


def test_run_svj_overrides_move_kpis():
    base = run_svj({})["kpis"]["npv_hybrid"]
    up = run_svj({"spread_capture": 0.95})["kpis"]["npv_hybrid"]
    assert up > base


def test_build_svj_xlsx_returns_bytes():
    data = build_svj_xlsx({})
    assert isinstance(data, (bytes, bytearray)) and len(data) > 1000
