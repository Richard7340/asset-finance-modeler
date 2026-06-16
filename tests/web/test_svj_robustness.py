"""PASADA 3 / A1: the SVJ override path must validate like the generic path.

A bad-type (``wacc:"abc"``) or pathological (``wacc:-1``) override is a client
error (HTTP 400 with a clear message), NOT an unhandled 500, on all three SVJ
entry points: ``/api/svj/run``, ``/api/svj/export`` and
``/api/models/svj_hybrid/run``. A valid override still returns 200.
"""
from __future__ import annotations

from fastapi.testclient import TestClient


def _client(monkeypatch):
    monkeypatch.setenv("SIM_TOKEN", "tk")
    monkeypatch.setenv("SIM_ONLY", "1")
    from asset_finance_modeler.mcp_server.http_server import app  # noqa: PLC0415

    # raise_server_exceptions=False so an unhandled 500 surfaces as a real 500
    # response (not a re-raised exception) — that is exactly what we must avoid.
    return TestClient(app, raise_server_exceptions=False)


_BAD = [
    {"wacc": "abc"},  # bad type
    {"wacc": -1},     # pathological (1+r = 0 -> ZeroDivisionError discounting)
]


def test_svj_run_bad_override_is_400(monkeypatch):
    c = _client(monkeypatch)
    for ov in _BAD:
        r = c.post("/api/svj/run?t=tk", json={"overrides": ov})
        assert r.status_code == 400, (ov, r.status_code, r.text)


def test_svj_export_bad_override_is_400(monkeypatch):
    c = _client(monkeypatch)
    for ov in _BAD:
        r = c.post("/api/svj/export?t=tk", json={"overrides": ov})
        assert r.status_code == 400, (ov, r.status_code, r.text)


def test_svj_hybrid_run_bad_override_is_400(monkeypatch):
    c = _client(monkeypatch)
    for ov in _BAD:
        r = c.post("/api/models/svj_hybrid/run?t=tk", json={"overrides": ov})
        assert r.status_code == 400, (ov, r.status_code, r.text)


def test_svj_bad_subordinated_override_is_400(monkeypatch):
    """A bad-type subordinated/senior override is also a 400 (raw float()/int()
    casts in ``_build_deal`` must not surface as a 500)."""
    c = _client(monkeypatch)
    for ov in ({"subordinated.interest_rate": "x"}, {"senior.tenor_years": "ten"}):
        r = c.post("/api/svj/run?t=tk", json={"overrides": ov})
        assert r.status_code == 400, (ov, r.status_code, r.text)


def test_svj_valid_override_still_200(monkeypatch):
    c = _client(monkeypatch)
    r = c.post("/api/svj/run?t=tk", json={"overrides": {"wacc": 0.06}})
    assert r.status_code == 200, r.text
    assert "kpis" in r.json()
    # generic entry point too
    r2 = c.post("/api/models/svj_hybrid/run?t=tk", json={"overrides": {"wacc": 0.06}})
    assert r2.status_code == 200, r2.text
    # export with a valid override returns the workbook
    r3 = c.post("/api/svj/export?t=tk", json={"overrides": {"spread_capture": 0.9}})
    assert r3.status_code == 200, r3.text
