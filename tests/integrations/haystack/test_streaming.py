import asyncio

import pytest

pytest.importorskip("haystack")

from haystack import component

from piighost.integrations.haystack.rag import build_piighost_rag
from piighost.service.core import PIIGhostService


@pytest.fixture()
def svc(tmp_path, monkeypatch):
    monkeypatch.setenv("PIIGHOST_EMBEDDER", "stub")
    monkeypatch.setenv("PIIGHOST_DETECTOR", "stub")
    service = asyncio.run(PIIGhostService.create(vault_dir=tmp_path / "vault"))
    yield service
    asyncio.run(service.close())


@component
class _StreamingGenerator:
    """Generator that invokes streaming_callback for each character."""

    def __init__(self) -> None:
        self.streaming_callback = None

    @component.output_types(replies=list[str])
    def run(self, prompt: str) -> dict:
        if self.streaming_callback is not None:
            try:
                from haystack.dataclasses import StreamingChunk
            except ImportError:  # pragma: no cover
                StreamingChunk = None
            for ch in "hello":
                if StreamingChunk is not None:
                    self.streaming_callback(StreamingChunk(content=ch))
                else:
                    self.streaming_callback(ch)
        return {"replies": ["hello"]}


def test_streaming_callback_receives_rehydrated_chunks(svc, tmp_path):
    captured: list[str] = []

    def user_callback(chunk):
        content = getattr(chunk, "content", str(chunk))
        captured.append(content)

    doc = tmp_path / "doc.txt"
    doc.write_text("Alice works in Paris")
    asyncio.run(svc.index_path(doc, project="p"))

    gen = _StreamingGenerator()
    pipeline = build_piighost_rag(
        svc, project="p", llm_generator=gen, streaming_callback=user_callback
    )
    pipeline.run({"query_anonymizer": {"text": "Who is Alice?"}})
    # The user callback must have been invoked for each streamed char
    assert len(captured) >= 1
    assert "".join(captured) == "hello"
