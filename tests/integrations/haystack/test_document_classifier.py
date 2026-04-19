"""Tests for ``PIIGhostDocumentClassifier``."""

import pytest
from haystack import Document

from piighost.classifier import ExactMatchClassifier
from piighost.integrations.haystack.documents import PIIGhostDocumentClassifier

pytestmark = pytest.mark.asyncio


@pytest.fixture
def classifier() -> ExactMatchClassifier:
    return ExactMatchClassifier(
        results={
            "Patient records for John": {
                "sensitivity": ["high"],
                "gdpr_category": ["health"],
                "language": ["en"],
            },
            "Recette de crêpes": {
                "sensitivity": ["low"],
                "gdpr_category": [],
                "language": ["fr"],
            },
        }
    )


class TestLabelsWritten:
    """Classifier populates ``meta[meta_key]`` with a structured dict."""

    async def test_writes_labels_as_dict(self, classifier) -> None:
        schemas = {
            "sensitivity": {"labels": ["low", "medium", "high"], "multi_label": False},
            "gdpr_category": {
                "labels": ["health", "financial", "none"],
                "multi_label": True,
            },
            "language": {"labels": ["en", "fr"], "multi_label": False},
        }
        component = PIIGhostDocumentClassifier(classifier=classifier, schemas=schemas)
        doc = Document(content="Patient records for John")
        out = await component.run_async(documents=[doc])
        labels = out["documents"][0].meta["labels"]
        assert labels == {
            "sensitivity": ["high"],
            "gdpr_category": ["health"],
            "language": ["en"],
        }

    async def test_content_not_modified(self, classifier) -> None:
        schemas = {"sensitivity": {"labels": ["low", "high"], "multi_label": False}}
        component = PIIGhostDocumentClassifier(classifier=classifier, schemas=schemas)
        doc = Document(content="Patient records for John")
        out = await component.run_async(documents=[doc])
        assert out["documents"][0].content == "Patient records for John"


class TestErrorHandling:
    """Lenient by default; strict re-raises."""

    async def test_lenient_error_writes_meta_error(self) -> None:
        class Boom:
            async def classify(self, text, schemas):
                raise RuntimeError("model oom")

        component = PIIGhostDocumentClassifier(
            classifier=Boom(),
            schemas={"x": {"labels": ["a"], "multi_label": False}},
        )
        doc = Document(content="hello")
        out = await component.run_async(documents=[doc])
        assert "piighost_classifier_error" in out["documents"][0].meta
        assert "labels" not in out["documents"][0].meta

    async def test_strict_reraises(self) -> None:
        class Boom:
            async def classify(self, text, schemas):
                raise RuntimeError("model oom")

        component = PIIGhostDocumentClassifier(
            classifier=Boom(),
            schemas={"x": {"labels": ["a"], "multi_label": False}},
            strict=True,
        )
        doc = Document(content="hello")
        with pytest.raises(RuntimeError, match="oom"):
            await component.run_async(documents=[doc])


class TestSyncRun:
    """Sync wrapper works."""

    def test_sync_run(self, classifier) -> None:
        schemas = {"sensitivity": {"labels": ["low", "high"], "multi_label": False}}
        component = PIIGhostDocumentClassifier(classifier=classifier, schemas=schemas)
        doc = Document(content="Patient records for John")
        out = component.run(documents=[doc])
        assert out["documents"][0].meta["labels"]["sensitivity"] == ["high"]
