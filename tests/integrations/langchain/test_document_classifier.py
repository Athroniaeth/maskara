"""PIIGhostDocumentClassifier writes structured labels to metadata."""

import pytest

pytest.importorskip("langchain_core")

from langchain_core.documents import Document  # noqa: E402

from piighost.integrations.langchain.transformers import (  # noqa: E402
    PIIGhostDocumentClassifier,
)


@pytest.mark.asyncio
async def test_atransform_writes_labels_dict(stub_classifier, gdpr_schemas) -> None:
    classifier = PIIGhostDocumentClassifier(
        classifier=stub_classifier, schemas=gdpr_schemas
    )
    docs = [Document(page_content="Health record", metadata={"source": "d1"})]

    out = await classifier.atransform_documents(docs)

    assert out[0].metadata["labels"] == {"gdpr_category": ["none"]}


def test_sync_path(stub_classifier, gdpr_schemas) -> None:
    classifier = PIIGhostDocumentClassifier(
        classifier=stub_classifier, schemas=gdpr_schemas
    )
    docs = [Document(page_content="Health record", metadata={"source": "d2"})]

    out = classifier.transform_documents(docs)

    assert out[0].metadata["labels"]["gdpr_category"] == ["none"]


def test_empty_content_skipped(stub_classifier, gdpr_schemas) -> None:
    classifier = PIIGhostDocumentClassifier(
        classifier=stub_classifier, schemas=gdpr_schemas
    )
    docs = [Document(page_content="  ", metadata={"source": "d3"})]

    out = classifier.transform_documents(docs)

    assert "labels" not in out[0].metadata
