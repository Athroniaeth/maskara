"""Matrix test for lenient-vs-strict error behaviour across components."""

import pytest
from haystack import Document

from piighost.exceptions import RehydrationError
from piighost.integrations.haystack import (
    PIIGhostDocumentAnonymizer,
    PIIGhostDocumentClassifier,
    PIIGhostQueryAnonymizer,
    PIIGhostRehydrator,
)

pytestmark = pytest.mark.asyncio


class _BrokenDetector:
    async def detect(self, text):
        raise RuntimeError("detector down")


class _BrokenClassifier:
    async def classify(self, text, schemas):
        raise RuntimeError("classifier down")


@pytest.fixture
def broken_pipeline(pipeline):
    """Patch the fixture pipeline to use a broken detector."""
    pipeline._detector = _BrokenDetector()
    return pipeline


class TestDocumentAnonymizerErrors:
    async def test_lenient_writes_error_meta(self, broken_pipeline) -> None:
        component = PIIGhostDocumentAnonymizer(pipeline=broken_pipeline)
        doc = Document(content="Patrick")
        out = await component.run_async(documents=[doc])
        assert "piighost_error" in out["documents"][0].meta
        assert "piighost_mapping" not in out["documents"][0].meta

    async def test_strict_reraises(self, broken_pipeline) -> None:
        component = PIIGhostDocumentAnonymizer(pipeline=broken_pipeline, strict=True)
        doc = Document(content="Patrick")
        with pytest.raises(RuntimeError, match="detector down"):
            await component.run_async(documents=[doc])


class TestQueryAnonymizerStrictAlways:
    """QueryAnonymizer is always strict — PII-leak risk."""

    async def test_raises_on_error(self, broken_pipeline) -> None:
        component = PIIGhostQueryAnonymizer(pipeline=broken_pipeline)
        with pytest.raises(RuntimeError, match="detector down"):
            await component.run_async(query="Patrick")


class TestClassifierErrors:
    async def test_lenient_writes_classifier_error_meta(self) -> None:
        component = PIIGhostDocumentClassifier(
            classifier=_BrokenClassifier(),
            schemas={"x": {"labels": ["a"], "multi_label": False}},
        )
        doc = Document(content="hello")
        out = await component.run_async(documents=[doc])
        assert "piighost_classifier_error" in out["documents"][0].meta

    async def test_strict_reraises(self) -> None:
        component = PIIGhostDocumentClassifier(
            classifier=_BrokenClassifier(),
            schemas={"x": {"labels": ["a"], "multi_label": False}},
            strict=True,
        )
        doc = Document(content="hello")
        with pytest.raises(RuntimeError, match="classifier down"):
            await component.run_async(documents=[doc])


class TestRehydratorFailFlag:
    async def test_lenient_returns_unchanged(self) -> None:
        component = PIIGhostRehydrator()
        doc = Document(content="<PERSON:abc>")
        out = await component.run_async(documents=[doc])
        assert out["documents"][0].content == "<PERSON:abc>"

    async def test_strict_raises(self) -> None:
        component = PIIGhostRehydrator(fail_on_missing_mapping=True)
        doc = Document(content="<PERSON:abc>")
        with pytest.raises(RehydrationError):
            await component.run_async(documents=[doc])
