import asyncio

import pytest

pytest.importorskip("langchain_core")

from piighost.integrations.langchain.streaming import StreamingRehydrator
from piighost.service.core import PIIGhostService


@pytest.fixture()
def svc_with_tokens(tmp_path, monkeypatch):
    """Service with a known entity so rehydration has something to do."""
    monkeypatch.setenv("PIIGHOST_EMBEDDER", "stub")
    monkeypatch.setenv("PIIGHOST_DETECTOR", "stub")
    service = asyncio.run(PIIGhostService.create(vault_dir=tmp_path / "vault"))
    # Anonymize so "Alice" → <PERSON:...> is in the vault
    anon = asyncio.run(service.anonymize("Alice works here", project="p"))
    token = anon.entities[0].token
    yield service, token
    asyncio.run(service.close())


def test_feed_plain_text_emits_immediately(svc_with_tokens):
    svc, _ = svc_with_tokens
    r = StreamingRehydrator(svc, "p")
    out = asyncio.run(r.feed("hello world"))
    assert out == "hello world"


def test_feed_complete_token_is_rehydrated(svc_with_tokens):
    svc, token = svc_with_tokens
    r = StreamingRehydrator(svc, "p")
    out = asyncio.run(r.feed(f"Name: {token} done"))
    assert "Alice" in out
    assert token not in out


def test_partial_token_stays_buffered(svc_with_tokens):
    svc, token = svc_with_tokens
    r = StreamingRehydrator(svc, "p")
    # Split token right after "<PERSON:"
    prefix, suffix = token[:8], token[8:]
    out1 = asyncio.run(r.feed(f"Name: {prefix}"))
    # The partial "<PERSON:" must NOT have been emitted yet
    assert "<" not in out1  # no partial token leaked
    assert out1 == "Name: "

    out2 = asyncio.run(r.feed(suffix))
    assert "Alice" in out2


def test_finalize_flushes_buffer(svc_with_tokens):
    svc, _ = svc_with_tokens
    r = StreamingRehydrator(svc, "p")
    asyncio.run(r.feed("pending"))
    # "pending" is plain text so it was already emitted; buffer is empty
    final = asyncio.run(r.finalize())
    assert final == ""


def test_finalize_flushes_partial_that_never_completes(svc_with_tokens):
    svc, _ = svc_with_tokens
    r = StreamingRehydrator(svc, "p")
    # Simulate a stream that ends with an incomplete token
    out = asyncio.run(r.feed("prefix <PERSON:abc"))
    # Incomplete token stays buffered
    assert "<" not in out
    final = asyncio.run(r.finalize())
    # On finalize, emit raw buffer (not a valid token, but no PII either)
    assert "<PERSON:abc" in final
