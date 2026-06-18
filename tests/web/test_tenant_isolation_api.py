"""REST-layer tenant isolation: the engine reads the webOS proxy headers
(``x-finance-workspace-id`` / ``x-finance-user-id`` / ``x-tenant-id``) and scopes
every assets/portfolio/actuals/live read+write to that workspace, while the
``default`` fallback keeps direct (header-less) use working.
"""
from fastapi.testclient import TestClient


def _client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("SIM_TOKEN", "tk")
    monkeypatch.setenv("SIM_ONLY", "1")
    monkeypatch.setenv("ASSET_FINANCE_DB_PATH", str(tmp_path))
    from asset_finance_modeler.mcp_server.http_server import app

    return TestClient(app)


def _h(workspace: str, user: str = "u") -> dict[str, str]:
    return {"x-finance-workspace-id": workspace, "x-finance-user-id": user}


def _save(c: TestClient, name: str, headers: dict[str, str]) -> str:
    r = c.post(
        "/api/assets?t=tk",
        json={"model_id": "bess_20mw_4h", "name": name, "overrides": {}},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_two_tenants_do_not_see_each_others_assets(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    a_id = _save(c, "Asset A", _h("company-A"))
    b_id = _save(c, "Asset B", _h("company-B"))

    a_list = c.get("/api/assets?t=tk", headers=_h("company-A")).json()["assets"]
    b_list = c.get("/api/assets?t=tk", headers=_h("company-B")).json()["assets"]

    a_ids = {a["id"] for a in a_list}
    b_ids = {a["id"] for a in b_list}
    assert a_id in a_ids and b_id not in a_ids
    assert b_id in b_ids and a_id not in b_ids


def test_tenant_cannot_read_other_tenants_asset_by_id(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    a_id = _save(c, "Asset A", _h("company-A"))
    # B guesses A's id -> 404, not the asset.
    r = c.get(f"/api/assets/{a_id}?t=tk", headers=_h("company-B"))
    assert r.status_code == 404
    # A can read its own.
    assert c.get(f"/api/assets/{a_id}?t=tk", headers=_h("company-A")).status_code == 200


def test_tenant_cannot_delete_other_tenants_asset(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    a_id = _save(c, "Asset A", _h("company-A"))
    # B tries to delete A's asset -> no-op (silently scoped away).
    c.delete(f"/api/assets/{a_id}?t=tk", headers=_h("company-B"))
    # A still sees it.
    a_list = c.get("/api/assets?t=tk", headers=_h("company-A")).json()["assets"]
    assert any(a["id"] == a_id for a in a_list)
    # A can delete its own.
    c.delete(f"/api/assets/{a_id}?t=tk", headers=_h("company-A"))
    a_list2 = c.get("/api/assets?t=tk", headers=_h("company-A")).json()["assets"]
    assert all(a["id"] != a_id for a in a_list2)


def test_portfolio_is_scoped_per_tenant(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    _save(c, "Asset A", _h("company-A"))
    _save(c, "Asset B1", _h("company-B"))
    _save(c, "Asset B2", _h("company-B"))

    pa = c.get("/api/portfolio?t=tk", headers=_h("company-A")).json()
    pb = c.get("/api/portfolio?t=tk", headers=_h("company-B")).json()
    assert pa["totals"]["count"] == 1
    assert pb["totals"]["count"] == 2


def test_actuals_isolated_per_tenant(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    a_id = _save(c, "Asset A", _h("company-A"))
    # B cannot POST actuals against A's asset (parent lookup 404s).
    r = c.post(
        f"/api/assets/{a_id}/actuals?t=tk",
        json={
            "actuals": [
                {
                    "period_start": "2026-01-01",
                    "line_path": "income_statement.rows.revenue",
                    "value": 1.0,
                }
            ]
        },
        headers=_h("company-B"),
    )
    assert r.status_code == 404
    # B cannot list A's actuals either.
    assert c.get(f"/api/assets/{a_id}/actuals?t=tk", headers=_h("company-B")).status_code == 404
    # A can.
    assert c.get(f"/api/assets/{a_id}/actuals?t=tk", headers=_h("company-A")).status_code == 200


def test_default_fallback_without_headers(monkeypatch, tmp_path):
    """No tenant headers -> the 'default' tenant. Two header-less requests share
    one workspace, exactly preserving the legacy direct-use behaviour."""
    c = _client(monkeypatch, tmp_path)
    a_id = _save(c, "Direct asset", headers={})
    # A second header-less reader sees it (same default workspace).
    lst = c.get("/api/assets?t=tk").json()["assets"]
    assert any(a["id"] == a_id for a in lst)
    # Direct GET by id works header-less.
    assert c.get(f"/api/assets/{a_id}?t=tk").status_code == 200


def test_x_tenant_id_aliases_workspace(monkeypatch, tmp_path):
    """When only x-tenant-id is sent it is used as the workspace boundary."""
    c = _client(monkeypatch, tmp_path)
    a_id = _save(c, "Aliased", {"x-tenant-id": "company-X"})
    # Same x-tenant-id sees it.
    lst = c.get("/api/assets?t=tk", headers={"x-tenant-id": "company-X"}).json()["assets"]
    assert any(a["id"] == a_id for a in lst)
    # A different x-tenant-id does not.
    other = c.get("/api/assets?t=tk", headers={"x-tenant-id": "company-Y"}).json()["assets"]
    assert all(a["id"] != a_id for a in other)
