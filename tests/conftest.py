"""Offline embedding adapter: predictable vectors without downloading a model or using an API."""

from hashlib import sha256

import pytest

from canonical_model_generator.repository_rag.embeddings import EmbeddingConfig


class FakeEmbedder:
    config = EmbeddingConfig()

    def embed(self, texts):
        return [[float(value) / 255 for value in sha256(text.encode()).digest()] for text in texts]


@pytest.fixture
def fake_embedder():
    return FakeEmbedder()
