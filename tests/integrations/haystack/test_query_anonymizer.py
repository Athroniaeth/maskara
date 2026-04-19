"""Tests for ``PIIGhostQueryAnonymizer``."""

import pytest
from haystack import Document

from piighost.integrations.haystack.documents import (
    PIIGhostDocumentAnonymizer,
    PIIGhostQueryAnonymizer,
)

pytestmark = pytest.mark.asyncio


class TestQueryAnonymize:
    """Anonymizes a query string and returns it with detected entities."""

    async def test_anonymizes_query_content(self, pipeline) -> None:
        component = PIIGhostQueryAnonymizer(pipeline=pipeline)
        out = await component.run_async(query="Où habite Patrick ?")
        assert "Patrick" not in out["query"]
        assert "<PERSON:" in out["query"]

    async def test_returns_entities(self, pipeline) -> None:
        component = PIIGhostQueryAnonymizer(pipeline=pipeline)
        out = await component.run_async(query="Patrick habite à Paris.")
        assert len(out["entities"]) == 2
        labels = {e.label for e in out["entities"]}
        assert labels == {"PERSON", "LOCATION"}

    async def test_query_hash_matches_document_hash(self, pipeline) -> None:
        """The token for ``Patrick`` in a query matches the one in a doc."""
        doc_component = PIIGhostDocumentAnonymizer(pipeline=pipeline)
        query_component = PIIGhostQueryAnonymizer(pipeline=pipeline)

        doc_out = await doc_component.run_async(
            documents=[Document(content="Patrick habite à Paris.")]
        )
        query_out = await query_component.run_async(query="Où est Patrick ?")

        doc_content = doc_out["documents"][0].content
        query_content = query_out["query"]
        doc_token_start = doc_content.index("<PERSON:")
        doc_token = doc_content[
            doc_token_start : doc_content.index(">", doc_token_start) + 1
        ]
        query_token_start = query_content.index("<PERSON:")
        query_token = query_content[
            query_token_start : query_content.index(">", query_token_start) + 1
        ]
        assert doc_token == query_token

    async def test_scope_defaults_to_query(self, pipeline) -> None:
        component = PIIGhostQueryAnonymizer(pipeline=pipeline)
        out = await component.run_async(query="Patrick")
        assert "<PERSON:" in out["query"]

    def test_sync_run(self, pipeline) -> None:
        component = PIIGhostQueryAnonymizer(pipeline=pipeline)
        out = component.run(query="Où habite Patrick ?")
        assert "<PERSON:" in out["query"]
