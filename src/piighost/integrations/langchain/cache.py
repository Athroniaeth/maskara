"""aiocache-backed answer cache for PIIGhostRAG."""

from __future__ import annotations

import hashlib
import json
from typing import Protocol

from aiocache import SimpleMemoryCache


class AnyCache(Protocol):
    async def get(self, key: str) -> str | None: ...
    async def set(self, key: str, value: str, ttl: int | None = None) -> None: ...


class RagCache:
    def __init__(self, backend: AnyCache | None = None, *, ttl: int = 300) -> None:
        self._backend = backend or SimpleMemoryCache()
        self._ttl = ttl

    @staticmethod
    def make_key(
        *,
        project: str,
        anonymized_query: str,
        k: int,
        filter_repr: str,
        prompt_hash: str,
        llm_id: str,
    ) -> str:
        payload = json.dumps(
            {
                "p": project,
                "q": anonymized_query,
                "k": k,
                "f": filter_repr,
                "pr": prompt_hash,
                "llm": llm_id,
            },
            sort_keys=True,
        )
        return "piighost_rag:" + hashlib.sha256(payload.encode()).hexdigest()[:32]

    async def get(self, key: str) -> str | None:
        try:
            return await self._backend.get(key)
        except Exception:
            return None

    async def set(self, key: str, value: str) -> None:
        try:
            await self._backend.set(key, value, ttl=self._ttl)
        except Exception:
            pass


def _prompt_fingerprint(prompt) -> str:
    if prompt is None:
        return "default"
    text = getattr(prompt, "template", repr(prompt))
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def _llm_id(llm) -> str:
    name = type(llm).__name__
    model = getattr(llm, "model_name", None) or getattr(llm, "model", "")
    return f"{name}:{model}" if model else name
