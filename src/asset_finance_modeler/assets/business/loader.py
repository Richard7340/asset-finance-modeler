"""Loader utilities for BusinessModelConfig.

Mirrors the infrastructure loader:

* ``load_business_preset(name)`` — loads a bundled YAML preset by name.
* ``business_preset_ids()``      — lists bundled preset names (stems).
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

import yaml

from asset_finance_modeler.assets.business.schema import BusinessModelConfig

__all__ = ["business_preset_ids", "load_business_preset"]


def load_business_preset(name: str) -> BusinessModelConfig:
    """Load a bundled YAML preset and return a validated business config.

    Parameters
    ----------
    name:
        Preset name without the ``.yaml`` extension, e.g. ``"business_generic"``.

    Returns
    -------
    BusinessModelConfig
    """
    preset_path = (
        files("asset_finance_modeler.assets.business.presets") / f"{name}.yaml"
    )
    with preset_path.open() as f:
        data = yaml.safe_load(f)
    return BusinessModelConfig.model_validate(data)


def business_preset_ids() -> list[str]:
    """Return the sorted stems of the bundled business preset YAMLs."""
    presets_dir = Path(str(files("asset_finance_modeler.assets.business.presets")))
    return sorted(q.stem for q in presets_dir.glob("*.yaml"))
