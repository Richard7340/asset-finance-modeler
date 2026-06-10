from asset_finance_modeler.deals.svj import build_svj_xlsx, run_svj, svj_input_spec


def test_svj_input_spec_has_key_drivers():
    keys = {i["key"] for i in svj_input_spec()}
    assert {"spread_capture", "ancillary_base", "bess_capex_eur_kwh", "sub_tenor_years", "sub_rate"} <= keys


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
