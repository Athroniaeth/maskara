"""End-to-end RAG wrapper for LangChain backed by :class:`PIIGhostService`."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from piighost.service.core import PIIGhostService
from piighost.service.models import IndexReport

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from langchain_core.language_models import BaseLanguageModel
    from langchain_core.retrievers import BaseRetriever
    from langchain_core.runnables import Runnable

    from piighost.indexer.filters import QueryFilter


def _build_retriever_class():
    """Lazy construction so langchain_core is only imported when used."""
    from langchain_core.documents import Document
    from langchain_core.retrievers import BaseRetriever
    from pydantic import ConfigDict

    class _PIIGhostRetriever(BaseRetriever):
        model_config = ConfigDict(arbitrary_types_allowed=True)

        svc: Any
        project: str = "default"
        k: int = 5

        async def _aget_relevant_documents(self, query: str, *, run_manager=None) -> list[Document]:
            result = await self.svc.query(query, project=self.project, k=self.k)
            return [
                Document(
                    page_content=hit.chunk,
                    metadata={
                        "doc_id": hit.doc_id,
                        "file_path": hit.file_path,
                        "score": hit.score,
                        "rank": hit.rank,
                        "project": self.project,
                    },
                )
                for hit in result.hits
            ]

        def _get_relevant_documents(self, query: str, *, run_manager=None) -> list[Document]:
            import asyncio
            return asyncio.run(self._aget_relevant_documents(query))

    return _PIIGhostRetriever


_DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful assistant. Answer the user's question based on the provided context.\n"
    "The context and question contain opaque tokens of the form <LABEL:hash> (e.g., <PERSON:abc123>).\n"
    "Preserve these tokens EXACTLY in your answer — do not expand, explain, or replace them.\n"
    "If the context does not contain enough information, say \"I don't know.\""
)


def _build_prompt(*, context: str, question: str) -> list:
    from langchain_core.messages import HumanMessage, SystemMessage

    return [
        SystemMessage(content=_DEFAULT_SYSTEM_PROMPT),
        HumanMessage(content=f"Context:\n{context}\n\nQuestion: {question}"),
    ]


class PIIGhostRAG:
    """End-to-end PII-safe RAG chain backed by :class:`PIIGhostService`.

    One instance per project. Compose ``.anonymizer``, ``.retriever``,
    ``.rehydrator`` into custom chains, or call ``.as_chain(llm)`` for the
    standard pipeline.
    """

    def __init__(
        self,
        svc: PIIGhostService,
        *,
        project: str = "default",
        cache: "Any | None" = None,
    ) -> None:
        self._svc = svc
        self._project = project
        self._cache = cache

    async def ingest(
        self,
        path: Path,
        *,
        recursive: bool = True,
        force: bool = False,
    ) -> IndexReport:
        return await self._svc.index_path(
            path, recursive=recursive, force=force, project=self._project
        )

    @property
    def anonymizer(self) -> "Runnable[str, dict]":
        from langchain_core.runnables import RunnableLambda

        async def _run(text: str) -> dict:
            result = await self._svc.anonymize(text, project=self._project)
            return {
                "anonymized": result.anonymized,
                "entities": [
                    {"token": e.token, "label": e.label, "count": e.count}
                    for e in result.entities
                ],
            }

        return RunnableLambda(_run)

    @property
    def rehydrator(self) -> "Runnable[str, str]":
        from langchain_core.runnables import RunnableLambda

        async def _run(text: str) -> str:
            result = await self._svc.rehydrate(text, project=self._project, strict=False)
            return result.text

        return RunnableLambda(_run)

    @property
    def retriever(self) -> "BaseRetriever":
        retriever_cls = _build_retriever_class()
        return retriever_cls(svc=self._svc, project=self._project)

    async def query(
        self,
        text: str,
        *,
        k: int = 5,
        llm: "BaseLanguageModel | None" = None,
        prompt: Any | None = None,
        filter: "QueryFilter | None" = None,
        rerank: bool = False,
        top_n: int = 20,
    ) -> str:
        anon = await self._svc.anonymize(text, project=self._project)

        cache_key: str | None = None
        if self._cache is not None and llm is not None:
            from piighost.integrations.langchain.cache import (
                RagCache,
                _llm_id,
                _prompt_fingerprint,
            )

            cache_key = RagCache.make_key(
                project=self._project,
                anonymized_query=anon.anonymized,
                k=k,
                filter_repr=repr(filter),
                prompt_hash=_prompt_fingerprint(prompt),
                llm_id=_llm_id(llm),
            )
            hit = await self._cache.get(cache_key)
            if hit is not None:
                return hit

        result = await self._svc.query(
            anon.anonymized,
            project=self._project,
            k=k,
            filter=filter,
            rerank=rerank,
            top_n=top_n,
        )
        context = "\n\n".join(hit.chunk for hit in result.hits)

        if llm is None:
            rehydrated = await self._svc.rehydrate(
                context, project=self._project, strict=False
            )
            return rehydrated.text

        if prompt is not None:
            messages = prompt.format_messages(context=context, question=anon.anonymized)
        else:
            messages = _build_prompt(context=context, question=anon.anonymized)

        raw_answer = await llm.ainvoke(messages)
        answer_text = raw_answer.content if hasattr(raw_answer, "content") else str(raw_answer)
        rehydrated = await self._svc.rehydrate(
            answer_text, project=self._project, strict=False
        )
        if cache_key is not None:
            await self._cache.set(cache_key, rehydrated.text)
        return rehydrated.text

    async def astream(
        self,
        text: str,
        *,
        llm: "BaseLanguageModel",
        k: int = 5,
        prompt: Any | None = None,
        filter: "QueryFilter | None" = None,
        rerank: bool = False,
        top_n: int = 20,
    ) -> "AsyncIterator[str]":
        from piighost.integrations.langchain.streaming import StreamingRehydrator

        anon = await self._svc.anonymize(text, project=self._project)
        result = await self._svc.query(
            anon.anonymized,
            project=self._project,
            k=k,
            filter=filter,
            rerank=rerank,
            top_n=top_n,
        )
        context = "\n\n".join(hit.chunk for hit in result.hits)

        if prompt is not None:
            messages = prompt.format_messages(context=context, question=anon.anonymized)
        else:
            messages = _build_prompt(context=context, question=anon.anonymized)

        rehydrator = StreamingRehydrator(self._svc, self._project)
        async for chunk in llm.astream(messages):
            text_chunk = chunk.content if hasattr(chunk, "content") else str(chunk)
            emitted = await rehydrator.feed(text_chunk)
            if emitted:
                yield emitted
        final = await rehydrator.finalize()
        if final:
            yield final

    def as_chain(
        self,
        llm: "BaseLanguageModel",
        *,
        prompt: Any | None = None,
    ) -> "Runnable[str, str]":
        from langchain_core.runnables import RunnableLambda

        async def _run(question: str) -> str:
            return await self.query(question, llm=llm, prompt=prompt)

        return RunnableLambda(_run)
