"""The stateful core that CLI, daemon, and MCP all wrap."""

from __future__ import annotations

import asyncio
import hashlib
import re
from pathlib import Path
from typing import Protocol

from piighost.anonymizer import Anonymizer
from piighost.exceptions import PIISafetyViolation
from piighost.models import Detection, Entity
from piighost.pipeline.base import AnonymizationPipeline
from piighost.placeholder import HashPlaceholderFactory
from piighost.service.config import ServiceConfig
from piighost.service.errors import AnonymizationFailed
from piighost.service.models import (
    AnonymizeResult,
    DetectionResult,
    EntityRef,
    RehydrateResult,
    VaultEntryModel,
    VaultPage,
    VaultStatsModel,
)
from piighost.vault import AuditLogger, Vault, VaultEntry

_TOKEN_RE = re.compile(r"<[A-Z_]+:[0-9a-f]{8}>")


class _Detector(Protocol):
    async def detect(self, text: str) -> list[Detection]: ...


class PIIGhostService:
    """Stateful service. One instance per vault directory."""

    def __init__(
        self,
        vault_dir: Path,
        config: ServiceConfig,
        vault: Vault,
        audit: AuditLogger,
        detector: _Detector,
        ph_factory: HashPlaceholderFactory,
    ) -> None:
        self._vault_dir = vault_dir
        self._config = config
        self._vault = vault
        self._audit = audit
        self._detector = detector
        self._ph = ph_factory
        self._pipeline = AnonymizationPipeline(
            detector=detector,
            anonymizer=Anonymizer(ph_factory),
        )
        self._write_lock = asyncio.Lock()
        from piighost.indexer.embedder import build_embedder
        from piighost.indexer.store import ChunkStore
        from piighost.indexer.retriever import BM25Index

        self._embedder = build_embedder(config.embedder)
        self._chunk_store = ChunkStore(vault_dir / ".piighost" / "lance")
        self._bm25 = BM25Index(vault_dir / ".piighost" / "bm25.pkl")
        self._bm25.load()

    @classmethod
    async def create(
        cls,
        *,
        vault_dir: Path,
        config: ServiceConfig | None = None,
        detector: _Detector | None = None,
    ) -> "PIIGhostService":
        config = config or ServiceConfig.default()
        vault = Vault.open(vault_dir / "vault.db")
        audit = AuditLogger(vault_dir / "audit.log")
        if detector is None:
            detector = await _build_default_detector(config)
        return cls(
            vault_dir=vault_dir,
            config=config,
            vault=vault,
            audit=audit,
            detector=detector,
            ph_factory=HashPlaceholderFactory(),
        )

    # ---- core ops ----

    def _token_for(self, entity: Entity) -> str:
        """Recompute the deterministic hash token for an entity."""
        return self._ph.create([entity])[entity]

    async def anonymize(
        self, text: str, *, doc_id: str | None = None
    ) -> AnonymizeResult:
        doc_id = (
            doc_id
            or f"anon-{hashlib.sha256(text.encode('utf-8')).hexdigest()[:10]}"
        )
        try:
            anonymized, entities = await self._pipeline.anonymize(text)
        except Exception as exc:
            raise AnonymizationFailed(
                doc_id=doc_id, stage="pipeline", entity_count=0
            ) from exc
        if not entities:
            return AnonymizeResult(
                doc_id=doc_id,
                anonymized=text,
                entities=[],
                stats={"chars_in": len(text), "chars_out": len(text)},
            )

        async with self._write_lock:
            for ent in entities:
                token = self._token_for(ent)
                confidence = max(
                    (d.confidence for d in ent.detections if d.confidence is not None),
                    default=None,
                )
                self._vault.upsert_entity(
                    token=token,
                    original=ent.detections[0].text,
                    label=ent.label,
                    confidence=confidence,
                )
                for det in ent.detections:
                    self._vault.link_doc_entity(
                        doc_id=doc_id,
                        token=token,
                        start_pos=det.position.start_pos,
                        end_pos=det.position.end_pos,
                    )

        refs = [
            EntityRef(
                token=self._token_for(ent),
                label=ent.label,
                count=len(ent.detections),
            )
            for ent in entities
        ]
        return AnonymizeResult(
            doc_id=doc_id,
            anonymized=anonymized,
            entities=refs,
            stats={"chars_in": len(text), "chars_out": len(anonymized)},
        )

    async def rehydrate(
        self, text: str, *, strict: bool | None = None
    ) -> RehydrateResult:
        strict = self._config.safety.strict_rehydrate if strict is None else strict
        tokens = _TOKEN_RE.findall(text)
        unknown: list[str] = []
        result = text
        # longest tokens first avoids prefix-clash
        for tok in sorted(set(tokens), key=len, reverse=True):
            entry = self._vault.get_by_token(tok)
            if entry is None:
                unknown.append(tok)
                continue
            result = result.replace(tok, entry.original)
            self._audit.record(op="rehydrate", token=tok, caller_kind="service")
        if unknown and strict:
            raise PIISafetyViolation(
                f"rehydrate: {len(unknown)} unknown tokens in strict mode"
            )
        return RehydrateResult(text=result, unknown_tokens=unknown)

    async def detect(self, text: str) -> list[DetectionResult]:
        dets = await self._detector.detect(text)
        return [
            DetectionResult(
                text=d.text,
                label=d.label,
                start=d.position.start_pos,
                end=d.position.end_pos,
                confidence=d.confidence,
            )
            for d in dets
        ]

    async def index_path(
        self, path: Path, *, recursive: bool = True
    ) -> "IndexReport":
        import time
        from piighost.indexer.chunker import chunk_text
        from piighost.indexer.ingestor import list_document_paths, extract_text
        from piighost.service.models import IndexReport

        start = time.monotonic()
        paths = await list_document_paths(path, recursive=recursive)
        indexed = 0
        skipped = 0
        errors: list[str] = []

        for p in paths:
            try:
                text = await extract_text(p)
                if text is None:
                    skipped += 1
                    continue
                result = await self.anonymize(text, doc_id=str(p))
                anon_text = result.anonymized
                chunks = chunk_text(anon_text)
                if not chunks:
                    skipped += 1
                    continue
                vectors = await self._embedder.embed(chunks)
                self._chunk_store.upsert_chunks(str(p), str(p), chunks, vectors)
                indexed += 1
            except Exception as exc:
                errors.append(f"{p}: {exc}")

        all_records = self._chunk_store.all_records()
        if all_records:
            self._bm25.rebuild(all_records)

        duration_ms = int((time.monotonic() - start) * 1000)
        return IndexReport(
            indexed=indexed,
            skipped=skipped,
            errors=errors,
            duration_ms=duration_ms,
        )

    async def query(self, text: str, *, k: int = 5) -> "QueryResult":
        from piighost.indexer.retriever import reciprocal_rank_fusion
        from piighost.service.models import QueryHit, QueryResult

        anon_result = await self.anonymize(text)
        anon_query = anon_result.anonymized

        bm25_hits = self._bm25.search(anon_query, k=k * 2)
        query_vecs = await self._embedder.embed([anon_query])
        vec_hits_raw = self._chunk_store.vector_search(query_vecs[0], k=k * 2)
        vector_hits = [(r["chunk_id"], r.get("_distance", 0.0)) for r in vec_hits_raw]

        fused = reciprocal_rank_fusion(bm25_hits, vector_hits, rrf_k=60)[:k]

        all_records = {r["chunk_id"]: r for r in self._chunk_store.all_records()}
        hits: list[QueryHit] = []
        for rank, (chunk_id, score) in enumerate(fused):
            rec = all_records.get(chunk_id)
            if rec is None:
                continue
            hits.append(
                QueryHit(
                    doc_id=rec["doc_id"],
                    file_path=rec["file_path"],
                    chunk=rec["chunk"],
                    score=score,
                    rank=rank,
                )
            )

        return QueryResult(query=text, hits=hits, k=k)

    # ---- vault ops ----

    async def vault_list(
        self,
        *,
        label: str | None = None,
        limit: int = 100,
        offset: int = 0,
        reveal: bool = False,
    ) -> VaultPage:
        rows = self._vault.list_entities(label=label, limit=limit, offset=offset)
        entries = [self._to_entry_model(r, reveal=reveal) for r in rows]
        return VaultPage(entries=entries)

    async def vault_show(
        self, token: str, *, reveal: bool = False
    ) -> VaultEntryModel | None:
        row = self._vault.get_by_token(token)
        if row is None:
            return None
        if reveal:
            self._audit.record(
                op="vault_show_reveal", token=token, caller_kind="service"
            )
        return self._to_entry_model(row, reveal=reveal)

    async def vault_stats(self) -> VaultStatsModel:
        s = self._vault.stats()
        return VaultStatsModel(total=s.total, by_label=s.by_label)

    async def vault_search(
        self, query: str, *, reveal: bool = False, limit: int = 100
    ) -> list[VaultEntryModel]:
        entries = self._vault.search_entities(query, limit=limit)
        return [self._to_entry_model(e, reveal=reveal) for e in entries]

    # ---- lifecycle ----

    async def flush(self) -> None:
        # autocommit mode — nothing to flush. Reserved for future buffered writes.
        pass

    async def close(self) -> None:
        self._vault.close()

    # ---- helpers ----

    @staticmethod
    def _mask(original: str) -> str:
        if len(original) <= 2:
            return "*" * len(original)
        return original[0] + "*" * (len(original) - 2) + original[-1]

    def _to_entry_model(self, v: VaultEntry, *, reveal: bool) -> VaultEntryModel:
        return VaultEntryModel(
            token=v.token,
            label=v.label,
            original=v.original if reveal else None,
            original_masked=self._mask(v.original),
            confidence=v.confidence,
            first_seen_at=v.first_seen_at,
            last_seen_at=v.last_seen_at,
            occurrence_count=v.occurrence_count,
        )


async def _build_default_detector(config: ServiceConfig) -> _Detector:
    """Load a detector based on config. Deferred import keeps cold start lean."""
    import os

    if os.environ.get("PIIGHOST_DETECTOR") == "stub":
        return _StubDetector()
    if config.detector.backend == "gliner2":
        from gliner2 import GLiNER2

        from piighost.detector.gliner2 import Gliner2Detector

        model = GLiNER2.from_pretrained(config.detector.gliner2_model)
        return Gliner2Detector(model=model, labels=config.detector.labels)
    raise NotImplementedError(
        f"detector backend {config.detector.backend!r} not shipped yet"
    )


class _StubDetector:
    """Deterministic stub used only when ``PIIGHOST_DETECTOR=stub`` (tests/dev)."""

    async def detect(self, text: str) -> list[Detection]:
        from piighost.models import Detection, Span

        out: list[Detection] = []
        for needle, label in (("Alice", "PERSON"), ("Paris", "LOC")):
            idx = text.find(needle)
            if idx >= 0:
                out.append(
                    Detection(
                        text=needle,
                        label=label,
                        position=Span(start_pos=idx, end_pos=idx + len(needle)),
                        confidence=0.99,
                    )
                )
        return out
