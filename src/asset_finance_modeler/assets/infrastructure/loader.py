"""Loader utilities for InfrastructureModelConfig.

Two entry points:

* ``load_preset(name)`` — loads a bundled YAML preset by name (no extension).
* ``load_yaml(path)``   — loads any YAML file from an arbitrary filesystem path.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

import yaml

from asset_finance_modeler.assets.infrastructure.schema import InfrastructureModelConfig

__all__ = ["load_preset", "load_yaml"]


def load_preset(name: str) -> InfrastructureModelConfig:
    """Load a bundled YAML preset and return a validated config.

    Parameters
    ----------
    name:
        Preset name without the ``.yaml`` extension, e.g. ``"solar_pv_50mw_spain"``.

    Returns
    -------
    InfrastructureModelConfig
    """
    preset_path = (
        files("asset_finance_modeler.assets.infrastructure.presets") / f"{name}.yaml"
    )
    with preset_path.open() as f:
        data = yaml.safe_load(f)
    return InfrastructureModelConfig.model_validate(data)


def load_yaml(path: Path | str) -> InfrastructureModelConfig:
    """Load an arbitrary YAML file and return a validated config.

    Parameters
    ----------
    path:
        Filesystem path to a YAML file.

    Returns
    -------
    InfrastructureModelConfig
    """
    with open(path) as f:
        data = yaml.safe_load(f)
    return InfrastructureModelConfig.model_validate(data)
