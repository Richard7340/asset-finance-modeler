import copy
import secrets
from datetime import UTC, datetime
from typing import Any

from jsonpath_ng.ext import parse as jsonpath_parse  # type: ignore[import-untyped]
from pydantic import BaseModel, Field

from asset_finance_modeler.assets.infrastructure.loader import load_preset as load_infra_preset
from asset_finance_modeler.assets.infrastructure.model import InfrastructureModel
from asset_finance_modeler.assets.infrastructure.schema import InfrastructureModelConfig
from asset_finance_modeler.assets.saas.loader import load_preset
from asset_finance_modeler.assets.saas.model import ModelResults, SaasModel
from asset_finance_modeler.assets.saas.schema import SaasModelConfig
from asset_finance_modeler.core.protocols import FinancialOutput

_SAAS_PRESETS = {"gestnova"}
_INFRA_PRESETS = {"solar_pv_50mw_spain", "bess_20mw_4h", "wind_onshore_30mw_spain", "datacenter_10mw_tier3"}


def new_scenario_id() -> str:
    """Generate a unique scenario id like 'scn-a3f2c1b9'."""
    return f"scn-{secrets.token_hex(4)}"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Scenario(BaseModel):
    id: str
    name: str
    description: str = ""
    base_model: str = Field(description="Preset key, e.g. 'gestnova'")
    parent_scenario_id: str | None = None
    overrides: dict[str, Any] = Field(default_factory=dict)
    inputs_snapshot: dict[str, Any] = Field(default_factory=dict)
    results_snapshot: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)
    tags: list[str] = Field(default_factory=list)
    notes: str = ""
    is_canonical: bool = False
    is_deleted: bool = False
    tenant_id: str = "default"


def _set_by_path(d: dict[str, Any], path: str, value: Any) -> None:
    """Set d[path] = value where path uses dotted+[index] syntax.
    Raises KeyError if any intermediate key does not exist."""
    expr = jsonpath_parse(path)
    matches = expr.find(d)
    if not matches:
        raise KeyError(f"Override path not found: {path!r}")
    expr.update(d, value)


def apply_overrides(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Return a deep-copied base with overrides applied. base is not mutated."""
    result = copy.deepcopy(base)
    for path, value in overrides.items():
        _set_by_path(result, path, value)
    return result


def run_scenario_saas(scenario: Scenario) -> ModelResults:
    """Resolve a Scenario for the SaaS asset type: load preset, apply overrides, run."""
    base_cfg = load_preset(scenario.base_model)
    base_dict = base_cfg.model_dump(mode="json")
    resolved_dict = apply_overrides(base_dict, scenario.overrides)
    resolved_cfg = SaasModelConfig.model_validate(resolved_dict)
    return SaasModel(resolved_cfg).run()


def run_scenario(scenario: Scenario) -> "ModelResults | FinancialOutput":
    """Run any scenario — dispatches by base_model to the right engine.

    Known SaaS presets (e.g. 'gestnova') are routed to SaasModel.
    Known infrastructure presets (e.g. 'solar_pv_50mw_spain', 'bess_20mw_4h')
    are routed to InfrastructureModel.
    Unknown presets fall back to SaaS first, then infrastructure.
    """
    if scenario.base_model in _SAAS_PRESETS:
        return run_scenario_saas(scenario)

    if scenario.base_model in _INFRA_PRESETS:
        base_cfg = load_infra_preset(scenario.base_model)
        base_dict = base_cfg.model_dump(mode="json")
        resolved_dict = apply_overrides(base_dict, scenario.overrides)
        resolved_cfg = InfrastructureModelConfig.model_validate(resolved_dict)
        return InfrastructureModel(resolved_cfg).run()

    # Fallback: try saas first, then infra
    try:
        return run_scenario_saas(scenario)
    except Exception:
        base_cfg = load_infra_preset(scenario.base_model)
        base_dict = base_cfg.model_dump(mode="json")
        resolved_dict = apply_overrides(base_dict, scenario.overrides)
        resolved_cfg = InfrastructureModelConfig.model_validate(resolved_dict)
        return InfrastructureModel(resolved_cfg).run()
