from __future__ import annotations

import os

from fastapi import HTTPException, Request


def require_token(request: Request) -> None:
    expected = os.getenv("SIM_TOKEN")
    if not expected:
        return  # no token configured -> open (dev/local)
    supplied = request.query_params.get("t") or request.headers.get("x-sim-token")
    if supplied != expected:
        raise HTTPException(status_code=401, detail="invalid or missing token")
