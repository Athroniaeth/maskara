"""LangChain document-pipeline components for PIIGhost."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Sequence

from langchain_core.documents import Document
from langchain_core.documents.transformers import BaseDocumentTransformer

from piighost.classifier.base import AnyClassifier, ClassificationSchema
from piighost.exceptions import RehydrationError
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
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.atransform_documents(documents, **kwargs))  # type: ignore[return-value]
        raise RuntimeError(
            "PIIGhostDocumentAnonymizer.transform_documents() was called from inside "
            "a running event loop. Use atransform_documents() instead."
        )

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


class PIIGhostDocumentClassifier(BaseDocumentTransformer):
    """Classify Documents and write structured labels to metadata[meta_key].

    Runs BEFORE the anonymizer so the classifier sees real text.
    """

    def __init__(
        self,
        classifier: AnyClassifier,
        schemas: dict[str, ClassificationSchema],
        meta_key: str = "labels",
        strict: bool = False,
    ) -> None:
        self._classifier = classifier
        self._schemas = schemas
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
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.atransform_documents(documents, **kwargs))  # type: ignore[return-value]
        raise RuntimeError(
            "PIIGhostDocumentClassifier.transform_documents() was called from "
            "inside a running event loop. Use atransform_documents() instead."
        )

    async def _process(self, doc: Document) -> None:
        content = doc.page_content
        if content is None or not content.strip():
            logger.warning("Skipping classifier on empty content")
            return
        try:
            labels = await self._classifier.classify(content, self._schemas)
        except Exception as exc:
            if self._strict:
                raise
            logger.error("classification failed: %s", exc)
            doc.metadata["classifier_error"] = f"classify_failed:{type(exc).__name__}"
            return
        doc.metadata[self._meta_key] = labels


class PIIGhostRehydrator(BaseDocumentTransformer):
    """Restore original content from the JSON mapping in metadata[meta_key].

    Longest-token-first replacement avoids partial-token collisions.
    No pipeline dependency — pure meta-driven.
    """

    def __init__(
        self,
        fail_on_missing_mapping: bool = False,
        meta_key: str = "piighost_mapping",
    ) -> None:
        self._fail_on_missing = fail_on_missing_mapping
        self._meta_key = meta_key

    async def atransform_documents(
        self, documents: Sequence[Document], **kwargs: Any
    ) -> Sequence[Document]:
        for doc in documents:
            self._rehydrate(doc)
        return list(documents)

    def transform_documents(
        self, documents: Sequence[Document], **kwargs: Any
    ) -> Sequence[Document]:
        for doc in documents:
            self._rehydrate(doc)
        return list(documents)

    def _rehydrate(self, doc: Document) -> None:
        raw = doc.metadata.get(self._meta_key)
        if raw is None:
            if self._fail_on_missing:
                raise RehydrationError(
                    f"Document has no mapping in metadata[{self._meta_key!r}]",
                    doc.page_content or "",
                )
            logger.error("doc missing mapping; content unchanged")
            return

        try:
            mapping = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            if self._fail_on_missing:
                raise RehydrationError(
                    f"Document has malformed mapping: {exc}",
                    doc.page_content or "",
                ) from exc
            logger.error("doc mapping malformed: %s", exc)
            return

        if not isinstance(mapping, list) or doc.page_content is None:
            return

        mapping.sort(key=lambda item: len(item.get("token", "")), reverse=True)

        content = doc.page_content
        for item in mapping:
            token = item.get("token")
            original = item.get("original")
            if not token or original is None:
                continue
            content = content.replace(token, original)
        doc.page_content = content
