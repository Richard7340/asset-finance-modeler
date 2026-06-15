from fastapi.testclient import TestClient


def _client(monkeypatch, tmp_path):
    monkeypatch.setenv("SIM_TOKEN", "tk")
    monkeypatch.setenv("SIM_ONLY", "1")
    monkeypatch.setenv("ASSET_FINANCE_DB_PATH", str(tmp_path))
    from asset_finance_modeler.mcp_server.http_server import app
    return TestClient(app)


def test_portfolio_aggregates_saved_assets(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    c.post("/api/assets?t=tk", json={"model_id": "business_restaurant", "name": "Resto", "overrides": {}})
    c.post("/api/assets?t=tk", json={"model_id": "bess_20mw_4h", "name": "BESS", "overrides": {}})
    p = c.get("/api/portfolio?t=tk").json()
    assert p["totals"]["count"] == 2
    assert len(p["assets"]) == 2
    assert p["totals"]["npv"] != 0
    names = {a["name"] for a in p["assets"]}
    assert {"Resto", "BESS"} == names


def test_portfolio_enriched_and_svj_capex_nonzero(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    c.post("/api/assets?t=tk", json={"model_id": "svj_hybrid", "name": "SVJ", "overrides": {}})
    c.post("/api/assets?t=tk", json={"model_id": "bess_20mw_4h", "name": "BESS", "overrides": {}})
    p = c.get("/api/portfolio?t=tk").json()
    by = {a["name"]: a for a in p["assets"]}
    assert by["SVJ"]["capex"] > 1_000_000  # ya no es 0 (≈6.28M)
    assert by["SVJ"]["revenue_y1"] > 0
    for a in p["assets"]:
        assert "irr" in a and "yield_pct" in a


def test_portfolio_surfaces_broken_assets_in_skipped(monkeypatch, tmp_path):
    """A saved asset that fails to re-run must appear in `skipped` with its id,
    name and error — not silently vanish (FIX 4).

    Both assets save fine; we then make re-valuing the broken one raise (as
    would happen if inputs drift incompatible, a preset is renamed, etc.)."""
    c = _client(monkeypatch, tmp_path)
    good = c.post(
        "/api/assets?t=tk",
        json={"model_id": "bess_20mw_4h", "name": "Good BESS", "overrides": {}},
    ).json()
    bad = c.post(
        "/api/assets?t=tk",
        json={"model_id": "bess_20mw_4h", "name": "Broken One", "overrides": {}},
    ).json()

    from asset_finance_modeler.web_api import assets as assets_mod

    real_run = assets_mod._run_model

    def _flaky_run(model_id, overrides):
        # Re-running the 'Broken One' fails; everything else runs normally.
        if overrides.get("_force_fail"):
            raise ValueError("boom: incompatible inputs")
        return real_run(model_id, overrides)

    # Mark the bad asset's stored overrides so the flaky runner fails on it.
    store = assets_mod._store()
    rec = store.get(bad["id"])
    rec.inputs_snapshot = {"model_id": rec.base_model, "overrides": {"_force_fail": True}}
    store.save(rec)

    monkeypatch.setattr(assets_mod, "_run_model", _flaky_run)

    p = c.get("/api/portfolio?t=tk").json()

    # Existing shape preserved.
    assert "assets" in p and "totals" in p
    good_names = {a["name"] for a in p["assets"]}
    assert "Good BESS" in good_names
    assert "Broken One" not in good_names  # not counted as a valued asset

    # New: the broken asset is visible in `skipped`.
    assert "skipped" in p
    skipped_ids = {s["id"] for s in p["skipped"]}
    assert bad["id"] in skipped_ids
    skipped_entry = next(s for s in p["skipped"] if s["id"] == bad["id"])
    assert skipped_entry["name"] == "Broken One"
    assert skipped_entry["error"]  # non-empty error string
    assert good["id"] not in skipped_ids
