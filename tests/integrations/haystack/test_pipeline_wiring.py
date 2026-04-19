"""End-to-end test wiring the 4 Phase 1 components in a real Haystack Pipeline.

Uses ``InMemoryDocumentStore`` + ``InMemoryBM25Retriever`` so we don't
require LanceDB for the fast test suite.  Verifies the core promise:
anonymized ingest, hash-stable query tokens, and meta-driven rehydration.
"""

from haystack import Document, Pipeline
from haystack.components.retrievers.in_memory import InMemoryBM25Retriever
from haystack.components.writers import DocumentWriter
from haystack.document_stores.in_memory import InMemoryDocumentStore

from piighost.classifier import ExactMatchClassifier
from piighost.integrations.haystack import (
    PIIGhostDocumentAnonymizer,
    PIIGhostDocumentClassifier,
    PIIGhostQueryAnonymizer,
    PIIGhostRehydrator,
)


class TestFullWiring:
    """Ingest → store → query → rehydrate with real Haystack Pipeline."""

    def test_end_to_end_flow(self, pipeline) -> None:
        store = InMemoryDocumentStore()

        classifier_double = ExactMatchClassifier(
            results={
                "Patrick habite à Paris.": {"sensitivity": ["low"]},
            }
        )

        ingest = Pipeline()
        ingest.add_component(
            "classifier",
            PIIGhostDocumentClassifier(
                classifier=classifier_double,
                schemas={
                    "sensitivity": {"labels": ["low", "high"], "multi_label": False}
                },
            ),
        )
        ingest.add_component(
            "anonymizer", PIIGhostDocumentAnonymizer(pipeline=pipeline)
        )
        ingest.add_component("writer", DocumentWriter(document_store=store))
        ingest.connect("classifier.documents", "anonymizer.documents")
        ingest.connect("anonymizer.documents", "writer.documents")

        doc = Document(content="Patrick habite à Paris.")
        ingest.run({"classifier": {"documents": [doc]}})

        stored = store.filter_documents()
        assert len(stored) == 1
        stored_content = stored[0].content
        assert "Patrick" not in stored_content
        assert "Paris" not in stored_content
        assert "<PERSON:" in stored_content
        assert stored[0].meta["labels"]["sensitivity"] == ["low"]
        assert "piighost_mapping" in stored[0].meta

        query_pipe = Pipeline()
        query_pipe.add_component(
            "query_anon", PIIGhostQueryAnonymizer(pipeline=pipeline)
        )
        query_pipe.add_component(
            "retriever", InMemoryBM25Retriever(document_store=store)
        )
        query_pipe.add_component("rehydrator", PIIGhostRehydrator())
        query_pipe.connect("query_anon.query", "retriever.query")
        query_pipe.connect("retriever.documents", "rehydrator.documents")

        result = query_pipe.run({"query_anon": {"query": "Où habite Patrick ?"}})

        docs = result["rehydrator"]["documents"]
        assert len(docs) >= 1
        assert docs[0].content == "Patrick habite à Paris."
