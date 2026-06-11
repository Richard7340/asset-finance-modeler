from fastapi.testclient import TestClient


def _client(monkeypatch):
    monkeypatch.setenv("SIM_TOKEN", "secret123")
    monkeypatch.setenv("SIM_ONLY", "1")
    from asset_finance_modeler.mcp_server.http_server import app  # noqa: PLC0415
    return TestClient(app)


def test_run_requires_token(monkeypatch):
    c = _client(monkeypatch)
    assert c.post("/api/svj/run", json={"overrides": {}}).status_code == 401
    ok = c.post("/api/svj/run?t=secret123", json={"overrides": {}})
    assert ok.status_code == 200
    assert "kpis" in ok.json()


def test_run_token_via_header(monkeypatch):
    c = _client(monkeypatch)
    r = c.post("/api/svj/run", json={"overrides": {}}, headers={"x-sim-token": "secret123"})
    assert r.status_code == 200


def test_model_endpoint(monkeypatch):
    c = _client(monkeypatch)
    r = c.get("/api/svj/model?t=secret123")
    assert r.status_code == 200 and isinstance(r.json()["inputs"], list)


def test_export_returns_xlsx(monkeypatch):
    c = _client(monkeypatch)
    r = c.post("/api/svj/export?t=secret123", json={"overrides": {}})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/")
    assert len(r.content) > 1000


def test_health_still_works(monkeypatch):
    c = _client(monkeypatch)
    assert c.get("/health").status_code == 200
