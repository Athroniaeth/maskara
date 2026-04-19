"""Tests for ``PIIGhostDocumentAnonymizer``."""

import json

import pytest
from haystack import Document

from piighost.anonymizer import Anonymizer
from piighost.detector import ExactMatchDetector
from piighost.integrations.haystack.documents import PIIGhostDocumentAnonymizer
from piighost.linker.entity import ExactEntityLinker
from piighost.pipeline.thread import ThreadAnonymizationPipeline
from piighost.placeholder import CounterPlaceholderFactory
from piighost.resolver.entity import MergeEntityConflictResolver
from piighost.resolver.span import ConfidenceSpanConflictResolver

pytestmark = pytest.mark.asyncio


class TestAnonymize:
    """Anonymization replaces content and stores a JSON mapping in meta."""

    async def test_anonymizes_content(self, pipeline) -> None:
        component = PIIGhostDocumentAnonymizer(pipeline=pipeline)
        doc = Document(content="Patrick habite à Paris.")
        out = await component.run_async(documents=[doc])
        anonymized = out["documents"][0].content
        assert "Patrick" not in anonymized
        assert "Paris" not in anonymized
        assert "<PERSON:" in anonymized
        assert "<LOCATION:" in anonymized

    async def test_stores_mapping_in_meta(self, pipeline) -> None:
        component = PIIGhostDocumentAnonymizer(pipeline=pipeline)
        doc = Document(content="Patrick habite à Paris.")
        out = await component.run_async(documents=[doc])
        mapping_raw = out["documents"][0].meta["piighost_mapping"]
        assert isinstance(mapping_raw, str)
        mapping = json.loads(mapping_raw)
        originals = {m["original"] for m in mapping}
        labels = {m["label"] for m in mapping}
        assert originals == {"Patrick", "Paris"}
        assert labels == {"PERSON", "LOCATION"}

    async def test_empty_content_passes_through(self, pipeline) -> None:
        component = PIIGhostDocumentAnonymizer(pipeline=pipeline)
        doc = Document(content="")
        out = await component.run_async(documents=[doc])
        assert out["documents"][0].content == ""
        assert "piighost_mapping" not in out["documents"][0].meta

    async def test_none_content_passes_through(self, pipeline) -> None:
        component = PIIGhostDocumentAnonymizer(pipeline=pipeline)
        doc = Document(content=None)
        out = await component.run_async(documents=[doc])
        assert out["documents"][0].content is None


class TestProfile:
    """The ``populate_profile`` flag adds a JSON profile summary to meta."""

    async def test_profile_contains_entity_flags_and_counts(self, pipeline) -> None:
        component = PIIGhostDocumentAnonymizer(pipeline=pipeline, populate_profile=True)
        doc = Document(content="Patrick habite à Paris.")
        out = await component.run_async(documents=[doc])
        profile_raw = out["documents"][0].meta["piighost_profile"]
        profile = json.loads(profile_raw)
        assert profile["has_person"] is True
        assert profile["n_entities"] == 2
        assert set(profile["labels"]) == {"PERSON", "LOCATION"}

    async def test_profile_absent_when_flag_off(self, pipeline) -> None:
        component = PIIGhostDocumentAnonymizer(
            pipeline=pipeline, populate_profile=False
        )
        doc = Document(content="Patrick habite à Paris.")
        out = await component.run_async(documents=[doc])
        assert "piighost_profile" not in out["documents"][0].meta


class TestPlaceholderFactoryCheck:
    """Counter-based factory is rejected unless opt-in."""

    def test_counter_factory_raises_value_error(self) -> None:
        pipeline = ThreadAnonymizationPipeline(
            detector=ExactMatchDetector([("Patrick", "PERSON")]),
            span_resolver=ConfidenceSpanConflictResolver(),
            entity_linker=ExactEntityLinker(),
            entity_resolver=MergeEntityConflictResolver(),
            anonymizer=Anonymizer(CounterPlaceholderFactory()),
        )
        with pytest.raises(ValueError, match="HashPlaceholderFactory"):
            PIIGhostDocumentAnonymizer(pipeline=pipeline)

    def test_counter_factory_allowed_with_escape_hatch(self) -> None:
        pipeline = ThreadAnonymizationPipeline(
            detector=ExactMatchDetector([("Patrick", "PERSON")]),
            span_resolver=ConfidenceSpanConflictResolver(),
            entity_linker=ExactEntityLinker(),
            entity_resolver=MergeEntityConflictResolver(),
            anonymizer=Anonymizer(CounterPlaceholderFactory()),
        )
        PIIGhostDocumentAnonymizer(pipeline=pipeline, allow_non_stable_tokens=True)


class TestSyncRun:
    """The sync ``run`` path works outside a running loop."""

    def test_sync_run_outside_loop(self, pipeline) -> None:
        component = PIIGhostDocumentAnonymizer(pipeline=pipeline)
        doc = Document(content="Patrick habite à Paris.")
        out = component.run(documents=[doc])
        assert "<PERSON:" in out["documents"][0].content
