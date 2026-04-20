import asyncio

import pytest

pytest.importorskip("aiocache")

from piighost.integrations.langchain.cache import RagCache


def test_make_key_is_deterministic():
    kwargs = dict(
        project="p",
        anonymized_query="<PERSON:abc12345>",
        k=5,
        filter_repr="None",
        prompt_hash="default",
        llm_id="FakeLLM",
    )
    assert RagCache.make_key(**kwargs) == RagCache.make_key(**kwargs)


def test_make_key_differs_by_project():
    base = dict(
        anonymized_query="q",
        k=5,
        filter_repr="None",
        prompt_hash="default",
        llm_id="FakeLLM",
    )
    assert RagCache.make_key(project="a", **base) != RagCache.make_key(project="b", **base)


def test_make_key_prefix():
    key = RagCache.make_key(
        project="p",
        anonymized_query="q",
        k=5,
        filter_repr="None",
        prompt_hash="default",
        llm_id="FakeLLM",
    )
    assert key.startswith("piighost_rag:")


def test_roundtrip_in_memory():
    cache = RagCache()
    asyncio.run(cache.set("k", "value"))
    assert asyncio.run(cache.get("k")) == "value"


def test_get_missing_returns_none():
    cache = RagCache()
    assert asyncio.run(cache.get("nope")) is None
