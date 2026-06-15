"""Curves catalog: /api/curves (read-only price-curve transparency).

Exposes every consultant price curve in the library so an investor/advisory
doing technical due diligence can see exactly which curves the 30-year
projections use, with their sources. The Curve object only surfaces
name+source+values, so the per-curve metadata (parameter/asset_type/bankable)
is read straight from the YAML — mirroring how curve_library.load_curve finds
the directory.
"""
from __future__ import annotations

from typing import Any

import yaml
from fastapi import APIRouter, Depends, HTTPException

from asset_finance_modeler.core.curve_library import _CURVES_DIR, list_curves, load_curve
from asset_finance_modeler.web_api.auth import require_token

router = APIRouter(prefix="/api/curves", dependencies=[Depends(require_token)])


def _curve_dict(name: str) -> dict[str, Any]:
    """Combine the YAML metadata with the Curve's 30-year projection values."""
    spec: dict[str, Any] = {}
    path = _CURVES_DIR / f"{name}.yaml"
    if path.is_file():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            spec = loaded
    curve = load_curve(name)
    return {
        "name": name,
        "source": curve.source or str(spec.get("source", "")),
        "parameter": spec.get("parameter"),
        "asset_type": spec.get("asset_type"),
        "bankable": spec.get("bankable"),
        "values": curve.to_list(30),
    }


@router.get("")
def list_curves_catalog(parameter: str | None = None) -> dict[str, list[dict[str, Any]]]:
    curves = [_curve_dict(name) for name in list_curves()]
    if parameter is not None:
        curves = [c for c in curves if c["parameter"] == parameter]
    return {"curves": curves}


@router.get("/{name}")
def get_curve(name: str) -> dict[str, Any]:
    if name not in list_curves():
        raise HTTPException(status_code=404, detail=f"unknown curve: {name}")
    return _curve_dict(name)
