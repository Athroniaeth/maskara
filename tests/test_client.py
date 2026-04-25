"""Unit tests for PIIGhostClient.

Uses httpx.MockTransport to stub the remote piighost-api server so the
tests run fully offline and deterministic.
"""

from __future__ import annotations

import importlib.util

import pytest

if importlib.util.find_spec("httpx") is None:
    pytest.skip(
        "httpx not installed (install piighost[client])", allow_module_level=True
    )

import httpx

from piighost.client import PIIGhostClient, _deserialize_entities
from piighost.exceptions import CacheMissError
from piighost.models import Detection, Entity, Span

BASE_URL = "http://piighost.test"
API_KEY = "ak_v1-test"


def _make_client(handler) -> PIIGhostClient:
    """Build a PIIGhostClient wired to an in-memory MockTransport."""
    client = PIIGhostClient(BASE_URL, API_KEY)
    client._client = httpx.AsyncClient(
        base_url=BASE_URL,
        headers={"Authorization": f"Bearer {API_KEY}"},
        transport=httpx.MockTransport(handler),
    )
    return client


def _entity_payload(
    text: str, label: str, start: int, end: int, confidence: float = 0.99
) -> dict:
    """Shape mirroring piighost-api's JSON entity representation."""
    return {
        "detections": [
            {
                "text": text,
                "label": label,
                "start_pos": start,
                "end_pos": end,
                "confidence": confidence,
            }
        ]
    }


# ---------------------------------------------------------------------------
# get_config
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_config_returns_server_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/config"
        assert request.headers["authorization"] == f"Bearer {API_KEY}"
        return httpx.Response(
            200, json={"labels": ["PERSON"], "placeholder_factory": "counter"}
        )

    async with _make_client(handler) as client:
        config = await client.get_config()

    assert config == {"labels": ["PERSON"], "placeholder_factory": "counter"}


@pytest.mark.asyncio
async def test_get_config_raises_on_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    async with _make_client(handler) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await client.get_config()


# ---------------------------------------------------------------------------
# detect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detect_posts_text_and_thread_id() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/detect"
        captured["body"] = request.read()
        return httpx.Response(
            200,
            json={"entities": [_entity_payload("Patrick", "PERSON", 0, 7)]},
        )

    async with _make_client(handler) as client:
        entities = await client.detect("Patrick habite ici", thread_id="t-42")

    import json

    assert json.loads(captured["body"]) == {
        "text": "Patrick habite ici",
        "thread_id": "t-42",
    }
    assert len(entities) == 1
    assert entities[0].label == "PERSON"
    assert entities[0].detections[0].text == "Patrick"


@pytest.mark.asyncio
async def test_detect_defaults_thread_id_to_default() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.read()
        return httpx.Response(200, json={"entities": []})

    async with _make_client(handler) as client:
        entities = await client.detect("hi")

    import json

    assert json.loads(captured["body"])["thread_id"] == "default"
    assert entities == []


@pytest.mark.asyncio
async def test_detect_handles_missing_entities_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    async with _make_client(handler) as client:
        entities = await client.detect("hi")

    assert entities == []


# ---------------------------------------------------------------------------
# override_detections
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_override_detections_serializes_each_detection() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PUT"
        assert request.url.path == "/v1/detect"
        captured["body"] = request.read()
        return httpx.Response(204)

    detections = [
        Detection(text="Patrick", label="PERSON", position=Span(0, 7), confidence=0.9),
        Detection(
            text="Paris", label="LOCATION", position=Span(20, 25), confidence=0.8
        ),
    ]

    async with _make_client(handler) as client:
        await client.override_detections(
            "Patrick habite a Paris", detections, thread_id="t-1"
        )

    import json

    body = json.loads(captured["body"])
    assert body["text"] == "Patrick habite a Paris"
    assert body["thread_id"] == "t-1"
    assert body["detections"] == [
        {
            "text": "Patrick",
            "label": "PERSON",
            "start_pos": 0,
            "end_pos": 7,
            "confidence": 0.9,
        },
        {
            "text": "Paris",
            "label": "LOCATION",
            "start_pos": 20,
            "end_pos": 25,
            "confidence": 0.8,
        },
    ]


@pytest.mark.asyncio
async def test_override_detections_raises_on_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "bad request"})

    async with _make_client(handler) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await client.override_detections("text", [], thread_id="t")


