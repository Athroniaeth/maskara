"""Async HTTP client for the piighost-api inference server.

Provides the same interface as ``ThreadAnonymizationPipeline`` but
delegates all processing to a remote piighost-api instance via HTTP.

Example::

    async with PIIGhostClient("http://localhost:8000", api_key="ak_v1-...") as client:
        config = await client.get_config()
        text, entities = await client.anonymize("Patrick habite à Paris")
        original, _ = await client.deanonymize(text)
"""

from __future__ import annotations

import importlib.util

if importlib.util.find_spec("httpx") is None:
    raise ImportError(
        "You must install httpx to use PIIGhostClient, "
        "please install piighost[client] for use client"
    )

import sys
from typing import Any

if sys.version_info >= (3, 11):
    from typing import Self
else:
    from typing_extensions import Self

import httpx

from piighost.exceptions import CacheMissError
from piighost.models import Detection, Entity


class PIIGhostClient:
    """Async HTTP client for a remote piighost-api server.

    Args:
        base_url: Base URL of the piighost-api server
            (e.g. ``"http://localhost:8000"``).
        api_key: API key for authentication (``Authorization: Bearer``).
        timeout: Request timeout in seconds (default: 30).
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 30.0,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    async def get_config(self) -> dict[str, Any]:
        """Retrieve the pipeline configuration from the server.

        Returns:
            A dict with ``labels`` and ``placeholder_factory`` keys.
        """
        response = await self._client.get("/v1/config")
        response.raise_for_status()
        return response.json()

    async def detect(
        self,
        text: str,
        thread_id: str = "default",
    ) -> list[Entity]:
        """Run detection only via the remote pipeline.

        Returns detected entities without anonymizing the text or
        recording entities in conversation memory.

        Args:
            text: The text to analyze.
            thread_id: Thread identifier for conversation isolation.

        Returns:
            A list of detected entities.
        """
        response = await self._client.post(
            "/v1/detect",
            json={"text": text, "thread_id": thread_id},
        )
        response.raise_for_status()
        data = response.json()
        return _deserialize_entities(data.get("entities", []))

    async def override_detections(
        self,
        text: str,
        detections: list[Detection],
        thread_id: str = "default",
    ) -> None:
        """Override cached detections for user corrections.

        Overwrites the detection cache entry for the given text so that
        subsequent calls to ``anonymize()`` use the corrected detections.

        Args:
            text: The original text whose detections should be overridden.
            detections: The corrected list of detections.
            thread_id: Thread identifier for conversation isolation.
        """
        response = await self._client.put(
            "/v1/detect",
            json={
                "text": text,
                "thread_id": thread_id,
                "detections": [d.to_dict() for d in detections],
            },
        )
        response.raise_for_status()

    async def anonymize(
        self,
        text: str,
        thread_id: str = "default",
    ) -> tuple[str, list[Entity]]:
        """Anonymize text via the remote pipeline.

        Args:
            text: The text to anonymize.
            thread_id: Thread identifier for conversation isolation.

        Returns:
            A tuple of (anonymized text, list of entities).
        """
        response = await self._client.post(
            "/v1/anonymize",
            json={"text": text, "thread_id": thread_id},
        )
        response.raise_for_status()
        data = response.json()
        entities = _deserialize_entities(data.get("entities", []))
        return data["anonymized_text"], entities

    async def deanonymize(
        self,
        text: str,
        thread_id: str = "default",
    ) -> tuple[str, list[Entity]]:
        """Deanonymize text via cache lookup on the server.

        Args:
            text: The anonymized text to restore.
            thread_id: Thread identifier for conversation isolation.

        Returns:
            A tuple of (original text, list of entities).

        Raises:
            CacheMissError: If the server has no cached mapping.
        """
        response = await self._client.post(
            "/v1/deanonymize",
            json={"text": text, "thread_id": thread_id},
        )
        if response.status_code == 404:
            raise CacheMissError(response.json().get("error", "Cache miss"))

        response.raise_for_status()
        data = response.json()
        entities = _deserialize_entities(data.get("entities", []))
        return data["text"], entities

    async def deanonymize_with_ent(
        self,
        text: str,
        thread_id: str = "default",
    ) -> str:
        """Deanonymize text via entity-based replacement.

        Works on any text containing placeholder tokens, even text
        never anonymized by the pipeline (e.g. LLM-generated output).

        Args:
            text: Text containing placeholder tokens.
            thread_id: Thread identifier for conversation isolation.

        Returns:
            Text with tokens replaced by original values.
        """
        response = await self._client.post(
            "/v1/deanonymize/entities",
            json={
                "text": text,
                "thread_id": thread_id,
            },
        )
        response.raise_for_status()
        return response.json()["text"]

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()


def _deserialize_entities(data: list[dict]) -> list[Entity]:
    """Convert JSON entity dicts back to piighost model objects."""
    return [Entity.from_dict(ent) for ent in data if ent.get("detections")]
