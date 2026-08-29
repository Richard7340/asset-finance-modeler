from __future__ import annotations

import io
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from asset_finance_modeler.deals.hybrid_consolidated import (
    HybridConsolidatedInputError,
    build_hybrid_consolidated_xlsx,
    run_hybrid_consolidated,
    hybrid_consolidated_input_spec,
)
from asset_finance_modeler.web_api.auth import require_token

router = APIRouter(prefix="/api/hybrid_consolidated", dependencies=[Depends(require_token)])


class RunBody(BaseModel):
    overrides: dict[str, Any] = {}


@router.get("/model")
def model() -> dict[str, Any]:
    return {"inputs": hybrid_consolidated_input_spec(), "name": "hybrid consolidated 1&2 — FV + BESS (Reference)"}


@router.post("/run")
def run(body: RunBody) -> dict[str, Any]:
    try:
        return run_hybrid_consolidated(body.overrides)
    except HybridConsolidatedInputError as exc:  # A1: bad override -> 400, not 500
        raise HTTPException(status_code=400, detail=exc.message) from exc


@router.post("/export")
def export(body: RunBody) -> StreamingResponse:
    try:
        data = build_hybrid_consolidated_xlsx(body.overrides)
    except HybridConsolidatedInputError as exc:  # A1: bad override -> 400, not 500
        raise HTTPException(status_code=400, detail=exc.message) from exc
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=simulacion_hibrida.xlsx"},
    )
