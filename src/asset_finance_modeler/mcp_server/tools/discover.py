from typing import Any

from asset_finance_modeler.assets.saas.loader import load_preset
from asset_finance_modeler.assets.saas.schema import SaasModelConfig
from asset_finance_modeler.core.scenario import Scenario, new_scenario_id

_PRESET_INDEX = {
    "saas": ["gestnova"],
}


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
        ],
    }


def handle_describe_schema(args: dict[str, Any]) -> dict[str, Any]:
    model = args.get("model")
    if model not in {"gestnova", "saas"}:
        raise ValueError(f"unknown model: {model!r}. Use 'gestnova' or 'saas'.")
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
        # Verify preset loads
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
