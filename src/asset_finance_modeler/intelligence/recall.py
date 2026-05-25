from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import faiss  # type: ignore[import-untyped]
import numpy as np

from asset_finance_modeler.intelligence.embeddings import LocalEmbeddingProvider

# Mapping from known base_model codes to human-readable expansions.
# This enriches the indexed text so that natural-language queries (including
# non-English ones) can match terse asset-type codes.
_ASSET_TYPE_EXPANSIONS: dict[str, str] = {
    "bess": "battery energy storage system almacenamiento de energía batería",
    "solar_pv": "solar photovoltaic energy solar fotovoltaica energía solar",
    "wind": "wind energy eólica energía eólica aerogenerador",
    "wind_onshore": "onshore wind energy eólica terrestre aerogenerador",
    "wind_offshore": "offshore wind energy eólica marina aerogenerador marino",
    "datacenter": "data center centro de datos computing computing infrastructure",
    "saas": "software as a service SaaS ingresos recurrentes subscription",
    "real_estate": "real estate inmobiliaria propiedad bienes raíces",
    "hydro": "hydroelectric power hydropower energía hidroeléctrica",
    "biomass": "biomass energy biomasa energía biomasa",
    "geothermal": "geothermal energy geotérmica energía geotérmica",
}


@dataclass
class RecallResult:
    scenario_id: str
    name: str
    description: str
    asset_type: str
    score: float
    summary: dict[str, Any]


class ScenarioRecall:
    """FAISS-based semantic search over indexed scenario metadata.

    Allows users to retrieve previously analysed scenarios with natural-language
    queries such as "remember the solar project in Spain".
    """

    def __init__(self) -> None:
        self._provider = LocalEmbeddingProvider()
        self._index: faiss.IndexFlatIP | None = None
        self._entries: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def index_scenario(
        self,
        scenario_id: str,
        name: str,
        description: str,
        base_model: str,
        tags: list[str],
        summary: dict[str, Any],
    ) -> None:
        """Embed and index a scenario so it can be retrieved later.

        Args:
            scenario_id: Unique identifier for the scenario.
            name: Human-readable name.
            description: Free-text description.
            base_model: Asset model type (e.g. ``solar_pv``, ``bess``).
            tags: Arbitrary keyword tags.
            summary: Dict of KPI names → values (e.g. ``{"irr_project": 0.085}``).
        """
        # Expand the base_model code with human-readable synonyms so multilingual
        # queries (e.g. "batería almacenamiento") match terse codes like "bess".
        model_expansion = _ASSET_TYPE_EXPANSIONS.get(base_model, "")
        text = f"{name} {description} {base_model} {model_expansion} {' '.join(tags)} "
        for k, v in summary.items():
            text += f"{k}={v} "

        vec = self._provider.embed(text).astype(np.float32).reshape(1, -1)

        if self._index is None:
            self._index = faiss.IndexFlatIP(vec.shape[1])

        self._index.add(vec)
        self._entries.append({
            "scenario_id": scenario_id,
            "name": name,
            "description": description,
            "asset_type": base_model,
            "tags": tags,
            "summary": summary,
        })

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        top_k: int = 5,
        tenant_id: str | None = None,  # reserved for future multi-tenant filtering
    ) -> list[RecallResult]:
        """Return the *top_k* scenarios most semantically similar to *query*.

        Args:
            query: Natural-language description of the desired scenario.
            top_k: Maximum number of results to return.
            tenant_id: Reserved — not used in the current implementation.

        Returns:
            Ordered list of :class:`RecallResult`, best match first.
        """
        if self._index is None or self._index.ntotal == 0:
            return []

        qvec = self._provider.embed(query).astype(np.float32).reshape(1, -1)
        k = min(top_k, self._index.ntotal)
        scores, idxs = self._index.search(qvec, k)

        results: list[RecallResult] = []
        for score, idx in zip(scores[0].tolist(), idxs[0].tolist()):
            if idx < 0 or idx >= len(self._entries):
                continue
            e = self._entries[idx]
            results.append(
                RecallResult(
                    scenario_id=e["scenario_id"],
                    name=e["name"],
                    description=e["description"],
                    asset_type=e["asset_type"],
                    score=float(score),
                    summary=e["summary"],
                )
            )
        return results

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def count(self) -> int:
        """Number of scenarios currently indexed."""
        return len(self._entries)
