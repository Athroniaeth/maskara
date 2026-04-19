"""Tests for ``PIIGhostRehydrator``."""

import json

import pytest
from haystack import Document

from piighost.exceptions import RehydrationError
from piighost.integrations.haystack.documents import (
    PIIGhostDocumentAnonymizer,
    PIIGhostRehydrator,
)

pytestmark = pytest.mark.asyncio


def _mapping(items: list[dict[str, str]]) -> str:
    return json.dumps(items)


class TestRoundtrip:
    """Anonymize → Rehydrate restores the original content."""

    async def test_full_roundtrip(self, pipeline) -> None:
        anonymizer = PIIGhostDocumentAnonymizer(pipeline=pipeline)
        rehydrator = PIIGhostRehydrator()

        doc = Document(content="Patrick habite à Paris.")
        anon_out = await anonymizer.run_async(documents=[doc])
        rehydrated_out = await rehydrator.run_async(documents=anon_out["documents"])

        assert rehydrated_out["documents"][0].content == "Patrick habite à Paris."


class TestLenient:
    """Default lenient behaviour: missing mapping leaves content unchanged."""

    async def test_missing_mapping_passes_through(self) -> None:
        rehydrator = PIIGhostRehydrator()
        doc = Document(content="<PERSON:abc> habite à <LOCATION:def>.")
        out = await rehydrator.run_async(documents=[doc])
        assert out["documents"][0].content == "<PERSON:abc> habite à <LOCATION:def>."

    async def test_malformed_mapping_passes_through(self) -> None:
        rehydrator = PIIGhostRehydrator()
        doc = Document(
            content="<PERSON:abc>",
            meta={"piighost_mapping": "not valid json"},
        )
        out = await rehydrator.run_async(documents=[doc])
        assert out["documents"][0].content == "<PERSON:abc>"


class TestStrict:
    """``fail_on_missing_mapping=True`` raises RehydrationError."""

    async def test_strict_missing_mapping_raises(self) -> None:
        rehydrator = PIIGhostRehydrator(fail_on_missing_mapping=True)
        doc = Document(content="<PERSON:abc>")
        with pytest.raises(RehydrationError):
            await rehydrator.run_async(documents=[doc])

    async def test_strict_malformed_mapping_raises(self) -> None:
        rehydrator = PIIGhostRehydrator(fail_on_missing_mapping=True)
        doc = Document(
            content="<PERSON:abc>",
            meta={"piighost_mapping": "{bad json"},
        )
        with pytest.raises(RehydrationError):
            await rehydrator.run_async(documents=[doc])


class TestLongestFirst:
    """Replacement is longest-first to avoid partial-token collisions."""

    async def test_longest_token_replaced_first(self) -> None:
        rehydrator = PIIGhostRehydrator()
        mapping = _mapping(
            [
                {"token": "<X>", "original": "short", "label": "X"},
                {"token": "<X_EXTENDED>", "original": "longer", "label": "X"},
            ]
        )
        doc = Document(
            content="<X_EXTENDED> et <X>",
            meta={"piighost_mapping": mapping},
        )
        out = await rehydrator.run_async(documents=[doc])
        assert out["documents"][0].content == "longer et short"


class TestSyncRun:
    """Sync ``run()`` roundtrip."""

    def test_sync_roundtrip(self, pipeline) -> None:
        anonymizer = PIIGhostDocumentAnonymizer(pipeline=pipeline)
        rehydrator = PIIGhostRehydrator()

        doc = Document(content="Patrick habite à Paris.")
        anon_out = anonymizer.run(documents=[doc])
        rehyd_out = rehydrator.run(documents=anon_out["documents"])
        assert rehyd_out["documents"][0].content == "Patrick habite à Paris."
