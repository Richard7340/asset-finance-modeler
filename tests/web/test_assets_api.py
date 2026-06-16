from fastapi.testclient import TestClient


def _client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("SIM_TOKEN", "tk")
    monkeypatch.setenv("SIM_ONLY", "1")
    monkeypatch.setenv("ASSET_FINANCE_DB_PATH", str(tmp_path))
    from asset_finance_modeler.mcp_server.http_server import app
    return TestClient(app)


def test_assets_crud(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    created = c.post("/api/assets?t=tk", json={"model_id": "bess_20mw_4h", "name": "Mi BESS", "overrides": {}}).json()
    aid = created["id"]
    lst = c.get("/api/assets?t=tk").json()["assets"]
    assert any(a["id"] == aid and a["name"] == "Mi BESS" for a in lst)
    got = c.get(f"/api/assets/{aid}?t=tk").json()
    assert got["model_id"] == "bess_20mw_4h" and "results_snapshot" in got
    c.delete(f"/api/assets/{aid}?t=tk")
    assert all(a["id"] != aid for a in c.get("/api/assets?t=tk").json()["assets"])


def test_list_includes_last_update(monkeypatch, tmp_path):
    """Every asset in the list carries a `last_update` ISO field. With no
    actuals it falls back to `created_at`."""
    c = _client(monkeypatch, tmp_path)
    aid = c.post(
        "/api/assets?t=tk",
        json={"model_id": "bess_20mw_4h", "name": "Sin actuals", "overrides": {}},
    ).json()["id"]
    row = next(a for a in c.get("/api/assets?t=tk").json()["assets"] if a["id"] == aid)
    assert "last_update" in row
    # No actuals yet -> last_update mirrors created_at.
    assert row["last_update"] == row["created_at"]
    # Single-asset GET exposes it too.
    assert c.get(f"/api/assets/{aid}?t=tk").json()["last_update"] == row["created_at"]


def test_last_update_reflects_latest_actual(monkeypatch, tmp_path):
    """An operational asset with actuals reports the latest actual's
    `entered_at` (newer than `created_at`) as `last_update`."""
    c = _client(monkeypatch, tmp_path)
    aid = c.post(
        "/api/assets?t=tk",
        json={"model_id": "bess_20mw_4h", "name": "Con actuals", "overrides": {}},
    ).json()["id"]
    c.patch(
        f"/api/assets/{aid}/lifecycle?t=tk",
        json={"lifecycle": "operational", "tracking_frequency": "monthly"},
    )
    c.post(
        f"/api/assets/{aid}/actuals?t=tk",
        json={
            "actuals": [
                {
                    "period_start": "2026-01-01",
                    "line_path": "income_statement.rows.revenue",
                    "value": 10.0,
                },
                {
                    "period_start": "2026-02-01",
                    "line_path": "income_statement.rows.revenue",
                    "value": 12.0,
                },
            ]
        },
    )
    # entered_at is stamped server-side at ingest, strictly after created_at.
    actuals = c.get(f"/api/assets/{aid}/actuals?t=tk").json()["actuals"]
    latest = max(a["entered_at"] for a in actuals)
    row = next(a for a in c.get("/api/assets?t=tk").json()["assets"] if a["id"] == aid)
    assert row["last_update"] == latest
    assert row["last_update"] > row["created_at"]
