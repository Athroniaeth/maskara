from piighost.service.models import IndexReport, QueryHit, QueryResult


def test_index_report_defaults():
    r = IndexReport(indexed=3, skipped=1, errors=[], duration_ms=42)
    assert r.indexed == 3
    assert r.skipped == 1
    assert r.errors == []
    assert r.duration_ms == 42


def test_query_hit_fields():
    h = QueryHit(doc_id="d1", file_path="/tmp/a.txt", chunk="hello", score=0.9, rank=0)
    assert h.rank == 0


def test_query_result_fields():
    r = QueryResult(query="alice", hits=[], k=5)
    assert r.hits == []
