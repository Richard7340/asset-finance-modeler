from __future__ import annotations

import io
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from asset_finance_modeler.deals.svj import (
    SvjInputError,
    build_svj_xlsx,
    run_svj,
    svj_input_spec,
)
from asset_finance_modeler.web_api.auth import require_token

router = APIRouter(prefix="/api/svj", dependencies=[Depends(require_token)])


class RunBody(BaseModel):
    overrides: dict[str, Any] = {}


@router.get("/model")
def model() -> dict[str, Any]:
    return {"inputs": svj_input_spec(), "name": "SVJ 1&2 — FV + BESS (Cordoba)"}


@router.post("/run")
def run(body: RunBody) -> dict[str, Any]:
    try:
        return run_svj(body.overrides)
    except SvjInputError as exc:  # A1: bad override -> 400, not 500
        raise HTTPException(status_code=400, detail=exc.message) from exc


@router.post("/export")
def export(body: RunBody) -> StreamingResponse:
    try:
        data = build_svj_xlsx(body.overrides)
    except SvjInputError as exc:  # A1: bad override -> 400, not 500
        raise HTTPException(status_code=400, detail=exc.message) from exc
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=SVJ_simulacion.xlsx"},
    )
