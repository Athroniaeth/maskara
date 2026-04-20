from __future__ import annotations

from pathlib import Path


class ChunkStore:
    def __init__(self, lance_path: Path) -> None:
        self._lance_path = lance_path
        self._meta_mode: bool = False
        self._meta: list[dict] = []
        self._db = None
        self._tbl = None

    def upsert_chunks(
        self,
        doc_id: str,
        file_path: str,
        texts: list[str],
        vectors: list[list[float]],
    ) -> None:
        has_vectors = any(v for v in vectors)
        if not has_vectors:
            self._meta_mode = True
            self._meta = [r for r in self._meta if r["doc_id"] != doc_id]
            for i, text in enumerate(texts):
                self._meta.append(
                    {
                        "doc_id": doc_id,
                        "file_path": file_path,
                        "chunk_id": f"{doc_id}:{i}",
                        "chunk": text,
                    }
                )
            return

        import lancedb
        import pyarrow as pa

        self._lance_path.mkdir(parents=True, exist_ok=True)
        if self._db is None:
            self._db = lancedb.connect(str(self._lance_path))

        dim = len(vectors[0])
        records = [
            {
                "doc_id": doc_id,
                "file_path": file_path,
                "chunk_id": f"{doc_id}:{i}",
                "chunk": text,
                "vector": vec,
            }
            for i, (text, vec) in enumerate(zip(texts, vectors))
        ]
        table_name = "chunks"
        if table_name in self._db.list_tables().tables:
            tbl = self._db.open_table(table_name)
            tbl.delete(f"doc_id = '{doc_id}'")
            tbl.add(records)
        else:
            schema = pa.schema(
                [
                    pa.field("doc_id", pa.string()),
                    pa.field("file_path", pa.string()),
                    pa.field("chunk_id", pa.string()),
                    pa.field("chunk", pa.string()),
                    pa.field("vector", pa.list_(pa.float32(), dim)),
                ]
            )
            self._tbl = self._db.create_table(table_name, data=records, schema=schema)

    def all_records(self) -> list[dict]:
        if self._meta_mode:
            return list(self._meta)
        if self._db is None:
            return []
        table_name = "chunks"
        if table_name not in self._db.list_tables().tables:
            return []
        tbl = self._db.open_table(table_name)
        rows = tbl.to_arrow().to_pylist()
        return [{k: v for k, v in r.items() if k != "vector"} for r in rows]

    def vector_search(self, embedding: list[float], *, k: int = 5) -> list[dict]:
        if self._meta_mode or not embedding:
            return []
        if self._db is None:
            return []
        table_name = "chunks"
        if table_name not in self._db.list_tables().tables:
            return []
        tbl = self._db.open_table(table_name)
        results = tbl.search(embedding).limit(k).to_list()
        return [{k: v for k, v in r.items() if k != "vector"} for r in results]
