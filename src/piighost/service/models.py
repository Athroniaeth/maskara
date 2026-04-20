"""Pydantic result types for service-layer operations."""

from __future__ import annotations

from pydantic import BaseModel, Field


class EntityRef(BaseModel):
    token: str
    label: str
    count: int = 1


class AnonymizeResult(BaseModel):
    doc_id: str
    anonymized: str
    entities: list[EntityRef] = Field(default_factory=list)
    stats: dict[str, int] = Field(default_factory=dict)


class RehydrateResult(BaseModel):
    text: str
    unknown_tokens: list[str] = Field(default_factory=list)


class DetectionResult(BaseModel):
    text: str
    label: str
    start: int
    end: int
    confidence: float | None = None


class VaultEntryModel(BaseModel):
    token: str
    label: str
    original: str | None = None
    original_masked: str | None = None
    confidence: float | None = None
    first_seen_at: int
    last_seen_at: int
    occurrence_count: int


class VaultStatsModel(BaseModel):
    total: int
    by_label: dict[str, int]


class VaultPage(BaseModel):
    entries: list[VaultEntryModel]
    next_cursor: str | None = None


class IndexReport(BaseModel):
    indexed: int
    skipped: int
    errors: list[str] = Field(default_factory=list)
    duration_ms: int


class QueryHit(BaseModel):
    doc_id: str
    file_path: str
    chunk: str
    score: float
    rank: int


class QueryResult(BaseModel):
    query: str
    hits: list[QueryHit]
    k: int
