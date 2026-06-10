from __future__ import annotations

from pathlib import Path

import yaml

from asset_finance_modeler.core.curves import Curve
from asset_finance_modeler.core.drivers import CurvePhase

_CURVES_DIR = Path(__file__).resolve().parent.parent / "data" / "curves"


def list_curves() -> list[str]:
    if not _CURVES_DIR.is_dir():
        return []
    return sorted(p.stem for p in _CURVES_DIR.glob("*.yaml"))


def load_curve(name: str) -> Curve:
    path = _CURVES_DIR / f"{name}.yaml"
    if not path.is_file():
        raise KeyError(f"Curve '{name}' not found in {_CURVES_DIR}")
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    source = str(spec.get("source", ""))
    build = spec.get("build", "points")
    if build == "phases":
        phases = [CurvePhase(int(p["years"]), float(p["growth_pct"])) for p in spec["phases"]]
        return Curve.from_phases(float(spec["base"]), phases, int(spec["periods"]), name, source)
    if build == "growth":
        return Curve.from_growth(
            float(spec["base"]), float(spec["rate"]), int(spec["periods"]), name, source,
        )
    return Curve.from_points([float(v) for v in spec["points"]], name, source)
