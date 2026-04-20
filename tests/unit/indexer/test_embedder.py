import asyncio
import os
import pytest
from piighost.indexer.embedder import MistralEmbedder, NullEmbedder, _StubEmbedder, build_embedder
from piighost.service.config import EmbedderSection, ServiceConfig


def test_null_embedder_returns_empty_vectors():
    emb = NullEmbedder()
    vecs = asyncio.run(emb.embed(["hello", "world"]))
    assert vecs == [[], []]


def test_stub_embedder_deterministic():
    emb = _StubEmbedder()
    v1 = asyncio.run(emb.embed(["hello"]))
    v2 = asyncio.run(emb.embed(["hello"]))
    assert v1 == v2
    assert len(v1[0]) == 8


def test_stub_embedder_different_inputs():
    emb = _StubEmbedder()
    v = asyncio.run(emb.embed(["hello", "world"]))
    assert v[0] != v[1]


def test_build_embedder_stub_env(monkeypatch):
    monkeypatch.setenv("PIIGHOST_EMBEDDER", "stub")
    cfg = ServiceConfig()
    emb = build_embedder(cfg.embedder)
    assert isinstance(emb, _StubEmbedder)


def test_build_embedder_none_backend(monkeypatch):
    monkeypatch.delenv("PIIGHOST_EMBEDDER", raising=False)
    cfg = ServiceConfig()
    # default backend is "none"
    emb = build_embedder(cfg.embedder)
    assert isinstance(emb, NullEmbedder)


def test_mistral_embedder_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.delenv("PIIGHOST_EMBEDDER", raising=False)
    with pytest.raises(RuntimeError, match="MISTRAL_API_KEY"):
        build_embedder(EmbedderSection(backend="mistral"))


def test_mistral_embedder_accepts_api_key(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    monkeypatch.delenv("PIIGHOST_EMBEDDER", raising=False)
    embedder = build_embedder(EmbedderSection(backend="mistral"))
    assert isinstance(embedder, MistralEmbedder)


def test_stub_override_wins_even_without_mistral_key(monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.setenv("PIIGHOST_EMBEDDER", "stub")
    embedder = build_embedder(EmbedderSection(backend="mistral"))
    assert embedder.__class__.__name__ == "_StubEmbedder"
