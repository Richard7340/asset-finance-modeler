from typing import Any

from asset_finance_modeler.assets.infrastructure.loader import load_preset as load_infra_preset
from asset_finance_modeler.assets.infrastructure.schema import InfrastructureModelConfig
from asset_finance_modeler.assets.saas.loader import load_preset
from asset_finance_modeler.assets.saas.schema import SaasModelConfig
from asset_finance_modeler.core.scenario import Scenario, new_scenario_id

_PRESET_INDEX = {
    "saas": ["gestnova"],
    "infrastructure": ["solar_pv_50mw_spain", "bess_20mw_4h", "wind_onshore_30mw_spain", "datacenter_10mw_tier3"],
}

_INFRA_PRESETS = {"solar_pv_50mw_spain", "bess_20mw_4h", "wind_onshore_30mw_spain", "datacenter_10mw_tier3"}


def handle_list_models(_args: dict[str, Any]) -> dict[str, Any]:
    return {
        "models": [
            {
                "name": "gestnova",
                "asset_type": "saas",
                "description": (
                    "Gestnova SaaS baseline — voice/WhatsApp/email agent platform. "
                    "Pricing per agent-month, cohort retention, multi-LLM COGS, "
                    "team ramp, debt + funding modeling, DCF valuation."
                ),
            },
            {
                "name": "solar_pv_50mw_spain",
                "asset_type": "infrastructure",
                "description": (
                    "50 MWp solar PV plant in Spain — PPA + merchant revenue, "
                    "project finance."
                ),
            },
            {
                "name": "bess_20mw_4h",
                "asset_type": "infrastructure",
                "description": (
                    "20 MW / 4h BESS — arbitrage + capacity market, "
                    "cycle-based degradation."
                ),
            },
            {
                "name": "wind_onshore_30mw_spain",
                "asset_type": "infrastructure",
                "description": "30 MW onshore wind farm in Spain — PPA + merchant + GOs, project finance.",
            },
            {
                "name": "datacenter_10mw_tier3",
                "asset_type": "infrastructure",
                "description": "10 MW IT Tier 3 data center — SLA colocation, N+1 redundancy.",
            },
        ],
    }


def handle_describe_schema(args: dict[str, Any]) -> dict[str, Any]:
    model = args.get("model")
    if model in _INFRA_PRESETS or model == "infrastructure":
        return {"schema": InfrastructureModelConfig.model_json_schema()}
    if model not in {"gestnova", "saas"}:
        raise ValueError(
            f"unknown model: {model!r}. Use 'gestnova', 'saas', "
            "'solar_pv_50mw_spain', 'bess_20mw_4h', 'wind_onshore_30mw_spain', "
            "'datacenter_10mw_tier3', or 'infrastructure'."
        )
    return {"schema": SaasModelConfig.model_json_schema()}


def handle_list_presets(args: dict[str, Any]) -> dict[str, Any]:
    model = args.get("model", "saas")
    keys = _PRESET_INDEX.get(model, [])
    return {
        "presets": [
            {"key": k, "name": k.capitalize(), "asset_type": model}
            for k in keys
        ],
    }


def make_handle_load_baseline(store: Any) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        preset = args.get("preset", "gestnova")
        # Verify preset loads (routing by type)
        if preset in _INFRA_PRESETS:
            load_infra_preset(preset)
        else:
            load_preset(preset)
        scenario = Scenario(
            id=new_scenario_id(),
            name=f"{preset}-baseline",
            description=f"Canonical baseline for {preset}",
            base_model=preset,
            overrides={},
            is_canonical=True,
            tags=["baseline"],
        )
        store.save(scenario)
        return {"scenario_id": scenario.id, "name": scenario.name}

    return _handle


# Stub for direct import in tests (closure-bound via make_handle_load_baseline)
handle_load_baseline = make_handle_load_baseline
