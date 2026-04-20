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