# ---------------------------------------------------------------------------
# anonymize
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_anonymize_returns_text_and_entities() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/anonymize"
        return httpx.Response(
            200,
            json={
                "anonymized_text": "<<PERSON:1>> habite ici",
                "entities": [_entity_payload("Patrick", "PERSON", 0, 7)],
            },
        )

    async with _make_client(handler) as client:
        text, entities = await client.anonymize("Patrick habite ici")

    assert text == "<<PERSON:1>> habite ici"
    assert len(entities) == 1
    assert entities[0].detections[0].text == "Patrick"


@pytest.mark.asyncio
async def test_anonymize_handles_no_entities() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"anonymized_text": "hi", "entities": []})

    async with _make_client(handler) as client:
        text, entities = await client.anonymize("hi")

    assert text == "hi"
    assert entities == []


# ---------------------------------------------------------------------------
# deanonymize
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deanonymize_returns_original_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/deanonymize"
        return httpx.Response(
            200,
            json={
                "text": "Patrick habite ici",
                "entities": [_entity_payload("Patrick", "PERSON", 0, 7)],
            },
        )

    async with _make_client(handler) as client:
        text, entities = await client.deanonymize("<<PERSON:1>> habite ici")

    assert text == "Patrick habite ici"
    assert len(entities) == 1


@pytest.mark.asyncio
async def test_deanonymize_raises_cache_miss_on_404() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "no mapping for thread"})

    async with _make_client(handler) as client:
        with pytest.raises(CacheMissError, match="no mapping for thread"):
            await client.deanonymize("<<PERSON:1>>")


@pytest.mark.asyncio
async def test_deanonymize_404_without_error_key_still_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={})

    async with _make_client(handler) as client:
        with pytest.raises(CacheMissError, match="Cache miss"):
            await client.deanonymize("<<PERSON:1>>")


@pytest.mark.asyncio
async def test_deanonymize_raises_on_other_http_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "server error"})

    async with _make_client(handler) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await client.deanonymize("<<PERSON:1>>")


# ---------------------------------------------------------------------------
# deanonymize_with_ent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deanonymize_with_ent_returns_plain_text() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/deanonymize/entities"
        captured["body"] = request.read()
        return httpx.Response(200, json={"text": "Bonjour Patrick"})

    async with _make_client(handler) as client:
        text = await client.deanonymize_with_ent(
            "Bonjour <<PERSON:1>>", thread_id="t-9"
        )

    import json

    assert text == "Bonjour Patrick"
    assert json.loads(captured["body"]) == {
        "text": "Bonjour <<PERSON:1>>",
        "thread_id": "t-9",
    }


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_context_manager_closes_underlying_client() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    client = _make_client(handler)
    async with client as c:
        assert c is client
    assert client._client.is_closed


@pytest.mark.asyncio
async def test_explicit_close() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    client = _make_client(handler)
    await client.close()
    assert client._client.is_closed


@pytest.mark.asyncio
async def test_init_configures_base_url_and_auth_header() -> None:
    client = PIIGhostClient(BASE_URL, API_KEY, timeout=5.0)
    try:
        assert str(client._client.base_url) == BASE_URL
        assert client._client.headers["authorization"] == f"Bearer {API_KEY}"
        assert client._client.timeout.read == 5.0
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# _deserialize_entities
# ---------------------------------------------------------------------------


def test_deserialize_entities_skips_entities_without_detections() -> None:
    data = [
        {"detections": []},
        _entity_payload("Patrick", "PERSON", 0, 7),
    ]
    entities = _deserialize_entities(data)
    assert len(entities) == 1
    assert entities[0].detections[0].text == "Patrick"


def test_deserialize_entities_preserves_all_fields() -> None:
    data = [
        {
            "detections": [
                {
                    "text": "Paris",
                    "label": "LOCATION",
                    "start_pos": 10,
                    "end_pos": 15,
                    "confidence": 0.77,
                },
                {
                    "text": "Paris",
                    "label": "LOCATION",
                    "start_pos": 30,
                    "end_pos": 35,
                    "confidence": 0.88,
                },
            ]
        }
    ]
    entities = _deserialize_entities(data)
    assert isinstance(entities[0], Entity)
    assert len(entities[0].detections) == 2
    first = entities[0].detections[0]
    assert first.text == "Paris"
    assert first.label == "LOCATION"
    assert first.position == Span(10, 15)
    assert first.confidence == 0.77


def test_deserialize_entities_empty_list_returns_empty() -> None:
    assert _deserialize_entities([]) == []
