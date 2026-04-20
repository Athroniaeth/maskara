"""Hybrid retrieval (BM25 + vector) recovers exact-name recall on anonymized docs.

Scenario: a corpus contains three documents, only one mentions 'Alain Dupont'.
A query with the same name must rank that document first. Pure vector search
on anonymized tokens underperforms because <PERSON:hash> is opaque; BM25 on
the same token is exact. EnsembleRetriever combines the two.
"""

import pytest

pytest.importorskip("langchain_core")
pytest.importorskip("langchain_community")
pytest.importorskip("rank_bm25")

pytestmark = [pytest.mark.asyncio, pytest.mark.slow]

from langchain_community.retrievers import EnsembleRetriever  # noqa: E402
from langchain_community.retrievers import BM25Retriever  # noqa: E402
from langchain_core.documents import Document  # noqa: E402

from piighost.anonymizer import Anonymizer  # noqa: E402
from piighost.models import Detection, Span  # noqa: E402
from piighost.pipeline.thread import ThreadAnonymizationPipeline  # noqa: E402
from piighost.placeholder import HashPlaceholderFactory  # noqa: E402
from piighost.integrations.langchain.transformers import (  # noqa: E402
    PIIGhostDocumentAnonymizer,
    PIIGhostQueryAnonymizer,
    PIIGhostRehydrator,
)


class _AlainDetector:
    """Detects 'Alain Dupont' as a single PERSON entity."""

    _NAME = "Alain Dupont"

    async def detect(self, text: str) -> list[Detection]:
        idx = text.find(self._NAME)
        if idx < 0:
            return []
        return [
            Detection(
                text=self._NAME,
                label="PERSON",
                position=Span(start_pos=idx, end_pos=idx + len(self._NAME)),
                confidence=1.0,
            )
        ]


@pytest.fixture
def alain_pipeline() -> ThreadAnonymizationPipeline:
    """Local pipeline that recognises 'Alain Dupont' as a PERSON entity."""
    return ThreadAnonymizationPipeline(
        detector=_AlainDetector(),  # type: ignore[arg-type]
        anonymizer=Anonymizer(HashPlaceholderFactory()),
    )


def _make_embeddings():
    pytest.importorskip("sentence_transformers")
    pytest.importorskip("langchain_huggingface")
    from langchain_huggingface import HuggingFaceEmbeddings

    return HuggingFaceEmbeddings(
        model_name="OrdalieTech/Solon-embeddings-base-0.1",
        encode_kwargs={"normalize_embeddings": True},
        query_encode_kwargs={"prompt": "query: "},
    )


async def test_bm25_plus_vector_recovers_exact_name(alain_pipeline, tmp_path) -> None:
    from langchain_community.vectorstores import LanceDB

    anonymizer = PIIGhostDocumentAnonymizer(pipeline=alain_pipeline)
    query_anon = PIIGhostQueryAnonymizer(pipeline=alain_pipeline)
    rehydrator = PIIGhostRehydrator()
    embeddings = _make_embeddings()

    raw = [
        Document(
            page_content="The legal brief mentions Alain Dupont as plaintiff.",
            metadata={"source": "case-1"},
        ),
        Document(
            page_content="Contract law overview: consideration and offer.",
            metadata={"source": "doctrine-1"},
        ),
        Document(
            page_content="Procedural deadlines for civil suits in France.",
            metadata={"source": "procedure-1"},
        ),
    ]
    anonymized = list(await anonymizer.atransform_documents(raw))
    for d in anonymized:
        assert "Alain" not in d.page_content

    # Vector leg
    db_path = str(tmp_path / "lancedb")
    vstore = LanceDB.from_documents(
        anonymized, embeddings, uri=db_path, table_name="hybrid"
    )
    vector_retriever = vstore.as_retriever(search_kwargs={"k": 3})

    # BM25 leg — exact keyword match on the opaque <PERSON:hash> token.
    bm25_retriever = BM25Retriever.from_documents(anonymized)
    bm25_retriever.k = 3

    ensemble = EnsembleRetriever(
        retrievers=[bm25_retriever, vector_retriever],
        weights=[0.4, 0.6],
    )

    qresult = await query_anon.ainvoke("What does the brief say about Alain Dupont?")
    assert "Alain" not in qresult["query"], "query must be anonymized before retrieval"

    # Confirm token identity: the BM25 leg only works if the same
    # HashPlaceholderFactory produces byte-identical tokens for the
    # document path and the query path.
    anon_token = next(
        (tok for tok in qresult["query"].split() if tok.startswith("<PERSON:")),
        None,
    )
    assert anon_token is not None, "query should contain an anonymized PERSON token"
    assert any(anon_token in d.page_content for d in anonymized), (
        "HashPlaceholderFactory must produce the same token for document and query paths"
    )

    hits = await ensemble.ainvoke(qresult["query"])
    rehydrated = await rehydrator.atransform_documents(hits)

    assert rehydrated, "ensemble should return hits"
    top = rehydrated[0]
    assert "Alain Dupont" in top.page_content, (
        "hybrid retrieval must surface the exact-name document first"
    )
