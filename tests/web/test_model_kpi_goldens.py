"""A5 (HIGH coverage): per-model golden KPIs at default inputs.

Pins the surfaced headline KPIs (npv / irr_project / irr_equity / dscr_min) of
every non-SVJ model at its default config. Tight tolerances so any silent
numeric drift in the engine — a changed default, an accidental sign flip, a
broken aggregation — fails loudly here, model by model.

Values are the CURRENT correct values (post Pasada 2 + Pasada 3 A3/A4): NPV is
the unlevered project NPV; irr_equity reflects the DSRA reserve timing wired
into the equity cashflow in A3; SaaS has no project IRR/DSCR (None → "n/a").
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _client(monkeypatch):
    monkeypatch.setenv("SIM_TOKEN", "tk")
    monkeypatch.setenv("SIM_ONLY", "1")
    from asset_finance_modeler.mcp_server.http_server import app  # noqa: PLC0415

    return TestClient(app)


# (model_id, npv, irr_project, irr_equity, dscr_min)
_GOLDENS: list[tuple[str, int, float | None, float | None, float | None]] = [
    ("bess_20mw_4h", 2_369_756, 0.099, 0.1466, 1.64),
    ("datacenter_10mw_tier3", 13_650_321, 0.1345, 0.0945, 1.25),
    ("solar_pv_50mw_spain", 2_354_276, 0.0825, 0.125, 2.27),
    ("svj_bess_cordoba", 2_382_001, 0.1832, 0.1198, 0.94),
    ("svj_fv_cordoba", -146_919, 0.0292, 0.0295, 1.02),
    ("wind_onshore_30mw_spain", 611_917, 0.0672, 0.0703, 1.3),
    ("business_generic", 1_102_585, 0.1384, 0.1384, 0.0),
    ("business_industrial", 6_724_877, 0.1547, 0.1547, 2.2),
    ("business_restaurant", 747_365, 0.209, 0.209, 0.0),
    ("real_estate_rental", 286_320, 0.0754, 0.0754, 1.59),
    ("inmueble_alquiler", 2_316, 0.043916, 0.062689, 1.02),
    ("saas_gestnova", 4_549_591, None, None, None),
]


def test_all_eleven_non_svj_models_covered():
    """The golden table must cover every non-SVJ model the API lists, so a new
    model can never slip in without a pinned KPI golden."""
    import os  # noqa: PLC0415

    os.environ["SIM_TOKEN"] = "tk"
    os.environ["SIM_ONLY"] = "1"
    from asset_finance_modeler.mcp_server.http_server import app  # noqa: PLC0415

    c = TestClient(app)
    listed = {
        m["id"]
        for m in c.get("/api/models?t=tk").json()["models"]
        if m["id"] != "svj_hybrid"
    }
    pinned = {g[0] for g in _GOLDENS}
    assert pinned == listed, ("drift in model list", pinned ^ listed)


@pytest.mark.parametrize("model_id,npv,irr_p,irr_e,dscr", _GOLDENS, ids=[g[0] for g in _GOLDENS])
def test_model_kpi_golden(monkeypatch, model_id, npv, irr_p, irr_e, dscr):
    c = _client(monkeypatch)
    k = c.post(f"/api/models/{model_id}/run?t=tk", json={"overrides": {}}).json()["kpis"]
    assert abs(k["npv"] - npv) <= 1, ("npv drift", model_id, k["npv"])
    _assert_close(k["irr_project"], irr_p, "irr_project", model_id)
    _assert_close(k["irr_equity"], irr_e, "irr_equity", model_id)
    _assert_close(k["dscr_min"], dscr, "dscr_min", model_id)


def _assert_close(got, expected, label, model_id):
    if expected is None:
        assert got is None, (f"{label} drift (expected n/a)", model_id, got)
    else:
        assert got is not None, (f"{label} drift (got n/a)", model_id)
        assert abs(got - expected) <= 1e-4, (f"{label} drift", model_id, got, expected)
