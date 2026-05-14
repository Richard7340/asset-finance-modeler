from __future__ import annotations

from abc import ABC, abstractmethod
from functools import lru_cache

import numpy as np


class EmbeddingProvider(ABC):
    @property
    @abstractmethod
    def dimension(self) -> int: ...

    @abstractmethod
    def embed(self, text: str) -> np.ndarray: ...

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> np.ndarray: ...


DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


@lru_cache(maxsize=1)
def _load_model(model_name: str):  # type: ignore[no-untyped-def]
    from sentence_transformers import SentenceTransformer  # noqa: PLC0415
    return SentenceTransformer(model_name)


class LocalEmbeddingProvider(EmbeddingProvider):
    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self._model_name = model_name
        self._dim: int | None = None

    @property
    def dimension(self) -> int:
        if self._dim is None:
            self._dim = _load_model(self._model_name).get_sentence_embedding_dimension()
        return int(self._dim)

    def embed(self, text: str) -> np.ndarray:
        model = _load_model(self._model_name)
        arr = model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
        return np.asarray(arr, dtype=np.float32)

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        model = _load_model(self._model_name)
        arr = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
        return np.asarray(arr, dtype=np.float32)
