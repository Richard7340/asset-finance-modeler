from fastapi.testclient import TestClient


def _client(monkeypatch, tmp_path):
    monkeypatch.setenv("SIM_TOKEN", "tk")
    monkeypatch.setenv("SIM_ONLY", "1")
    monkeypatch.setenv("ASSET_FINANCE_DB_PATH", str(tmp_path))
    from asset_finance_modeler.mcp_server.http_server import app
    return TestClient(app)


def _operational_asset(c) -> str:
    aid = c.post(
        "/api/assets?t=tk",
        json={"model_id": "bess_20mw_4h", "name": "B", "overrides": {}},
    ).json()["id"]
    c.patch(
        f"/api/assets/{aid}/lifecycle?t=tk",
        json={"lifecycle": "operational", "tracking_frequency": "monthly"},
    )
    return aid


def test_lines_non_empty(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    aid = _operational_asset(c)
    r = c.get(f"/api/assets/{aid}/lines?t=tk")
    assert r.status_code == 200
    lines = r.json()["lines"]
    assert lines
    paths = {ln["path"] for ln in lines}
    assert "income_statement.rows.revenue" in paths
    for ln in lines:
        assert set(ln.keys()) >= {"path", "label", "unit"}


def test_lines_requires_token(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    aid = _operational_asset(c)
    assert c.get(f"/api/assets/{aid}/lines").status_code == 401


def test_lines_unknown_asset_404(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    assert c.get("/api/assets/scn-nope/lines?t=tk").status_code == 404


def test_post_single_actual_and_list(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    aid = _operational_asset(c)
    r = c.post(
        f"/api/assets/{aid}/actuals?t=tk",
        json={
            "actuals": [
                {
                    "period_start": "2026-01-01",
                    "line_path": "income_statement.rows.revenue",
                    "value": 1234.0,
                    "unit": "EUR",
                }
            ]
        },
    )
    assert r.status_code == 200
    assert len(r.json()["ids"]) == 1
    rows = c.get(f"/api/assets/{aid}/actuals?t=tk").json()["actuals"]
    assert len(rows) == 1
    assert rows[0]["value"] == 1234.0


def test_post_batch(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    aid = _operational_asset(c)
    r = c.post(
        f"/api/assets/{aid}/actuals?t=tk",
        json={
            "actuals": [
                {"period_start": "2026-01-01",
                 "line_path": "income_statement.rows.revenue", "value": 10.0},
                {"period_start": "2026-02-01",
                 "line_path": "income_statement.rows.revenue", "value": 20.0},
            ]
        },
    )
    assert r.status_code == 200
    assert len(r.json()["ids"]) == 2
    rows = c.get(
        f"/api/assets/{aid}/actuals?t=tk&line_path=income_statement.rows.revenue"
    ).json()["actuals"]
    assert len(rows) == 2


def test_post_unknown_asset_404(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    r = c.post(
        "/api/assets/scn-nope/actuals?t=tk",
        json={"actuals": [{"period_start": "2026-01-01", "line_path": "x", "value": 1.0}]},
    )
    assert r.status_code == 404


def test_delete_actual(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    aid = _operational_asset(c)
    actual_id = c.post(
        f"/api/assets/{aid}/actuals?t=tk",
        json={"actuals": [{"period_start": "2026-01-01",
                           "line_path": "income_statement.rows.revenue", "value": 1.0}]},
    ).json()["ids"][0]
    assert c.delete(f"/api/assets/{aid}/actuals/{actual_id}?t=tk").status_code == 200
    assert c.get(f"/api/assets/{aid}/actuals?t=tk").json()["actuals"] == []


def test_post_requires_token(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    aid = _operational_asset(c)
    r = c.post(
        f"/api/assets/{aid}/actuals",
        json={"actuals": [{"period_start": "2026-01-01", "line_path": "x", "value": 1.0}]},
    )
    assert r.status_code == 401
