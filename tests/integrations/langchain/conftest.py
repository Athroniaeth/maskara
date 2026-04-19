"""Fixtures shared by every LangChain integration test module."""

from __future__ import annotations

import pytest

from piighost.anonymizer import Anonymizer
from piighost.classifier.base import AnyClassifier, ClassificationSchema
from piighost.detector.base import AnyDetector
from piighost.models import Detection, Span
from piighost.pipeline.thread import ThreadAnonymizationPipeline
from piighost.placeholder import HashPlaceholderFactory


class _StubDetector:
    """Always returns a single PERSON entity covering the first occurrence of 'Alice'."""

    async def detect(self, text: str) -> list[Detection]:
        idx = text.find("Alice")
        if idx < 0:
            return []
        return [
            Detection(
                text="Alice",
                label="PERSON",
                position=Span(start_pos=idx, end_pos=idx + len("Alice")),
                confidence=1.0,
            )
        ]


class _StubClassifier:
    """Returns fixed labels per schema."""

    def __init__(self, result: dict[str, list[str]]) -> None:
        self._result = result

    async def classify(
        self,
        text: str,
        schemas: dict[str, ClassificationSchema],
    ) -> dict[str, list[str]]:
        return {name: self._result.get(name, []) for name in schemas}


@pytest.fixture
def pipeline() -> ThreadAnonymizationPipeline:
    detector: AnyDetector = _StubDetector()  # type: ignore[assignment]  # _StubDetector satisfies AnyDetector structurally
    return ThreadAnonymizationPipeline(
        detector=detector,
        anonymizer=Anonymizer(HashPlaceholderFactory()),
    )


@pytest.fixture
def stub_classifier() -> AnyClassifier:
    return _StubClassifier({"gdpr_category": ["none"]})  # type: ignore[return-value]  # _StubClassifier satisfies AnyClassifier structurally


@pytest.fixture
def gdpr_schemas() -> dict[str, ClassificationSchema]:
    from piighost.presets import PRESET_GDPR

    return PRESET_GDPR
