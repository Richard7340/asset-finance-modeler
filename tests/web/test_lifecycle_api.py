from fastapi.testclient import TestClient


def _client(monkeypatch, tmp_path):
    monkeypatch.setenv("SIM_TOKEN", "tk")
    monkeypatch.setenv("SIM_ONLY", "1")
    monkeypatch.setenv("ASSET_FINANCE_DB_PATH", str(tmp_path))
    from asset_finance_modeler.mcp_server.http_server import app
    return TestClient(app)


def test_new_asset_is_opportunity_by_default(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    aid = c.post("/api/assets?t=tk",
                 json={"model_id": "bess_20mw_4h", "name": "B", "overrides": {}}).json()["id"]
    lst = c.get("/api/assets?t=tk").json()["assets"]
    row = next(a for a in lst if a["id"] == aid)
    assert row["lifecycle"] == "opportunity"


def test_promote_to_operational(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    aid = c.post("/api/assets?t=tk",
                 json={"model_id": "bess_20mw_4h", "name": "B", "overrides": {}}).json()["id"]
    r = c.patch(f"/api/assets/{aid}/lifecycle?t=tk",
                json={"lifecycle": "operational", "tracking_frequency": "monthly"})
    assert r.status_code == 200
    body = r.json()
    assert body["lifecycle"] == "operational"
    assert body["base_locked"] is True
    assert body["commissioning_date"]  # fecha fijada
    assert body["tracking_frequency"] == "monthly"


def test_list_filters_by_lifecycle(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    a1 = c.post("/api/assets?t=tk", json={"model_id": "bess_20mw_4h", "name": "A1"}).json()["id"]
    a2 = c.post("/api/assets?t=tk", json={"model_id": "bess_20mw_4h", "name": "A2"}).json()["id"]
    c.patch(f"/api/assets/{a1}/lifecycle?t=tk", json={"lifecycle": "operational"})
    op = c.get("/api/assets?t=tk&lifecycle=operational").json()["assets"]
    assert [a["id"] for a in op] == [a1]
    opp = c.get("/api/assets?t=tk&lifecycle=opportunity").json()["assets"]
    assert [a["id"] for a in opp] == [a2]


def test_demote_to_opportunity(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    aid = c.post("/api/assets?t=tk", json={"model_id": "bess_20mw_4h", "name": "B"}).json()["id"]
    c.patch(f"/api/assets/{aid}/lifecycle?t=tk", json={"lifecycle": "operational"})
    body = c.patch(f"/api/assets/{aid}/lifecycle?t=tk", json={"lifecycle": "opportunity"}).json()
    assert body["lifecycle"] == "opportunity"
    assert body["base_locked"] is False
    assert body["commissioning_date"] is None


def test_patch_unknown_asset_404(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    r = c.patch("/api/assets/scn-nope/lifecycle?t=tk", json={"lifecycle": "operational"})
    assert r.status_code == 404


def test_patch_invalid_lifecycle_422(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    aid = c.post("/api/assets?t=tk", json={"model_id": "bess_20mw_4h", "name": "B"}).json()["id"]
    r = c.patch(f"/api/assets/{aid}/lifecycle?t=tk", json={"lifecycle": "bogus"})
    assert r.status_code == 422
