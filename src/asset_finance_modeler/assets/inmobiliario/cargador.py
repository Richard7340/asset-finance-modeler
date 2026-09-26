"""Presets del modelo inmobiliario (inmueble_*)."""
from __future__ import annotations

from importlib.resources import files
from pathlib import Path

import yaml

from asset_finance_modeler.assets.inmobiliario.modelo import InmuebleConfig


def ids_inmobiliario() -> list[str]:
    d = Path(str(files("asset_finance_modeler.assets.inmobiliario.presets")))
    return sorted(q.stem for q in d.glob("*.yaml"))


def cargar_inmueble(nombre: str) -> InmuebleConfig:
    d = Path(str(files("asset_finance_modeler.assets.inmobiliario.presets")))
    return InmuebleConfig.model_validate(yaml.safe_load((d / f"{nombre}.yaml").read_text(encoding="utf-8")))
