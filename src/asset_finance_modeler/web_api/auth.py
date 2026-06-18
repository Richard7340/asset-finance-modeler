from __future__ import annotations

import os
from dataclasses import dataclass

from fastapi import Header, HTTPException, Request

# Explicit, documented fallback for tenant scoping. Used when no tenant headers
# are present — i.e. the engine is driven directly (its own SPA, MCP/stdio, local
# dev, the test client) rather than proxied by the webOS. Every direct flow lands
# in this single shared tenant, so those paths keep working exactly as before.
DEFAULT_TENANT = "default"


def require_token(request: Request) -> None:
    expected = os.getenv("SIM_TOKEN")
    if not expected:
        return  # no token configured -> open (dev/local)
    supplied = request.query_params.get("t") or request.headers.get("x-sim-token")
    if supplied != expected:
        raise HTTPException(status_code=401, detail="invalid or missing token")


@dataclass(frozen=True)
class TenantContext:
    """Resolved per-request tenant. ``workspace_id`` is the hard isolation
    boundary (= webOS companyId); ``user_id`` is the acting account inside it."""

    workspace_id: str
    user_id: str


def tenant_ctx(
    x_finance_workspace_id: str | None = Header(None),
    x_finance_user_id: str | None = Header(None),
    x_tenant_id: str | None = Header(None),
) -> TenantContext:
    """FastAPI dependency that extracts the tenant from the headers the webOS
    proxy sends on every request:

      * ``x-finance-workspace-id`` -> companyId  (isolation boundary)
      * ``x-finance-user-id``      -> userAccountId
      * ``x-tenant-id``            -> legacy/alias, used as a fallback for both

    When a header is absent (direct engine use: own SPA, MCP/stdio, dev, tests)
    it falls back to ``DEFAULT_TENANT`` so those flows are never broken and all
    land in one shared, well-known tenant. Blank/whitespace values are treated
    as absent.
    """

    def _clean(v: str | None) -> str | None:
        return v.strip() if v and v.strip() else None

    workspace = _clean(x_finance_workspace_id) or _clean(x_tenant_id) or DEFAULT_TENANT
    user = _clean(x_finance_user_id) or _clean(x_tenant_id) or DEFAULT_TENANT
    return TenantContext(workspace_id=workspace, user_id=user)
