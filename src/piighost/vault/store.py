"""Synchronous SQLite-backed vault store.

All writes serialize on the single connection. WAL mode allows concurrent
readers (used by the daemon's query endpoints).
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from piighost.vault.schema import ensure_schema


@dataclass(frozen=True)
class VaultEntry:
    token: str
    original: str
    label: str
    confidence: float | None
    first_seen_at: int
    last_seen_at: int
    occurrence_count: int


@dataclass(frozen=True)
class VaultStats:
    total: int
    by_label: dict[str, int]


class Vault:
    """Thread-safe only for single-connection use. One `Vault` per process."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    @classmethod
    def open(cls, db_path: Path) -> "Vault":
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path, isolation_level=None)  # autocommit
        conn.row_factory = sqlite3.Row
        ensure_schema(conn)
        return cls(conn)

    def close(self) -> None:
        self._conn.close()

    # ---- mutations ----

    def upsert_entity(
        self,
        token: str,
        original: str,
        label: str,
        confidence: float | None,
    ) -> None:
        now = int(time.time())
        self._conn.execute(
            """
            INSERT INTO entities (token, original, label, confidence,
                                   first_seen_at, last_seen_at, occurrence_count)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(token) DO UPDATE SET
                last_seen_at = excluded.last_seen_at,
                confidence = COALESCE(excluded.confidence, entities.confidence),
                occurrence_count = entities.occurrence_count + 1
            """,
            (token, original, label, confidence, now, now),
        )

    def link_doc_entity(
        self, doc_id: str, token: str, start_pos: int, end_pos: int
    ) -> None:
        self._conn.execute(
            """
            INSERT OR IGNORE INTO doc_entities (doc_id, token, start_pos, end_pos)
            VALUES (?, ?, ?, ?)
            """,
            (doc_id, token, start_pos, end_pos),
        )

    # ---- reads ----

    def get_by_token(self, token: str) -> VaultEntry | None:
        row = self._conn.execute(
            "SELECT * FROM entities WHERE token = ?", (token,)
        ).fetchone()
        return self._row_to_entry(row) if row else None

    def list_entities(
        self, label: str | None = None, limit: int = 100, offset: int = 0
    ) -> list[VaultEntry]:
        if label is not None:
            rows = self._conn.execute(
                "SELECT * FROM entities WHERE label = ? "
                "ORDER BY last_seen_at DESC LIMIT ? OFFSET ?",
                (label, limit, offset),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM entities ORDER BY last_seen_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def entities_for_doc(self, doc_id: str) -> list[VaultEntry]:
        rows = self._conn.execute(
            """
            SELECT e.* FROM entities e
            JOIN doc_entities de ON de.token = e.token
            WHERE de.doc_id = ?
            ORDER BY de.start_pos
            """,
            (doc_id,),
        ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def stats(self) -> VaultStats:
        (total,) = self._conn.execute("SELECT COUNT(*) FROM entities").fetchone()
        by_label = {
            row[0]: row[1]
            for row in self._conn.execute(
                "SELECT label, COUNT(*) FROM entities GROUP BY label"
            )
        }
        return VaultStats(total=total, by_label=by_label)

    def search_entities(self, query: str, *, limit: int = 100) -> list[VaultEntry]:
        if not query:
            return []
        rows = self._conn.execute(
            "SELECT * FROM entities WHERE original LIKE ? "
            "ORDER BY occurrence_count DESC LIMIT ?",
            (f"%{query}%", limit),
        ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> VaultEntry:
        return VaultEntry(
            token=row["token"],
            original=row["original"],
            label=row["label"],
            confidence=row["confidence"],
            first_seen_at=row["first_seen_at"],
            last_seen_at=row["last_seen_at"],
            occurrence_count=row["occurrence_count"],
        )
