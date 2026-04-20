from __future__ import annotations

import hashlib
import os
from typing import Protocol, runtime_checkable

from piighost.service.config import EmbedderSection


@runtime_checkable
class AnyEmbedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class NullEmbedder:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[] for _ in texts]


class _StubEmbedder:
    DIM = 8

    async def embed(self, texts: list[str]) -> list[list[float]]:
        result = []
        for t in texts:
            digest = hashlib.md5(t.encode()).digest()[: self.DIM]
            result.append([b / 255.0 for b in digest])
        return result


class LocalEmbedder:
    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(model_name)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(list(texts)).tolist()


class MistralEmbedder:
    def __init__(self, model: str) -> None:
        self._api_key = os.environ.get("MISTRAL_API_KEY", "")
        self._model = model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.mistral.ai/v1/embeddings",
                json={"model": self._model, "input": texts},
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
            return [item["embedding"] for item in data["data"]]


def build_embedder(cfg: EmbedderSection) -> AnyEmbedder:
    if os.environ.get("PIIGHOST_EMBEDDER") == "stub":
        return _StubEmbedder()
    if cfg.backend == "none":
        return NullEmbedder()
    if cfg.backend == "local":
        return LocalEmbedder(cfg.local_model)
    if cfg.backend == "mistral":
        return MistralEmbedder(cfg.mistral_model)
    raise ValueError(f"Unknown embedder backend: {cfg.backend!r}")
