from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# Thresholds used in insight extraction
_DSCR_COVENANT: float = 1.30
_IRR_INFRA_THRESHOLD: float = 0.08
_IRR_EQUITY_TARGET: float = 0.12
_PAYBACK_MAX_YEARS: float = 100.0
_PRESET_DELTA_MIN: float = 0.001


@dataclass
class Insight:
    scenario_id: str
    asset_type: str
    metric: str
    actual_value: float
    reference_value: float | None
    reference_source: str
    observation: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class MetaLearner:
    """Extracts insights from completed scenario runs and accumulates them for KB promotion."""

    def __init__(self) -> None:
        self._insights: list[Insight] = []

    def extract_insights(
        self,
        scenario_id: str,
        asset_type: str,
        results: dict[str, Any],
        preset_defaults: dict[str, Any] | None = None,
    ) -> list[Insight]:
        """Analyze scenario results and return a list of new Insight objects.

        Insights cover DSCR, project IRR, equity IRR, LCOE, payback, and
        optional deviations from preset default values.
        """
        insights: list[Insight] = []
        summary: dict[str, Any] = dict(results.get("summary", {}))
        kpis = results.get("project_kpis", {})
        if isinstance(kpis, dict):
            summary = {**summary, **kpis}

        # --- DSCR vs standard covenant ------------------------------------------
        dscr_min = summary.get("dscr_min")
        if dscr_min is not None and isinstance(dscr_min, (int, float)) and dscr_min > 0:
            insights.append(
                Insight(
                    scenario_id=scenario_id,
                    asset_type=asset_type,
                    metric="dscr_min",
                    actual_value=float(dscr_min),
                    reference_value=_DSCR_COVENANT,
                    reference_source="standard_covenant",
                    observation=f"Actual min DSCR {dscr_min:.2f} vs typical covenant {_DSCR_COVENANT:.2f}x",
                )
            )

        # --- Project IRR vs infrastructure threshold ----------------------------
        irr_project = summary.get("irr_project")
        if irr_project is not None and isinstance(irr_project, (int, float)):
            label = "above" if irr_project > _IRR_INFRA_THRESHOLD else "below"
            insights.append(
                Insight(
                    scenario_id=scenario_id,
                    asset_type=asset_type,
                    metric="irr_project",
                    actual_value=float(irr_project),
                    reference_value=_IRR_INFRA_THRESHOLD,
                    reference_source="market_threshold",
                    observation=(
                        f"Project IRR {irr_project:.1%} is {label} the"
                        f" {_IRR_INFRA_THRESHOLD:.0%} infrastructure threshold"
                    ),
                )
            )

        # --- Equity IRR vs typical target ---------------------------------------
        irr_equity = summary.get("irr_equity")
        if irr_equity is not None and isinstance(irr_equity, (int, float)):
            label = "exceeds" if irr_equity > _IRR_EQUITY_TARGET else "below"
            insights.append(
                Insight(
                    scenario_id=scenario_id,
                    asset_type=asset_type,
                    metric="irr_equity",
                    actual_value=float(irr_equity),
                    reference_value=_IRR_EQUITY_TARGET,
                    reference_source="equity_target",
                    observation=f"Equity IRR {irr_equity:.1%} {label} typical target of {_IRR_EQUITY_TARGET:.0%}",
                )
            )

        # --- LCOE (informational) -----------------------------------------------
        lcoe = summary.get("lcoe")
        if lcoe is not None and isinstance(lcoe, (int, float)) and lcoe > 0:
            insights.append(
                Insight(
                    scenario_id=scenario_id,
                    asset_type=asset_type,
                    metric="lcoe",
                    actual_value=float(lcoe),
                    reference_value=None,
                    reference_source="computed",
                    observation=f"LCOE of {lcoe:.1f} €/MWh for {asset_type}",
                )
            )

        # --- Discounted payback (informational) ---------------------------------
        payback = summary.get("payback_years")
        if (
            payback is not None
            and isinstance(payback, (int, float))
            and 0 < payback < _PAYBACK_MAX_YEARS
        ):
            insights.append(
                Insight(
                    scenario_id=scenario_id,
                    asset_type=asset_type,
                    metric="payback_years",
                    actual_value=float(payback),
                    reference_value=None,
                    reference_source="computed",
                    observation=f"Discounted payback of {payback:.1f} years for {asset_type}",
                )
            )

        # --- Deviation from preset defaults -------------------------------------
        if preset_defaults:
            for key in ("irr_project", "dscr_min", "lcoe"):
                preset_val = preset_defaults.get(key)
                actual_val = summary.get(key)
                if (
                    preset_val is not None
                    and actual_val is not None
                    and isinstance(preset_val, (int, float))
                    and isinstance(actual_val, (int, float))
                ):
                    delta = float(actual_val) - float(preset_val)
                    if abs(delta) > _PRESET_DELTA_MIN:
                        insights.append(
                            Insight(
                                scenario_id=scenario_id,
                                asset_type=asset_type,
                                metric=f"{key}_vs_preset",
                                actual_value=float(actual_val),
                                reference_value=float(preset_val),
                                reference_source="preset_default",
                                observation=(
                                    f"{key} actual={actual_val:.4f} vs preset={preset_val:.4f}"
                                    f" (delta={delta:+.4f})"
                                ),
                            )
                        )

        self._insights.extend(insights)
        return insights

    # --- Accessors --------------------------------------------------------------

    @property
    def all_insights(self) -> list[Insight]:
        """Return a copy of all accumulated insights."""
        return list(self._insights)

    def insights_for_asset(self, asset_type: str) -> list[Insight]:
        """Return insights filtered by asset type."""
        return [i for i in self._insights if i.asset_type == asset_type]

    def clear(self) -> None:
        """Remove all accumulated insights."""
        self._insights.clear()
