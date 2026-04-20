from piighost.service.models import IndexReport, QueryHit, QueryResult


def test_index_report_defaults():
    r = IndexReport(indexed=3, skipped=1, errors=[], duration_ms=42)
    assert r.indexed == 3
    assert r.skipped == 1
    assert r.errors == []
    assert r.duration_ms == 42


def test_index_report_errors_default():
    r = IndexReport(indexed=0, skipped=0, duration_ms=0)
    assert r.errors == []


def test_query_hit_fields():
    h = QueryHit(doc_id="d1", file_path="/tmp/a.txt", chunk="hello", score=0.9, rank=0)
    assert h.doc_id == "d1"
    assert h.file_path == "/tmp/a.txt"
    assert h.chunk == "hello"
    assert h.score == 0.9
    assert h.rank == 0


def test_query_result_fields():
    r = QueryResult(query="alice", hits=[], k=5)
    assert r.query == "alice"
    assert r.hits == []
    assert r.k == 5
