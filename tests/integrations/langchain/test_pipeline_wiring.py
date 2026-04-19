"""End-to-end LangChain wiring: classify → anonymize → index → query → rehydrate."""

import pytest

pytest.importorskip("langchain_core")

from langchain_core.documents import Document  # noqa: E402

from piighost.integrations.langchain.transformers import (  # noqa: E402
    PIIGhostDocumentAnonymizer,
    PIIGhostDocumentClassifier,
    PIIGhostQueryAnonymizer,
    PIIGhostRehydrator,
)


class _InMemoryStore:
    """Minimal vectorstore stub: stores Documents, returns them on substring match."""

    def __init__(self) -> None:
        self.docs: list[Document] = []

    def add_documents(self, docs: list[Document]) -> None:
        self.docs.extend(docs)

    def similarity_search(self, query: str, k: int = 5) -> list[Document]:
        return [
            Document(page_content=d.page_content, metadata=dict(d.metadata))
            for d in self.docs
            if query in d.page_content
        ][:k]


@pytest.mark.asyncio
async def test_ingest_then_query_end_to_end(
    pipeline, stub_classifier, gdpr_schemas
) -> None:
    # Ingest: classify → anonymize → store
    classifier = PIIGhostDocumentClassifier(
        classifier=stub_classifier, schemas=gdpr_schemas
    )
    anonymizer = PIIGhostDocumentAnonymizer(pipeline=pipeline)
    store = _InMemoryStore()

    raw = [
        Document(page_content="Alice visited Paris.", metadata={"source": "doc-1"}),
    ]
    classified = await classifier.atransform_documents(raw)
    anonymized = await anonymizer.atransform_documents(list(classified))

    assert "Alice" not in anonymized[0].page_content
    assert anonymized[0].metadata["labels"] == {"gdpr_category": ["none"]}
    # Paris is NOT detected by the stub detector → remains as plain text.
    assert "Paris" in anonymized[0].page_content
    store.add_documents(list(anonymized))

    # Query: anonymize query → retrieve → rehydrate
    query_anon = PIIGhostQueryAnonymizer(pipeline=pipeline)
    rehydrator = PIIGhostRehydrator()

    qresult = await query_anon.ainvoke("Where did Alice go?")

    # HashPlaceholderFactory is deterministic: SHA-256("alice:PERSON") is the
    # same regardless of thread_id, so the token produced for "Alice" in the
    # query is identical to the one embedded in the anonymized document.
    # Extract that token and use it as the search term.
    assert qresult["entities"], "Alice should be detected in the query"
    alice_token = pipeline.ph_factory.create(qresult["entities"])[
        qresult["entities"][0]
    ]
    hits = store.similarity_search(alice_token, k=3)
    assert hits, "query token should match indexed token"

    rehydrated = await rehydrator.atransform_documents(hits)
    assert "Alice" in rehydrated[0].page_content
    assert "Paris" in rehydrated[0].page_content
