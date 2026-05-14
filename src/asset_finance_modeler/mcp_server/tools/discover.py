from typing import Any


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
