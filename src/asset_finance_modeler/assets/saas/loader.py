from importlib.resources import files
from pathlib import Path

import yaml

from .schema import SaasModelConfig


def load_preset(name: str) -> SaasModelConfig:
    preset_path = files("asset_finance_modeler.assets.saas.presets") / f"{name}.yaml"
    with preset_path.open() as f:
        data = yaml.safe_load(f)
    return SaasModelConfig.model_validate(data)


def load_yaml(path: Path | str) -> SaasModelConfig:
    with open(path) as f:
        data = yaml.safe_load(f)
    return SaasModelConfig.model_validate(data)
