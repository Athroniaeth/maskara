"""Tests for ``ExactMatchClassifier`` (test double for GLiNER2 classification)."""

import pytest

from piighost.classifier import ExactMatchClassifier
from piighost.classifier.base import ClassificationSchema

pytestmark = pytest.mark.asyncio


class TestExactMatchClassifier:
    """Hard-coded classifier used in tests to avoid loading GLiNER2."""

    async def test_returns_configured_labels_for_known_text(self) -> None:
        classifier = ExactMatchClassifier(
            results={
                "hello world": {"sentiment": ["positive"], "language": ["en"]},
            }
        )
        schemas: dict[str, ClassificationSchema] = {
            "sentiment": {"labels": ["positive", "negative"], "multi_label": False},
            "language": {"labels": ["en", "fr"], "multi_label": False},
        }
        result = await classifier.classify("hello world", schemas)
        assert result == {"sentiment": ["positive"], "language": ["en"]}

    async def test_returns_empty_lists_for_unknown_text(self) -> None:
        classifier = ExactMatchClassifier(results={})
        schemas: dict[str, ClassificationSchema] = {
            "sentiment": {"labels": ["positive", "negative"], "multi_label": False},
        }
        result = await classifier.classify("unknown text", schemas)
        assert result == {"sentiment": []}

    async def test_returns_empty_dict_for_empty_schemas(self) -> None:
        classifier = ExactMatchClassifier(
            results={"hello": {"sentiment": ["positive"]}}
        )
        result = await classifier.classify("hello", {})
        assert result == {}

    async def test_multi_label_returns_multiple_labels(self) -> None:
        classifier = ExactMatchClassifier(
            results={
                "great camera and battery": {"aspects": ["camera", "battery"]},
            }
        )
        schemas: dict[str, ClassificationSchema] = {
            "aspects": {
                "labels": ["camera", "battery", "screen"],
                "multi_label": True,
            },
        }
        result = await classifier.classify("great camera and battery", schemas)
        assert result == {"aspects": ["camera", "battery"]}
