import numpy as np
import pytest

from asset_finance_modeler.intelligence.embeddings import (
    EmbeddingProvider,
    LocalEmbeddingProvider,
)


@pytest.fixture(scope="module")
def provider() -> LocalEmbeddingProvider:
    return LocalEmbeddingProvider()


def test_provider_is_subclass_of_abstract():
    assert issubclass(LocalEmbeddingProvider, EmbeddingProvider)


def test_embed_single_returns_vector(provider):
    vec = provider.embed("test query")
    assert isinstance(vec, np.ndarray)
    assert vec.ndim == 1
    assert vec.shape[0] == provider.dimension


def test_embed_batch_returns_matrix(provider):
    matrix = provider.embed_batch(["hello", "world", "test"])
    assert matrix.shape == (3, provider.dimension)


def test_similar_texts_have_higher_cosine_similarity(provider):
    revenue = provider.embed("monthly recurring revenue")
    arr = provider.embed("MRR")
    unrelated = provider.embed("today is a sunny day")

    def cos(a, b):
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    assert cos(revenue, arr) > cos(revenue, unrelated)


def test_spanish_text_works(provider):
    vec = provider.embed("ingresos recurrentes mensuales")
    assert vec.shape[0] == provider.dimension
