"""Haystack RAG wrapper: PIIGhostRetriever component + pipeline factory."""

from __future__ import annotations

from typing import Any

from haystack import Pipeline, component
from haystack.dataclasses import Document

from piighost.integrations.haystack._base import run_coroutine_sync
from piighost.service.core import PIIGhostService


@component
class PIIGhostRetriever:
    """Haystack retriever wrapping :meth:`PIIGhostService.query`."""

    def __init__(
        self,
        svc: PIIGhostService,
        *,
        project: str = "default",
        top_k: int = 5,
    ) -> None:
        self._svc = svc
        self._project = project
        self._top_k = top_k

    @component.output_types(documents=list[Document])
    def run(self, query: str, top_k: int | None = None) -> dict:
        return run_coroutine_sync(self._arun(query, top_k=top_k))

    @component.output_types(documents=list[Document])
    async def run_async(self, query: str, top_k: int | None = None) -> dict:
        return await self._arun(query, top_k=top_k)

    async def _arun(self, query: str, top_k: int | None) -> dict:
        k = top_k if top_k is not None else self._top_k
        result = await self._svc.query(query, project=self._project, k=k)
        docs = [
            Document(
                content=hit.chunk,
                meta={
                    "doc_id": hit.doc_id,
                    "file_path": hit.file_path,
                    "score": hit.score,
                    "rank": hit.rank,
                    "project": self._project,
                },
            )
            for hit in result.hits
        ]
        return {"documents": docs}


_HAYSTACK_PROMPT_TEMPLATE = """You are a helpful assistant. Answer based on the provided context.
Both the context and question contain opaque tokens like <LABEL:hash>. Preserve them exactly.

Context:
{% for doc in documents %}
{{ doc.content }}
{% endfor %}

Question: {{ question }}
"""


@component
class _ServiceQueryAnonymizer:
    """Anonymize a query via PIIGhostService (project-scoped)."""

    def __init__(self, svc: PIIGhostService, *, project: str = "default") -> None:
        self._svc = svc
        self._project = project

    @component.output_types(query=str)
    def run(self, text: str) -> dict:
        return run_coroutine_sync(self._arun(text))

    @component.output_types(query=str)
    async def run_async(self, text: str) -> dict:
        return await self._arun(text)

    async def _arun(self, text: str) -> dict:
        result = await self._svc.anonymize(text, project=self._project)
        return {"query": result.anonymized}


@component
class _ServiceRehydrator:
    """Rehydrate text via PIIGhostService (project-scoped)."""

    def __init__(self, svc: PIIGhostService, *, project: str = "default") -> None:
        self._svc = svc
        self._project = project

    @component.output_types(text=str)
    def run(self, text: str | None = None) -> dict:
        if text is None:
            return {"text": ""}
        return run_coroutine_sync(self._arun(text))

    @component.output_types(text=str)
    async def run_async(self, text: str | None = None) -> dict:
        if text is None:
            return {"text": ""}
        return await self._arun(text)

    async def _arun(self, text: str) -> dict:
        result = await self._svc.rehydrate(text, project=self._project, strict=False)
        return {"text": result.text}


class CachedRagPipeline:
    """Pipeline wrapper that checks a cache before running."""

    def __init__(
        self,
        pipeline: Pipeline,
        svc: PIIGhostService,
        project: str,
        cache,
        top_k: int,
    ) -> None:
        self._pipeline = pipeline
        self._svc = svc
        self._project = project
        self._cache = cache
        self._top_k = top_k

    @property
    def graph(self):
        return self._pipeline.graph

    def run(self, inputs: dict) -> dict:
        key, hit = run_coroutine_sync(self._lookup(inputs))
        if hit is not None:
            return {"rehydrator": {"text": hit}}
        result = self._pipeline.run(inputs)
        answer = result.get("rehydrator", {}).get("text", "")
        if answer:
            run_coroutine_sync(self._cache.set(key, answer))
        return result

    async def _lookup(self, inputs: dict) -> tuple[str, str | None]:
        from piighost.integrations.langchain.cache import RagCache

        query_text = inputs.get("query_anonymizer", {}).get("text", "")
        anon = await self._svc.anonymize(query_text, project=self._project)
        key = RagCache.make_key(
            project=self._project,
            anonymized_query=anon.anonymized,
            k=self._top_k,
            filter_repr="None",
            prompt_hash="haystack_default",
            llm_id="haystack_generator",
            rerank=False,
            top_n=20,
        )
        hit = await self._cache.get(key)
        return key, hit


def build_piighost_rag(
    svc: PIIGhostService,
    *,
    project: str = "default",
    llm_generator: Any | None = None,
    top_k: int = 5,
    streaming_callback: Any | None = None,
    cache: Any | None = None,
):
    """Build a pre-wired Haystack :class:`Pipeline` for PII-safe RAG.

    Components and connections (with LLM):

        query_anonymizer -> retriever -> prompt_builder -> llm -> rehydrator

    Without an LLM the pipeline stops at ``prompt_builder``. This lets tests
    assert wiring without exercising an LLM.

    If ``streaming_callback`` is provided alongside an ``llm_generator`` that
    exposes a ``streaming_callback`` attribute, intermediate LLM chunks are
    rehydrated through a :class:`StreamingRehydrator` before being forwarded
    to the user callback.

    If ``cache`` is provided, returns a :class:`CachedRagPipeline` wrapper
    that short-circuits on cache hits; otherwise returns the raw
    :class:`Pipeline`.
    """
    from haystack.components.builders import PromptBuilder

    pipeline = Pipeline()
    pipeline.add_component(
        "query_anonymizer", _ServiceQueryAnonymizer(svc, project=project)
    )
    pipeline.add_component(
        "retriever", PIIGhostRetriever(svc, project=project, top_k=top_k)
    )
    pipeline.add_component(
        "prompt_builder",
        PromptBuilder(
            template=_HAYSTACK_PROMPT_TEMPLATE,
            required_variables=["question", "documents"],
        ),
    )
    pipeline.add_component(
        "rehydrator", _ServiceRehydrator(svc, project=project)
    )
    if llm_generator is not None:
        if streaming_callback is not None and hasattr(
            llm_generator, "streaming_callback"
        ):
            from piighost.integrations.langchain.streaming import StreamingRehydrator

            rehydrator = StreamingRehydrator(svc, project)

            def _wrapped(chunk) -> None:
                content = getattr(chunk, "content", str(chunk))
                emitted = run_coroutine_sync(rehydrator.feed(content))
                if emitted:
                    try:
                        from haystack.dataclasses import StreamingChunk

                        streaming_callback(StreamingChunk(content=emitted))
                    except ImportError:  # pragma: no cover
                        streaming_callback(emitted)

            llm_generator.streaming_callback = _wrapped
        pipeline.add_component("llm", llm_generator)

    pipeline.connect("query_anonymizer.query", "retriever.query")
    pipeline.connect("query_anonymizer.query", "prompt_builder.question")
    pipeline.connect("retriever.documents", "prompt_builder.documents")
    if llm_generator is not None:
        pipeline.connect("prompt_builder.prompt", "llm.prompt")
        pipeline.connect("llm.replies", "rehydrator.text")

    if cache is not None:
        return CachedRagPipeline(pipeline, svc, project, cache, top_k)
    return pipeline
