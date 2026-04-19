"""LangChain document-pipeline components for PIIGhost."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Sequence

from langchain_core.documents import Document
from langchain_core.documents.transformers import BaseDocumentTransformer

from piighost.models import Entity
from piighost.pipeline.thread import ThreadAnonymizationPipeline
from piighost.placeholder import AnyPlaceholderFactory, CounterPlaceholderFactory

logger = logging.getLogger(__name__)


def _serialize_mapping(
    entities: list[Entity],
    ph_factory: AnyPlaceholderFactory,
) -> str:
    """Serialize the (token → original) mapping as a JSON list string.

    Each item has ``token``, ``original``, and ``label`` so downstream
    components can rebuild the token → original map without re-running
    the factory.
    """
    tokens = ph_factory.create(entities)
    items: list[dict[str, str]] = []
    for entity, token in tokens.items():
        for detection in entity.detections:
            items.append(
                {
                    "token": token,
                    "original": detection.text,
                    "label": entity.label,
                }
            )
    return json.dumps(items)


def _thread_id_for(doc: Document) -> str:
    if getattr(doc, "id", None):
        return str(doc.id)
    src = doc.metadata.get("source")
    return str(src) if src else "default"


class PIIGhostDocumentAnonymizer(BaseDocumentTransformer):
    """Anonymize LangChain Documents in place, storing the mapping in metadata.

    Uses each document's ``id`` (or ``metadata["source"]``) as the pipeline
    ``thread_id`` so that mapping and cache are scoped per document.
    ``page_content`` is replaced with anonymized text; the mapping is stored
    as a JSON string under ``metadata[meta_key]`` (default
    ``"piighost_mapping"``).

    Args:
        pipeline: A configured ``ThreadAnonymizationPipeline``.
        meta_key: Metadata dict key for the serialized mapping.
        strict: If ``True``, re-raise errors from detection. Default is
            lenient (log ERROR, leave content unchanged, write
            ``metadata["piighost_error"]``).
        allow_non_stable_tokens: Escape hatch for using
            ``CounterPlaceholderFactory``.  Default ``False`` rejects it
            at construction time with a clear error.
    """

    def __init__(
        self,
        pipeline: ThreadAnonymizationPipeline,
        meta_key: str = "piighost_mapping",
        strict: bool = False,
        allow_non_stable_tokens: bool = False,
    ) -> None:
        if (
            isinstance(pipeline.ph_factory, CounterPlaceholderFactory)
            and not allow_non_stable_tokens
        ):
            raise ValueError(
                "CounterPlaceholderFactory is not recommended for document "
                "pipelines because its tokens are not stable across documents "
                "or queries. Use HashPlaceholderFactory instead, or pass "
                "allow_non_stable_tokens=True if you know what you're doing."
            )
        self._pipeline = pipeline
        self._meta_key = meta_key
        self._strict = strict

    async def atransform_documents(
        self, documents: Sequence[Document], **kwargs: Any
    ) -> Sequence[Document]:
        for doc in documents:
            await self._process(doc)
        return list(documents)

    def transform_documents(
        self, documents: Sequence[Document], **kwargs: Any
    ) -> Sequence[Document]:
        return asyncio.run(self.atransform_documents(documents, **kwargs))

    async def _process(self, doc: Document) -> None:
        content = doc.page_content
        if content is None or not content.strip():
            return

        thread_id = _thread_id_for(doc)
        try:
            anonymized, entities = await self._pipeline.anonymize(
                content, thread_id=thread_id
            )
        except Exception as exc:
            if self._strict:
                raise
            logger.error("anonymization failed for %s: %s", thread_id, exc)
            doc.metadata["piighost_error"] = f"detection_failed:{type(exc).__name__}"
            return

        doc.page_content = anonymized
        doc.metadata[self._meta_key] = _serialize_mapping(
            entities, self._pipeline.ph_factory
        )
