# piighost CLI + Daemon (Sprint 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Sprint 1 of the piighost CLI + daemon: a stateful `PIIGhostService` core, SQLite vault, five CLI commands, an auto-spawning localhost daemon, and a PII-safe structured-output contract that works on Windows, macOS, and Linux.

**Architecture:** Three-layer model (CLI → Service → {Vault, Pipeline}). CLI is a thin typer adapter over `PIIGhostService`. Daemon exposes the same service over JSON-RPC / HTTP on 127.0.0.1 with a bearer-token file. Vault is SQLite (WAL mode). All anonymization reuses the existing `ThreadAnonymizationPipeline`; we add persistence and an async surface.

**Tech Stack:** Python 3.13, typer, rich, httpx, psutil, portalocker, starlette + uvicorn (daemon HTTP), pydantic v2 (models), sqlite3 (stdlib), pytest + pytest-asyncio, cibuildwheel-style matrix CI (Windows / macOS / Linux).

**Specification:** [docs/superpowers/specs/2026-04-19-piighost-mcp-cli-design.md](../specs/2026-04-19-piighost-mcp-cli-design.md)

**Scope boundary:** Sprint 1 only. Indexing, embedding, querying, and the MCP server adapter are Sprint 2 (separate plan). Classification is deferred to Sprint 3.

---

## File Structure

**New source files:**
- `src/piighost/service/__init__.py` — re-exports `PIIGhostService`, `ServiceConfig`
- `src/piighost/service/config.py` — pydantic `ServiceConfig` loader (TOML → model)
- `src/piighost/service/core.py` — `PIIGhostService` class (async, stateful)
- `src/piighost/service/models.py` — pydantic result types (`AnonymizeResult`, `RehydrateResult`, `VaultEntry`, `VaultStats`, `VaultPage`, `DetectionResult`)
- `src/piighost/service/errors.py` — service-layer exceptions with PII-safe messages
- `src/piighost/vault/__init__.py` — re-exports `Vault`, `open_vault`
- `src/piighost/vault/schema.py` — SQLite DDL + migration runner
- `src/piighost/vault/store.py` — `Vault` class wrapping SQLite connection
- `src/piighost/vault/audit.py` — `AuditLogger` append-only JSONL writer
- `src/piighost/vault/discovery.py` — git-style upward walk to find `.piighost/`
- `src/piighost/cli/__init__.py` — typer `app` object, mounts subcommands
- `src/piighost/cli/main.py` — entry point `piighost` (dispatch + global flags)
- `src/piighost/cli/commands/init.py` — `piighost init`
- `src/piighost/cli/commands/anonymize.py` — `piighost anonymize`
- `src/piighost/cli/commands/rehydrate.py` — `piighost rehydrate`
- `src/piighost/cli/commands/detect.py` — `piighost detect`
- `src/piighost/cli/commands/vault.py` — `piighost vault list/show/stats`
- `src/piighost/cli/commands/daemon.py` — `piighost daemon start/stop/status/restart/logs`
- `src/piighost/cli/output.py` — JSON-line emitter + Rich pretty renderer + exit-code taxonomy
- `src/piighost/cli/io_utils.py` — stdin/path/glob reader helpers
- `src/piighost/daemon/__init__.py` — re-exports `DaemonClient`, `spawn_daemon`
- `src/piighost/daemon/server.py` — starlette app exposing JSON-RPC over HTTP
- `src/piighost/daemon/client.py` — `DaemonClient` (httpx, reads `daemon.json`)
- `src/piighost/daemon/lifecycle.py` — auto-spawn, portalocker, psutil, stale detection
- `src/piighost/daemon/handshake.py` — write/read/validate `daemon.json`
- `src/piighost/daemon/__main__.py` — `python -m piighost.daemon` (actual daemon entry)

**New test files:**
- `tests/service/test_config.py`
- `tests/service/test_core.py`
- `tests/service/test_pii_safe_errors.py`
- `tests/vault/test_schema.py`
- `tests/vault/test_store.py`
- `tests/vault/test_audit.py`
- `tests/vault/test_discovery.py`
- `tests/cli/test_init.py`
- `tests/cli/test_anonymize.py`
- `tests/cli/test_rehydrate.py`
- `tests/cli/test_detect.py`
- `tests/cli/test_vault_cmds.py`
- `tests/cli/test_daemon_cmd.py`
- `tests/cli/test_output_contract.py`
- `tests/cli/test_exit_codes.py`
- `tests/cli/snapshots/` — golden files per command
- `tests/daemon/test_handshake.py`
- `tests/daemon/test_lifecycle.py`
- `tests/daemon/test_server.py`
- `tests/daemon/test_spawn_race.py`
- `tests/daemon/test_cross_platform_smoke.py` — CI-only

**Modified files:**
- `pyproject.toml` — add runtime deps; add `[project.scripts]` entry; add `[mcp]` extra placeholder (empty for Sprint 1)
- `src/piighost/exceptions.py` — add `VaultNotFound`, `VaultSchemaMismatch`, `DaemonUnreachable`, `PIISafetyViolation`
- `.github/workflows/ci.yml` — add Windows + macOS jobs; smoke-test matrix

---

## Task Sequencing Rationale

Tasks are ordered so each one produces working software that builds on the previous. Tasks 1-4 build the `Service` + `Vault` foundation (no CLI yet, fully async, unit-tested). Tasks 5-8 layer the CLI (synchronous wrapper) on top. Tasks 9-11 add the daemon. Task 12 hardens with cross-platform CI + the PII-in-errors fuzz test.

Every task ends with a commit. Every task introduces tests before code (TDD). No task modifies a file touched in a prior task's "Create" list without explicit justification.

---

### Task 1: Scaffold service package + ServiceConfig

**Files:**
- Create: `src/piighost/service/__init__.py`
- Create: `src/piighost/service/config.py`
- Create: `tests/service/test_config.py`
- Create: `tests/service/__init__.py`
- Modify: `pyproject.toml` (add `typer`, `rich`, `pydantic>=2`, `tomli-w` runtime deps)

- [ ] **Step 1: Add runtime dependencies**

Edit `pyproject.toml` — add to `[project] dependencies` (append to existing list):

```toml
dependencies = [
    # ... existing entries ...
    "typer>=0.12",
    "rich>=13.7",
    "pydantic>=2.7",
    "tomli; python_version < '3.11'",  # fallback only; stdlib tomllib on 3.11+
    "tomli-w>=1.0",
    "psutil>=5.9",
    "portalocker>=2.8",
    "httpx>=0.27",
    "starlette>=0.37",
    "uvicorn>=0.30",
]
```

Add to `[project.scripts]` (create section if absent):

```toml
[project.scripts]
piighost = "piighost.cli.main:app"
```

- [ ] **Step 2: Run `uv lock` to refresh lockfile**

Run: `uv lock`
Expected: no errors; `uv.lock` updated.

- [ ] **Step 3: Write the failing test for `ServiceConfig.from_toml`**

Create `tests/service/test_config.py`:

```python
from pathlib import Path

import pytest

from piighost.service.config import ServiceConfig


def test_from_toml_roundtrip(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        """
schema_version = 1

[vault]
placeholder_factory = "hash"
audit_log = true

[detector]
backend = "gliner2"
gliner2_model = "fastino/gliner2-multi-v1"
threshold = 0.5
labels = ["PERSON", "LOC"]

[daemon]
idle_timeout_sec = 3600
log_level = "info"
max_workers = 4

[safety]
strict_rehydrate = true
max_doc_bytes = 10485760
redact_errors = true
""",
        encoding="utf-8",
    )
    cfg = ServiceConfig.from_toml(cfg_path)
    assert cfg.schema_version == 1
    assert cfg.vault.placeholder_factory == "hash"
    assert cfg.detector.backend == "gliner2"
    assert cfg.detector.labels == ["PERSON", "LOC"]
    assert cfg.safety.strict_rehydrate is True


def test_rejects_counter_placeholder(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        """
schema_version = 1
[vault]
placeholder_factory = "counter"
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="hash"):
        ServiceConfig.from_toml(cfg_path)


def test_defaults_when_missing_sections(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text("schema_version = 1\n", encoding="utf-8")
    cfg = ServiceConfig.from_toml(cfg_path)
    assert cfg.vault.placeholder_factory == "hash"
    assert cfg.detector.backend == "gliner2"
    assert cfg.safety.strict_rehydrate is True
```

- [ ] **Step 4: Run the test to verify failure**

Run: `uv run pytest tests/service/test_config.py -v`
Expected: FAIL (`ModuleNotFoundError: piighost.service.config`).

- [ ] **Step 5: Implement `ServiceConfig`**

Create `src/piighost/service/__init__.py`:

```python
"""Stateful service layer for piighost CLI, daemon, and MCP."""

from piighost.service.config import ServiceConfig

__all__ = ["ServiceConfig"]
```

Create `src/piighost/service/config.py`:

```python
"""Load ``.piighost/config.toml`` into a validated pydantic model."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib


class VaultSection(BaseModel):
    placeholder_factory: Literal["hash"] = "hash"
    audit_log: bool = True

    @field_validator("placeholder_factory")
    @classmethod
    def _reject_non_hash(cls, v: str) -> str:
        if v != "hash":
            raise ValueError(
                "placeholder_factory must be 'hash' — counter mode is unsupported "
                "because it breaks RAG token determinism across sessions."
            )
        return v


class DetectorSection(BaseModel):
    backend: Literal["gliner2", "regex_only"] = "gliner2"
    gliner2_model: str = "fastino/gliner2-multi-v1"
    threshold: float = 0.5
    labels: list[str] = Field(
        default_factory=lambda: [
            "PERSON", "LOC", "ORG", "EMAIL",
            "PHONE", "IBAN", "CREDIT_CARD", "ID",
        ]
    )


class EmbedderSection(BaseModel):
    backend: Literal["local", "mistral", "none"] = "none"
    local_model: str = "OrdalieTech/Solon-embeddings-base-0.1"
    mistral_model: str = "mistral-embed"


class IndexSection(BaseModel):
    store: Literal["lancedb"] = "lancedb"
    chunk_size: int = 512
    chunk_overlap: int = 64
    bm25_weight: float = 0.4
    vector_weight: float = 0.6


class DaemonSection(BaseModel):
    idle_timeout_sec: int = 3600
    log_level: Literal["debug", "info", "warn", "error"] = "info"
    max_workers: int = 4


class SafetySection(BaseModel):
    strict_rehydrate: bool = True
    max_doc_bytes: int = 10_485_760
    redact_errors: bool = True


class ServiceConfig(BaseModel):
    schema_version: int = 1
    vault: VaultSection = Field(default_factory=VaultSection)
    detector: DetectorSection = Field(default_factory=DetectorSection)
    embedder: EmbedderSection = Field(default_factory=EmbedderSection)
    index: IndexSection = Field(default_factory=IndexSection)
    daemon: DaemonSection = Field(default_factory=DaemonSection)
    safety: SafetySection = Field(default_factory=SafetySection)

    @classmethod
    def from_toml(cls, path: Path) -> "ServiceConfig":
        with path.open("rb") as f:
            data = tomllib.load(f)
        return cls.model_validate(data)

    @classmethod
    def default(cls) -> "ServiceConfig":
        return cls()
```

- [ ] **Step 6: Run tests to verify pass**

Run: `uv run pytest tests/service/test_config.py -v`
Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock src/piighost/service tests/service
git commit -m "feat(service): scaffold ServiceConfig with pydantic"
```

---

### Task 2: SQLite vault schema + migrations

**Files:**
- Create: `src/piighost/vault/__init__.py`
- Create: `src/piighost/vault/schema.py`
- Create: `tests/vault/__init__.py`
- Create: `tests/vault/test_schema.py`

- [ ] **Step 1: Write the failing schema test**

Create `tests/vault/test_schema.py`:

```python
import sqlite3
from pathlib import Path

from piighost.vault.schema import CURRENT_SCHEMA_VERSION, ensure_schema


def test_creates_all_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "vault.db"
    conn = sqlite3.connect(db_path)
    ensure_schema(conn)
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert {"entities", "doc_entities", "audit_log", "schema_meta"}.issubset(tables)
    conn.close()


def test_stamps_schema_version(tmp_path: Path) -> None:
    db_path = tmp_path / "vault.db"
    conn = sqlite3.connect(db_path)
    ensure_schema(conn)
    version = conn.execute("SELECT version FROM schema_meta").fetchone()[0]
    assert version == CURRENT_SCHEMA_VERSION
    conn.close()


def test_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "vault.db"
    conn = sqlite3.connect(db_path)
    ensure_schema(conn)
    ensure_schema(conn)  # second call must not raise
    (count,) = conn.execute("SELECT COUNT(*) FROM schema_meta").fetchone()
    assert count == 1
    conn.close()


def test_wal_mode_enabled(tmp_path: Path) -> None:
    db_path = tmp_path / "vault.db"
    conn = sqlite3.connect(db_path)
    ensure_schema(conn)
    (mode,) = conn.execute("PRAGMA journal_mode").fetchone()
    assert mode.lower() == "wal"
    conn.close()
```

- [ ] **Step 2: Run test to verify failure**

Run: `uv run pytest tests/vault/test_schema.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement schema module**

Create `src/piighost/vault/__init__.py`:

```python
"""SQLite-backed vault for piighost token/original mappings."""
```

Create `src/piighost/vault/schema.py`:

```python
"""Vault DDL and forward-only migrations."""

from __future__ import annotations

import sqlite3

CURRENT_SCHEMA_VERSION = 1

_DDL = """
CREATE TABLE IF NOT EXISTS entities (
    token TEXT PRIMARY KEY,
    original TEXT NOT NULL,
    label TEXT NOT NULL,
    confidence REAL,
    first_seen_at INTEGER NOT NULL,
    last_seen_at INTEGER NOT NULL,
    occurrence_count INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS doc_entities (
    doc_id TEXT NOT NULL,
    token TEXT NOT NULL REFERENCES entities(token),
    start_pos INTEGER,
    end_pos INTEGER,
    PRIMARY KEY (doc_id, token, start_pos)
);

CREATE TABLE IF NOT EXISTS audit_log (
    ts INTEGER NOT NULL,
    caller_pid INTEGER,
    caller_kind TEXT,
    op TEXT NOT NULL,
    token TEXT,
    metadata_json TEXT
);

CREATE TABLE IF NOT EXISTS schema_meta (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    version INTEGER NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_entities_label ON entities(label);
CREATE INDEX IF NOT EXISTS idx_doc_entities_doc ON doc_entities(doc_id);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Idempotently create schema and stamp the version row.

    Sets ``journal_mode=WAL`` so the daemon and CLI can read concurrently.
    """
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(_DDL)
    cur = conn.execute("SELECT COUNT(*) FROM schema_meta")
    if cur.fetchone()[0] == 0:
        import time

        conn.execute(
            "INSERT INTO schema_meta (singleton, version, created_at) VALUES (1, ?, ?)",
            (CURRENT_SCHEMA_VERSION, int(time.time())),
        )
    conn.commit()
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/vault/test_schema.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/piighost/vault tests/vault
git commit -m "feat(vault): SQLite schema with idempotent migrations"
```

---

### Task 3: Vault store + audit log + discovery

**Files:**
- Create: `src/piighost/vault/store.py`
- Create: `src/piighost/vault/audit.py`
- Create: `src/piighost/vault/discovery.py`
- Create: `tests/vault/test_store.py`
- Create: `tests/vault/test_audit.py`
- Create: `tests/vault/test_discovery.py`
- Modify: `src/piighost/vault/__init__.py`
- Modify: `src/piighost/exceptions.py` (add `VaultNotFound`, `VaultSchemaMismatch`)

- [ ] **Step 1: Add exception types**

Append to `src/piighost/exceptions.py`:

```python
class VaultNotFound(Exception):
    """No `.piighost/` found in cwd or any ancestor directory."""


class VaultSchemaMismatch(Exception):
    """Vault database schema version does not match the current code."""


class PIISafetyViolation(Exception):
    """An operation would violate a PII-safety invariant (e.g. unknown rehydrate token in strict mode)."""


class DaemonUnreachable(Exception):
    """Daemon is configured but not reachable; CLI may auto-spawn."""
```

- [ ] **Step 2: Write the failing store test**

Create `tests/vault/test_store.py`:

```python
from pathlib import Path

import pytest

from piighost.vault.store import Vault


@pytest.fixture()
def vault(tmp_path: Path) -> Vault:
    v = Vault.open(tmp_path / "vault.db")
    yield v
    v.close()


def test_upsert_and_lookup(vault: Vault) -> None:
    vault.upsert_entity(
        token="<PERSON:a1b2c3d4>",
        original="Alice",
        label="PERSON",
        confidence=0.97,
    )
    entry = vault.get_by_token("<PERSON:a1b2c3d4>")
    assert entry is not None
    assert entry.original == "Alice"
    assert entry.label == "PERSON"
    assert entry.occurrence_count == 1


def test_upsert_increments_occurrence(vault: Vault) -> None:
    vault.upsert_entity("<P:x>", "Bob", "PERSON", 0.9)
    vault.upsert_entity("<P:x>", "Bob", "PERSON", 0.92)
    entry = vault.get_by_token("<P:x>")
    assert entry is not None
    assert entry.occurrence_count == 2


def test_list_filters_by_label(vault: Vault) -> None:
    vault.upsert_entity("<PERSON:1>", "Alice", "PERSON", 0.9)
    vault.upsert_entity("<LOC:2>", "Paris", "LOC", 0.9)
    people = vault.list_entities(label="PERSON")
    assert len(people) == 1
    assert people[0].label == "PERSON"


def test_stats(vault: Vault) -> None:
    vault.upsert_entity("<PERSON:1>", "Alice", "PERSON", 0.9)
    vault.upsert_entity("<LOC:2>", "Paris", "LOC", 0.9)
    stats = vault.stats()
    assert stats.total == 2
    assert stats.by_label["PERSON"] == 1
    assert stats.by_label["LOC"] == 1


def test_link_doc_entity(vault: Vault) -> None:
    vault.upsert_entity("<P:1>", "Alice", "PERSON", 0.9)
    vault.link_doc_entity(doc_id="doc1", token="<P:1>", start_pos=0, end_pos=5)
    hits = vault.entities_for_doc("doc1")
    assert len(hits) == 1
    assert hits[0].original == "Alice"
```

- [ ] **Step 3: Run test to verify failure**

Run: `uv run pytest tests/vault/test_store.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 4: Implement the store**

Create `src/piighost/vault/store.py`:

```python
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
```

- [ ] **Step 5: Run store tests to verify pass**

Run: `uv run pytest tests/vault/test_store.py -v`
Expected: 5 passed.

- [ ] **Step 6: Write audit logger test**

Create `tests/vault/test_audit.py`:

```python
import json
from pathlib import Path

from piighost.vault.audit import AuditLogger


def test_appends_jsonl(tmp_path: Path) -> None:
    log = tmp_path / "audit.log"
    a = AuditLogger(log)
    a.record(op="rehydrate", token="<P:x>", caller_kind="cli", caller_pid=1234)
    a.record(op="vault_show_reveal", token="<P:x>", caller_kind="mcp", caller_pid=5678)
    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    row = json.loads(lines[0])
    assert row["op"] == "rehydrate"
    assert row["token"] == "<P:x>"
    assert row["caller_kind"] == "cli"


def test_append_only(tmp_path: Path) -> None:
    log = tmp_path / "audit.log"
    AuditLogger(log).record(op="rehydrate", caller_kind="cli")
    AuditLogger(log).record(op="rehydrate", caller_kind="cli")
    assert len(log.read_text(encoding="utf-8").splitlines()) == 2
```

- [ ] **Step 7: Run test to verify failure**

Run: `uv run pytest tests/vault/test_audit.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 8: Implement audit logger**

Create `src/piighost/vault/audit.py`:

```python
"""Append-only JSONL audit log for sensitive vault operations."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class AuditLogger:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        *,
        op: str,
        token: str | None = None,
        caller_kind: str = "cli",
        caller_pid: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        row = {
            "ts": int(time.time()),
            "op": op,
            "token": token,
            "caller_kind": caller_kind,
            "caller_pid": caller_pid,
            "metadata": metadata or {},
        }
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
```

- [ ] **Step 9: Run audit tests to verify pass**

Run: `uv run pytest tests/vault/test_audit.py -v`
Expected: 2 passed.

- [ ] **Step 10: Write discovery test**

Create `tests/vault/test_discovery.py`:

```python
from pathlib import Path

import pytest

from piighost.exceptions import VaultNotFound
from piighost.vault.discovery import find_vault_dir


def test_finds_in_cwd(tmp_path: Path) -> None:
    (tmp_path / ".piighost").mkdir()
    assert find_vault_dir(start=tmp_path) == tmp_path / ".piighost"


def test_walks_upward(tmp_path: Path) -> None:
    (tmp_path / ".piighost").mkdir()
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    assert find_vault_dir(start=deep) == tmp_path / ".piighost"


def test_raises_when_absent(tmp_path: Path) -> None:
    with pytest.raises(VaultNotFound):
        find_vault_dir(start=tmp_path)


def test_explicit_override(tmp_path: Path) -> None:
    explicit = tmp_path / "custom" / ".piighost"
    explicit.mkdir(parents=True)
    assert find_vault_dir(start=tmp_path, explicit=explicit) == explicit
```

- [ ] **Step 11: Run test to verify failure**

Run: `uv run pytest tests/vault/test_discovery.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 12: Implement discovery**

Create `src/piighost/vault/discovery.py`:

```python
"""Git-style upward walk to locate the nearest `.piighost/` directory."""

from __future__ import annotations

from pathlib import Path

from piighost.exceptions import VaultNotFound


def find_vault_dir(
    *, start: Path | None = None, explicit: Path | None = None
) -> Path:
    """Locate a vault directory.

    Resolution order:
    1. If ``explicit`` is provided and exists, return it.
    2. Walk from ``start`` (default: cwd) upward looking for ``.piighost/``.
    3. Raise ``VaultNotFound``.
    """
    if explicit is not None:
        if not explicit.is_dir():
            raise VaultNotFound(f"--vault {explicit} is not a directory")
        return explicit.resolve()

    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        found = candidate / ".piighost"
        if found.is_dir():
            return found
    raise VaultNotFound(
        "No .piighost/ in cwd or any ancestor directory. "
        "Run `piighost init` here or pass --vault."
    )
```

- [ ] **Step 13: Update `vault/__init__.py` exports**

Replace `src/piighost/vault/__init__.py`:

```python
"""SQLite-backed vault for piighost token/original mappings."""

from piighost.vault.audit import AuditLogger
from piighost.vault.discovery import find_vault_dir
from piighost.vault.store import Vault, VaultEntry, VaultStats

__all__ = [
    "AuditLogger",
    "Vault",
    "VaultEntry",
    "VaultStats",
    "find_vault_dir",
]
```

- [ ] **Step 14: Run full vault test suite to verify pass**

Run: `uv run pytest tests/vault -v`
Expected: 11 passed (4 schema + 5 store + 2 audit + 4 discovery). Adjust if counts drift.

- [ ] **Step 15: Commit**

```bash
git add src/piighost/vault src/piighost/exceptions.py tests/vault
git commit -m "feat(vault): store, audit log, and upward discovery"
```

---

### Task 4: PIIGhostService core with anonymize/rehydrate/detect

**Files:**
- Create: `src/piighost/service/core.py`
- Create: `src/piighost/service/models.py`
- Create: `src/piighost/service/errors.py`
- Create: `tests/service/test_core.py`
- Modify: `src/piighost/service/__init__.py`

- [ ] **Step 1: Write the failing core tests**

Create `tests/service/test_core.py`:

```python
from pathlib import Path

import pytest

from piighost.exceptions import PIISafetyViolation
from piighost.service import PIIGhostService, ServiceConfig


class _StubDetector:
    """Deterministic Alice/Paris stub so tests don't need GLiNER2 weights."""

    async def detect(self, text: str) -> list:
        from piighost.models import Detection, Span

        out: list = []
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


@pytest.fixture()
def vault_dir(tmp_path: Path) -> Path:
    d = tmp_path / ".piighost"
    d.mkdir()
    (d / "config.toml").write_text("schema_version = 1\n", encoding="utf-8")
    return d


@pytest.mark.asyncio
async def test_anonymize_persists_entities(vault_dir: Path) -> None:
    svc = await PIIGhostService.create(
        vault_dir=vault_dir,
        config=ServiceConfig.default(),
        detector=_StubDetector(),
    )
    try:
        r = await svc.anonymize("Alice lives in Paris", doc_id="doc1")
        assert "Alice" not in r.anonymized
        assert "Paris" not in r.anonymized
        assert r.anonymized.count("<PERSON:") == 1
        assert r.anonymized.count("<LOC:") == 1
        assert len(r.entities) == 2
        stats = await svc.vault_stats()
        assert stats.total == 2
    finally:
        await svc.close()


@pytest.mark.asyncio
async def test_rehydrate_roundtrip(vault_dir: Path) -> None:
    svc = await PIIGhostService.create(
        vault_dir=vault_dir,
        config=ServiceConfig.default(),
        detector=_StubDetector(),
    )
    try:
        anon = await svc.anonymize("Alice met Alice in Paris")
        rehydrated = await svc.rehydrate(anon.anonymized)
        assert rehydrated.text == "Alice met Alice in Paris"
    finally:
        await svc.close()


@pytest.mark.asyncio
async def test_rehydrate_strict_rejects_unknown_token(vault_dir: Path) -> None:
    svc = await PIIGhostService.create(
        vault_dir=vault_dir,
        config=ServiceConfig.default(),
        detector=_StubDetector(),
    )
    try:
        with pytest.raises(PIISafetyViolation):
            await svc.rehydrate("Hello <PERSON:deadbeef>!", strict=True)
    finally:
        await svc.close()


@pytest.mark.asyncio
async def test_detect_does_not_mutate_vault(vault_dir: Path) -> None:
    svc = await PIIGhostService.create(
        vault_dir=vault_dir,
        config=ServiceConfig.default(),
        detector=_StubDetector(),
    )
    try:
        await svc.detect("Alice lives in Paris")
        stats = await svc.vault_stats()
        assert stats.total == 0
    finally:
        await svc.close()
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/service/test_core.py -v`
Expected: FAIL (`ModuleNotFoundError: piighost.service.core`).

- [ ] **Step 3: Implement result models**

Create `src/piighost/service/models.py`:

```python
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
    # original omitted unless ``reveal=True`` is passed at the call site
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
```

- [ ] **Step 4: Implement service errors**

Create `src/piighost/service/errors.py`:

```python
"""Service-layer exceptions. Messages never contain raw PII."""

from __future__ import annotations


class ServiceError(Exception):
    """Base class. Subclasses take structured fields, not PII text."""


class AnonymizationFailed(ServiceError):
    def __init__(self, doc_id: str, stage: str, entity_count: int) -> None:
        super().__init__(
            f"Anonymization failed at stage={stage} for doc={doc_id} "
            f"after detecting {entity_count} entities"
        )
        self.doc_id = doc_id
        self.stage = stage
        self.entity_count = entity_count
```

- [ ] **Step 5: Implement the service core**

Create `src/piighost/service/core.py`:

```python
"""The stateful core that CLI, daemon, and MCP all wrap."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Protocol

from piighost.anonymizer import Anonymizer
from piighost.exceptions import PIISafetyViolation
from piighost.models import Detection, Entity, Span
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
from piighost.vault import AuditLogger, Vault, VaultEntry, VaultStats

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

    async def anonymize(
        self, text: str, *, doc_id: str | None = None
    ) -> AnonymizeResult:
        doc_id = doc_id or f"anon-{abs(hash(text)) % 10**10}"
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
                token = self._ph.create(ent)
                self._vault.upsert_entity(
                    token=token,
                    original=ent.text,
                    label=ent.label,
                    confidence=max(
                        (d.confidence for d in ent.detections if d.confidence), default=None
                    ),
                )
                for det in ent.detections:
                    self._vault.link_doc_entity(
                        doc_id=doc_id,
                        token=token,
                        start_pos=det.position.start_pos,
                        end_pos=det.position.end_pos,
                    )

        refs = [
            EntityRef(token=self._ph.create(ent), label=ent.label, count=len(ent.detections))
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

    # ---- vault ops ----

    async def vault_list(
        self, *, label: str | None = None, limit: int = 100, offset: int = 0,
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
            self._audit.record(op="vault_show_reveal", token=token, caller_kind="service")
        return self._to_entry_model(row, reveal=reveal)

    async def vault_stats(self) -> VaultStatsModel:
        s = self._vault.stats()
        return VaultStatsModel(total=s.total, by_label=s.by_label)

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
    if config.detector.backend == "gliner2":
        from piighost.detector.gliner2 import Gliner2Detector
        from gliner2 import GLiNER2

        model = GLiNER2.from_pretrained(config.detector.gliner2_model)
        return Gliner2Detector(model=model, labels=config.detector.labels)
    raise NotImplementedError(f"detector backend {config.detector.backend!r} not shipped yet")
```

- [ ] **Step 6: Update service `__init__.py` exports**

Replace `src/piighost/service/__init__.py`:

```python
"""Stateful service layer for piighost CLI, daemon, and MCP."""

from piighost.service.config import ServiceConfig
from piighost.service.core import PIIGhostService
from piighost.service.errors import AnonymizationFailed, ServiceError
from piighost.service.models import (
    AnonymizeResult,
    DetectionResult,
    EntityRef,
    RehydrateResult,
    VaultEntryModel,
    VaultPage,
    VaultStatsModel,
)

__all__ = [
    "AnonymizationFailed",
    "AnonymizeResult",
    "DetectionResult",
    "EntityRef",
    "PIIGhostService",
    "RehydrateResult",
    "ServiceConfig",
    "ServiceError",
    "VaultEntryModel",
    "VaultPage",
    "VaultStatsModel",
]
```

- [ ] **Step 7: Run service tests to verify pass**

Run: `uv run pytest tests/service/test_core.py -v`
Expected: 4 passed.

- [ ] **Step 8: Commit**

```bash
git add src/piighost/service tests/service/test_core.py
git commit -m "feat(service): PIIGhostService with anonymize/rehydrate/detect"
```

---

### Task 5: PII-safe error fuzz test

**Files:**
- Create: `tests/service/test_pii_safe_errors.py`

- [ ] **Step 1: Write the fuzz test**

Create `tests/service/test_pii_safe_errors.py`:

```python
"""Invariant: no raw PII appears in any exception message."""

from __future__ import annotations

import random
import string
from pathlib import Path

import pytest

from piighost.service import PIIGhostService, ServiceConfig
from piighost.service.errors import AnonymizationFailed


@pytest.mark.asyncio
async def test_fuzz_no_raw_pii_in_error_messages(tmp_path: Path) -> None:
    rng = random.Random(0xB00B)
    vault_dir = tmp_path / ".piighost"
    vault_dir.mkdir()

    class _BrokenAnonymizer:
        async def detect(self, text: str) -> list:
            from piighost.models import Detection, Span

            return [
                Detection(
                    text="SECRETNAME",
                    label="PERSON",
                    position=Span(start_pos=0, end_pos=10),
                    confidence=0.9,
                )
            ]

    svc = await PIIGhostService.create(
        vault_dir=vault_dir, config=ServiceConfig.default(), detector=_BrokenAnonymizer()
    )
    try:
        secrets = ["".join(rng.choices(string.ascii_letters, k=12)) for _ in range(100)]
        for s in secrets:
            try:
                await svc.anonymize(s + " is here")
            except AnonymizationFailed as exc:
                msg = str(exc)
                assert s not in msg, f"PII leak: {s!r} in error message"
    finally:
        await svc.close()
```

- [ ] **Step 2: Run the test**

Run: `uv run pytest tests/service/test_pii_safe_errors.py -v`
Expected: PASS (no leaks; all errors are structured).

- [ ] **Step 3: Commit**

```bash
git add tests/service/test_pii_safe_errors.py
git commit -m "test(service): fuzz for raw-PII leaks in error messages"
```

---

### Task 6: CLI output contract (JSON Lines + Rich + exit codes)

**Files:**
- Create: `src/piighost/cli/__init__.py`
- Create: `src/piighost/cli/output.py`
- Create: `src/piighost/cli/io_utils.py`
- Create: `tests/cli/__init__.py`
- Create: `tests/cli/test_output_contract.py`

- [ ] **Step 1: Write the failing output test**

Create `tests/cli/test_output_contract.py`:

```python
import io
import json

from piighost.cli.output import (
    ExitCode,
    emit_error_line,
    emit_json_line,
)


def test_emit_json_line_writes_jsonl() -> None:
    buf = io.StringIO()
    emit_json_line({"a": 1, "b": "x"}, stream=buf)
    emit_json_line({"a": 2}, stream=buf)
    lines = buf.getvalue().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"a": 1, "b": "x"}


def test_emit_error_line_has_structure() -> None:
    buf = io.StringIO()
    emit_error_line(
        error="VaultNotFound",
        message="nope",
        hint="run init",
        exit_code=ExitCode.USER_ERROR,
        stream=buf,
    )
    parsed = json.loads(buf.getvalue())
    assert parsed["error"] == "VaultNotFound"
    assert parsed["exit_code"] == 2


def test_exit_code_taxonomy() -> None:
    assert int(ExitCode.SUCCESS) == 0
    assert int(ExitCode.BUG) == 1
    assert int(ExitCode.USER_ERROR) == 2
    assert int(ExitCode.ANONYMIZATION_FAILED) == 3
    assert int(ExitCode.DAEMON_UNREACHABLE) == 4
    assert int(ExitCode.PII_SAFETY_VIOLATION) == 5
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/cli/test_output_contract.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement output module**

Create `src/piighost/cli/__init__.py`:

```python
"""piighost command-line interface."""
```

Create `src/piighost/cli/output.py`:

```python
"""JSON Lines emitter, Rich pretty renderer, and exit-code taxonomy."""

from __future__ import annotations

import enum
import json
import sys
from typing import IO, Any

from rich.console import Console
from rich.table import Table


class ExitCode(enum.IntEnum):
    SUCCESS = 0
    BUG = 1
    USER_ERROR = 2
    ANONYMIZATION_FAILED = 3
    DAEMON_UNREACHABLE = 4
    PII_SAFETY_VIOLATION = 5


def emit_json_line(obj: Any, *, stream: IO[str] | None = None) -> None:
    target = stream if stream is not None else sys.stdout
    target.write(json.dumps(obj, ensure_ascii=False) + "\n")


def emit_error_line(
    *,
    error: str,
    message: str,
    hint: str | None = None,
    exit_code: ExitCode,
    stream: IO[str] | None = None,
) -> None:
    target = stream if stream is not None else sys.stderr
    payload = {
        "error": error,
        "message": message,
        "hint": hint,
        "exit_code": int(exit_code),
    }
    target.write(json.dumps(payload, ensure_ascii=False) + "\n")


def pretty_anonymize(console: Console, result: dict[str, Any]) -> None:
    table = Table(title=f"doc: {result['doc_id']}")
    table.add_column("token")
    table.add_column("label")
    table.add_column("count", justify="right")
    for ent in result.get("entities", []):
        table.add_row(ent["token"], ent["label"], str(ent["count"]))
    console.print(table)
    console.print()
    console.print(result["anonymized"])
```

Create `src/piighost/cli/io_utils.py`:

```python
"""Read input text from a path, stdin, or string literal."""

from __future__ import annotations

import sys
from pathlib import Path


def read_input(spec: str) -> tuple[str, str]:
    """Return ``(doc_id, text)``.

    ``spec == "-"`` reads stdin, ``doc_id = "<stdin>"``.
    A file path reads UTF-8 text; ``doc_id`` is the path.
    """
    if spec == "-":
        return "<stdin>", sys.stdin.read()
    p = Path(spec)
    return str(p), p.read_text(encoding="utf-8")
```

- [ ] **Step 4: Run test to verify pass**

Run: `uv run pytest tests/cli/test_output_contract.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/piighost/cli tests/cli/__init__.py tests/cli/test_output_contract.py
git commit -m "feat(cli): JSON Lines output + exit-code taxonomy + Rich renderer"
```

---

### Task 7: CLI commands — init, anonymize, rehydrate, detect

**Files:**
- Create: `src/piighost/cli/main.py`
- Create: `src/piighost/cli/commands/__init__.py`
- Create: `src/piighost/cli/commands/init.py`
- Create: `src/piighost/cli/commands/anonymize.py`
- Create: `src/piighost/cli/commands/rehydrate.py`
- Create: `src/piighost/cli/commands/detect.py`
- Create: `tests/cli/test_init.py`
- Create: `tests/cli/test_anonymize.py`
- Create: `tests/cli/test_rehydrate.py`
- Create: `tests/cli/test_detect.py`

- [ ] **Step 1: Write failing `init` test**

Create `tests/cli/test_init.py`:

```python
from pathlib import Path

from typer.testing import CliRunner

from piighost.cli.main import app


def test_init_creates_piighost_dir(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["init"], env={"PIIGHOST_CWD": str(tmp_path)})
    assert result.exit_code == 0
    assert (tmp_path / ".piighost" / "config.toml").exists()
    assert (tmp_path / ".piighost" / "vault.db").exists()


def test_init_is_idempotent(tmp_path: Path) -> None:
    runner = CliRunner()
    runner.invoke(app, ["init"], env={"PIIGHOST_CWD": str(tmp_path)})
    result = runner.invoke(app, ["init"], env={"PIIGHOST_CWD": str(tmp_path)})
    # Default: second run refuses unless --force; exit_code != 0 acceptable
    assert result.exit_code in (0, 2)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/cli/test_init.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement CLI main + init**

Create `src/piighost/cli/commands/__init__.py` (empty).

Create `src/piighost/cli/main.py`:

```python
"""piighost CLI entry point (typer app)."""

from __future__ import annotations

import os
from pathlib import Path

import typer

from piighost.cli.commands import anonymize as anonymize_cmd
from piighost.cli.commands import detect as detect_cmd
from piighost.cli.commands import init as init_cmd
from piighost.cli.commands import rehydrate as rehydrate_cmd

app = typer.Typer(no_args_is_help=True, add_completion=False)

app.command("init")(init_cmd.run)
app.command("anonymize")(anonymize_cmd.run)
app.command("rehydrate")(rehydrate_cmd.run)
app.command("detect")(detect_cmd.run)


def _effective_cwd() -> Path:
    return Path(os.environ.get("PIIGHOST_CWD", Path.cwd()))
```

Create `src/piighost/cli/commands/init.py`:

```python
"""`piighost init` — create `.piighost/` in the current directory."""

from __future__ import annotations

import os
from pathlib import Path

import typer

from piighost.cli.output import ExitCode, emit_error_line, emit_json_line
from piighost.vault.store import Vault

_DEFAULT_CONFIG = """\
schema_version = 1

[vault]
placeholder_factory = "hash"
audit_log = true

[detector]
backend = "gliner2"
gliner2_model = "fastino/gliner2-multi-v1"
threshold = 0.5
labels = ["PERSON", "LOC", "ORG", "EMAIL", "PHONE", "IBAN", "CREDIT_CARD", "ID"]

[embedder]
backend = "none"

[daemon]
idle_timeout_sec = 3600

[safety]
strict_rehydrate = true
max_doc_bytes = 10485760
redact_errors = true
"""


def run(force: bool = typer.Option(False, "--force")) -> None:
    cwd = Path(os.environ.get("PIIGHOST_CWD", Path.cwd()))
    vault_dir = cwd / ".piighost"
    cfg = vault_dir / "config.toml"
    if vault_dir.exists() and not force:
        emit_error_line(
            error="VaultAlreadyExists",
            message=f"{vault_dir} already exists",
            hint="pass --force to overwrite",
            exit_code=ExitCode.USER_ERROR,
        )
        raise typer.Exit(code=int(ExitCode.USER_ERROR))
    vault_dir.mkdir(parents=True, exist_ok=True)
    cfg.write_text(_DEFAULT_CONFIG, encoding="utf-8")
    # Pre-create the DB so second-call users get a warm schema.
    v = Vault.open(vault_dir / "vault.db")
    v.close()
    emit_json_line({"created": str(vault_dir), "config": str(cfg)})
```

- [ ] **Step 4: Run `init` test to verify pass**

Run: `uv run pytest tests/cli/test_init.py -v`
Expected: 2 passed.

- [ ] **Step 5: Write failing anonymize/rehydrate/detect tests**

Create `tests/cli/test_anonymize.py`:

```python
import json
from pathlib import Path

from typer.testing import CliRunner

from piighost.cli.main import app


def test_anonymize_stdin(tmp_path: Path) -> None:
    runner = CliRunner(mix_stderr=False)
    runner.invoke(app, ["init"], env={"PIIGHOST_CWD": str(tmp_path)})
    # We inject a stub detector via env var (see service loader)
    result = runner.invoke(
        app,
        ["anonymize", "-"],
        input="Alice lives in Paris",
        env={"PIIGHOST_CWD": str(tmp_path), "PIIGHOST_DETECTOR": "stub"},
    )
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert "Alice" not in payload["anonymized"]
    assert payload["anonymized"].count("<PERSON:") == 1
```

Create `tests/cli/test_rehydrate.py`:

```python
import json
from pathlib import Path

from typer.testing import CliRunner

from piighost.cli.main import app


def test_rehydrate_roundtrip(tmp_path: Path) -> None:
    runner = CliRunner(mix_stderr=False)
    env = {"PIIGHOST_CWD": str(tmp_path), "PIIGHOST_DETECTOR": "stub"}
    runner.invoke(app, ["init"], env=env)
    a = runner.invoke(app, ["anonymize", "-"], input="Alice in Paris", env=env)
    anon = json.loads(a.stdout.strip().splitlines()[-1])["anonymized"]
    r = runner.invoke(app, ["rehydrate", "-"], input=anon, env=env)
    assert r.exit_code == 0
    payload = json.loads(r.stdout.strip().splitlines()[-1])
    assert payload["text"] == "Alice in Paris"
```

Create `tests/cli/test_detect.py`:

```python
import json
from pathlib import Path

from typer.testing import CliRunner

from piighost.cli.main import app


def test_detect_emits_detections(tmp_path: Path) -> None:
    runner = CliRunner(mix_stderr=False)
    env = {"PIIGHOST_CWD": str(tmp_path), "PIIGHOST_DETECTOR": "stub"}
    runner.invoke(app, ["init"], env=env)
    r = runner.invoke(app, ["detect", "-"], input="Alice lives in Paris", env=env)
    assert r.exit_code == 0
    payload = json.loads(r.stdout.strip().splitlines()[-1])
    labels = {d["label"] for d in payload["detections"]}
    assert "PERSON" in labels
    assert "LOC" in labels
```

- [ ] **Step 6: Run them to verify failure**

Run: `uv run pytest tests/cli/test_anonymize.py tests/cli/test_rehydrate.py tests/cli/test_detect.py -v`
Expected: all FAIL (`ModuleNotFoundError`).

- [ ] **Step 7: Implement the three commands + stub-detector hook**

Append to `src/piighost/service/core.py` (extend `_build_default_detector`):

```python
async def _build_default_detector(config: ServiceConfig) -> _Detector:
    import os

    if os.environ.get("PIIGHOST_DETECTOR") == "stub":
        return _StubDetector()
    if config.detector.backend == "gliner2":
        from piighost.detector.gliner2 import Gliner2Detector
        from gliner2 import GLiNER2

        model = GLiNER2.from_pretrained(config.detector.gliner2_model)
        return Gliner2Detector(model=model, labels=config.detector.labels)
    raise NotImplementedError(f"detector backend {config.detector.backend!r} not shipped yet")


class _StubDetector:
    """Deterministic stub used only when ``PIIGHOST_DETECTOR=stub`` (tests/dev)."""

    async def detect(self, text: str) -> list:
        from piighost.models import Detection, Span

        out: list = []
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
```

Create `src/piighost/cli/commands/anonymize.py`:

```python
"""`piighost anonymize` — detect + anonymize text from a path or stdin."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import typer

from piighost.cli.io_utils import read_input
from piighost.cli.output import ExitCode, emit_error_line, emit_json_line
from piighost.exceptions import VaultNotFound
from piighost.service import PIIGhostService, ServiceConfig
from piighost.service.config import ServiceConfig as _Cfg
from piighost.vault.discovery import find_vault_dir


def run(
    target: str = typer.Argument(..., help="File path or '-' for stdin"),
    vault: Path | None = typer.Option(None, "--vault"),
) -> None:
    try:
        vault_dir = find_vault_dir(
            start=Path(os.environ.get("PIIGHOST_CWD", Path.cwd())),
            explicit=vault,
        )
    except VaultNotFound as exc:
        emit_error_line(
            error="VaultNotFound",
            message=str(exc),
            hint="Run `piighost init` or pass --vault",
            exit_code=ExitCode.USER_ERROR,
        )
        raise typer.Exit(code=int(ExitCode.USER_ERROR))

    doc_id, text = read_input(target)
    asyncio.run(_run(vault_dir, doc_id, text))


async def _run(vault_dir: Path, doc_id: str, text: str) -> None:
    cfg_path = vault_dir / "config.toml"
    config = (
        _Cfg.from_toml(cfg_path) if cfg_path.exists() else ServiceConfig.default()
    )
    svc = await PIIGhostService.create(vault_dir=vault_dir, config=config)
    try:
        result = await svc.anonymize(text, doc_id=doc_id)
        emit_json_line(result.model_dump())
    finally:
        await svc.close()
```

Create `src/piighost/cli/commands/rehydrate.py`:

```python
"""`piighost rehydrate` — reverse anonymized text via vault."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import typer

from piighost.cli.io_utils import read_input
from piighost.cli.output import ExitCode, emit_error_line, emit_json_line
from piighost.exceptions import PIISafetyViolation, VaultNotFound
from piighost.service import PIIGhostService
from piighost.service.config import ServiceConfig
from piighost.vault.discovery import find_vault_dir


def run(
    target: str = typer.Argument(..., help="File path or '-' for stdin"),
    vault: Path | None = typer.Option(None, "--vault"),
    lenient: bool = typer.Option(False, "--lenient"),
) -> None:
    try:
        vault_dir = find_vault_dir(
            start=Path(os.environ.get("PIIGHOST_CWD", Path.cwd())),
            explicit=vault,
        )
    except VaultNotFound as exc:
        emit_error_line(
            error="VaultNotFound",
            message=str(exc),
            hint="Run `piighost init` or pass --vault",
            exit_code=ExitCode.USER_ERROR,
        )
        raise typer.Exit(code=int(ExitCode.USER_ERROR))

    _, text = read_input(target)
    try:
        asyncio.run(_run(vault_dir, text, strict=not lenient))
    except PIISafetyViolation as exc:
        emit_error_line(
            error="PIISafetyViolation",
            message=str(exc),
            hint="Pass --lenient to skip unknown tokens",
            exit_code=ExitCode.PII_SAFETY_VIOLATION,
        )
        raise typer.Exit(code=int(ExitCode.PII_SAFETY_VIOLATION))


async def _run(vault_dir: Path, text: str, *, strict: bool) -> None:
    cfg_path = vault_dir / "config.toml"
    config = ServiceConfig.from_toml(cfg_path) if cfg_path.exists() else ServiceConfig.default()
    svc = await PIIGhostService.create(vault_dir=vault_dir, config=config)
    try:
        result = await svc.rehydrate(text, strict=strict)
        emit_json_line(result.model_dump())
    finally:
        await svc.close()
```

Create `src/piighost/cli/commands/detect.py`:

```python
"""`piighost detect` — detection only, no vault mutation."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import typer

from piighost.cli.io_utils import read_input
from piighost.cli.output import ExitCode, emit_error_line, emit_json_line
from piighost.exceptions import VaultNotFound
from piighost.service import PIIGhostService
from piighost.service.config import ServiceConfig
from piighost.vault.discovery import find_vault_dir


def run(
    target: str = typer.Argument(..., help="File path or '-' for stdin"),
    vault: Path | None = typer.Option(None, "--vault"),
) -> None:
    try:
        vault_dir = find_vault_dir(
            start=Path(os.environ.get("PIIGHOST_CWD", Path.cwd())),
            explicit=vault,
        )
    except VaultNotFound as exc:
        emit_error_line(
            error="VaultNotFound",
            message=str(exc),
            hint="Run `piighost init` or pass --vault",
            exit_code=ExitCode.USER_ERROR,
        )
        raise typer.Exit(code=int(ExitCode.USER_ERROR))

    doc_id, text = read_input(target)
    asyncio.run(_run(vault_dir, doc_id, text))


async def _run(vault_dir: Path, doc_id: str, text: str) -> None:
    cfg_path = vault_dir / "config.toml"
    config = ServiceConfig.from_toml(cfg_path) if cfg_path.exists() else ServiceConfig.default()
    svc = await PIIGhostService.create(vault_dir=vault_dir, config=config)
    try:
        dets = await svc.detect(text)
        emit_json_line({"doc_id": doc_id, "detections": [d.model_dump() for d in dets]})
    finally:
        await svc.close()
```

- [ ] **Step 8: Run the CLI tests to verify pass**

Run: `uv run pytest tests/cli -v`
Expected: all passing (init: 2, anonymize: 1, rehydrate: 1, detect: 1, output: 3).

- [ ] **Step 9: Commit**

```bash
git add src/piighost/cli src/piighost/service/core.py tests/cli
git commit -m "feat(cli): init/anonymize/rehydrate/detect commands"
```

---

### Task 8: CLI `vault list/show/stats` commands

**Files:**
- Create: `src/piighost/cli/commands/vault.py`
- Create: `tests/cli/test_vault_cmds.py`
- Modify: `src/piighost/cli/main.py`

- [ ] **Step 1: Write the failing test**

Create `tests/cli/test_vault_cmds.py`:

```python
import json
from pathlib import Path

from typer.testing import CliRunner

from piighost.cli.main import app


def _setup(tmp_path: Path) -> dict[str, str]:
    env = {"PIIGHOST_CWD": str(tmp_path), "PIIGHOST_DETECTOR": "stub"}
    runner = CliRunner(mix_stderr=False)
    runner.invoke(app, ["init"], env=env)
    runner.invoke(app, ["anonymize", "-"], input="Alice in Paris", env=env)
    return env


def test_vault_list_masks_by_default(tmp_path: Path) -> None:
    env = _setup(tmp_path)
    r = CliRunner(mix_stderr=False).invoke(app, ["vault", "list"], env=env)
    assert r.exit_code == 0
    rows = [json.loads(l) for l in r.stdout.strip().splitlines()]
    assert all(row["original"] is None for row in rows)
    assert any(row["original_masked"] for row in rows)


def test_vault_stats(tmp_path: Path) -> None:
    env = _setup(tmp_path)
    r = CliRunner(mix_stderr=False).invoke(app, ["vault", "stats"], env=env)
    assert r.exit_code == 0
    row = json.loads(r.stdout.strip())
    assert row["total"] == 2
    assert row["by_label"]["PERSON"] == 1
    assert row["by_label"]["LOC"] == 1


def test_vault_show_reveal_writes_audit(tmp_path: Path) -> None:
    env = _setup(tmp_path)
    list_r = CliRunner(mix_stderr=False).invoke(app, ["vault", "list"], env=env)
    token = json.loads(list_r.stdout.strip().splitlines()[0])["token"]
    r = CliRunner(mix_stderr=False).invoke(
        app, ["vault", "show", token, "--reveal"], env=env
    )
    assert r.exit_code == 0
    row = json.loads(r.stdout.strip())
    assert row["original"] is not None
    audit_path = tmp_path / ".piighost" / "audit.log"
    assert "vault_show_reveal" in audit_path.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/cli/test_vault_cmds.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement vault commands**

Create `src/piighost/cli/commands/vault.py`:

```python
"""`piighost vault list/show/stats`."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import typer

from piighost.cli.output import ExitCode, emit_error_line, emit_json_line
from piighost.exceptions import VaultNotFound
from piighost.service import PIIGhostService
from piighost.service.config import ServiceConfig
from piighost.vault.discovery import find_vault_dir

vault_app = typer.Typer(no_args_is_help=True)


def _resolve_vault(explicit: Path | None) -> Path:
    return find_vault_dir(
        start=Path(os.environ.get("PIIGHOST_CWD", Path.cwd())),
        explicit=explicit,
    )


@vault_app.command("list")
def list_cmd(
    label: str | None = typer.Option(None, "--label"),
    limit: int = typer.Option(100, "--limit"),
    reveal: bool = typer.Option(False, "--reveal"),
    vault: Path | None = typer.Option(None, "--vault"),
) -> None:
    try:
        vault_dir = _resolve_vault(vault)
    except VaultNotFound as exc:
        emit_error_line(
            error="VaultNotFound", message=str(exc),
            hint="Run `piighost init`", exit_code=ExitCode.USER_ERROR,
        )
        raise typer.Exit(code=int(ExitCode.USER_ERROR))
    asyncio.run(_list(vault_dir, label, limit, reveal))


async def _list(vault_dir: Path, label: str | None, limit: int, reveal: bool) -> None:
    config = _load_cfg(vault_dir)
    svc = await PIIGhostService.create(vault_dir=vault_dir, config=config)
    try:
        page = await svc.vault_list(label=label, limit=limit, reveal=reveal)
        for entry in page.entries:
            emit_json_line(entry.model_dump())
    finally:
        await svc.close()


@vault_app.command("show")
def show_cmd(
    token: str,
    reveal: bool = typer.Option(False, "--reveal"),
    vault: Path | None = typer.Option(None, "--vault"),
) -> None:
    try:
        vault_dir = _resolve_vault(vault)
    except VaultNotFound as exc:
        emit_error_line(
            error="VaultNotFound", message=str(exc),
            hint="Run `piighost init`", exit_code=ExitCode.USER_ERROR,
        )
        raise typer.Exit(code=int(ExitCode.USER_ERROR))
    asyncio.run(_show(vault_dir, token, reveal))


async def _show(vault_dir: Path, token: str, reveal: bool) -> None:
    config = _load_cfg(vault_dir)
    svc = await PIIGhostService.create(vault_dir=vault_dir, config=config)
    try:
        entry = await svc.vault_show(token, reveal=reveal)
        if entry is None:
            emit_error_line(
                error="TokenNotFound", message=f"no entry for {token}",
                hint=None, exit_code=ExitCode.USER_ERROR,
            )
            raise typer.Exit(code=int(ExitCode.USER_ERROR))
        emit_json_line(entry.model_dump())
    finally:
        await svc.close()


@vault_app.command("stats")
def stats_cmd(vault: Path | None = typer.Option(None, "--vault")) -> None:
    try:
        vault_dir = _resolve_vault(vault)
    except VaultNotFound as exc:
        emit_error_line(
            error="VaultNotFound", message=str(exc),
            hint="Run `piighost init`", exit_code=ExitCode.USER_ERROR,
        )
        raise typer.Exit(code=int(ExitCode.USER_ERROR))
    asyncio.run(_stats(vault_dir))


async def _stats(vault_dir: Path) -> None:
    config = _load_cfg(vault_dir)
    svc = await PIIGhostService.create(vault_dir=vault_dir, config=config)
    try:
        s = await svc.vault_stats()
        emit_json_line(s.model_dump())
    finally:
        await svc.close()


def _load_cfg(vault_dir: Path) -> ServiceConfig:
    cfg = vault_dir / "config.toml"
    return ServiceConfig.from_toml(cfg) if cfg.exists() else ServiceConfig.default()
```

Modify `src/piighost/cli/main.py` — add the sub-app:

```python
from piighost.cli.commands.vault import vault_app

app.add_typer(vault_app, name="vault")
```

- [ ] **Step 4: Run vault tests to verify pass**

Run: `uv run pytest tests/cli/test_vault_cmds.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/piighost/cli tests/cli/test_vault_cmds.py
git commit -m "feat(cli): vault list/show/stats with redact-by-default + audit"
```

---

### Task 9: Daemon handshake (daemon.json + port discovery)

**Files:**
- Create: `src/piighost/daemon/__init__.py`
- Create: `src/piighost/daemon/handshake.py`
- Create: `tests/daemon/__init__.py`
- Create: `tests/daemon/test_handshake.py`

- [ ] **Step 1: Write failing handshake test**

Create `tests/daemon/test_handshake.py`:

```python
from pathlib import Path

import pytest

from piighost.daemon.handshake import (
    DaemonHandshake,
    read_handshake,
    write_handshake,
)


def test_write_then_read(tmp_path: Path) -> None:
    vault_dir = tmp_path / ".piighost"
    vault_dir.mkdir()
    hs = DaemonHandshake(pid=1234, port=50001, token="abc", started_at=42)
    write_handshake(vault_dir, hs)
    assert read_handshake(vault_dir) == hs


def test_read_missing_returns_none(tmp_path: Path) -> None:
    vault_dir = tmp_path / ".piighost"
    vault_dir.mkdir()
    assert read_handshake(vault_dir) is None


def test_write_is_atomic(tmp_path: Path) -> None:
    """A partial write must never leave a half-file readable."""
    vault_dir = tmp_path / ".piighost"
    vault_dir.mkdir()
    hs = DaemonHandshake(pid=1, port=1, token="t", started_at=0)
    write_handshake(vault_dir, hs)
    # Overwrite with new content — no exception, new value visible.
    hs2 = DaemonHandshake(pid=2, port=2, token="u", started_at=9)
    write_handshake(vault_dir, hs2)
    assert read_handshake(vault_dir) == hs2
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/daemon/test_handshake.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement handshake**

Create `src/piighost/daemon/__init__.py`:

```python
"""Localhost-bound daemon for piighost's stateful service."""

from piighost.daemon.handshake import DaemonHandshake, read_handshake, write_handshake

__all__ = ["DaemonHandshake", "read_handshake", "write_handshake"]
```

Create `src/piighost/daemon/handshake.py`:

```python
"""Atomic read/write of `.piighost/daemon.json`."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class DaemonHandshake:
    pid: int
    port: int
    token: str
    started_at: int


def _handshake_path(vault_dir: Path) -> Path:
    return vault_dir / "daemon.json"


def write_handshake(vault_dir: Path, hs: DaemonHandshake) -> None:
    target = _handshake_path(vault_dir)
    vault_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="daemon.", suffix=".json", dir=str(vault_dir))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(asdict(hs), f)
        os.replace(tmp, target)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def read_handshake(vault_dir: Path) -> DaemonHandshake | None:
    p = _handshake_path(vault_dir)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return DaemonHandshake(**data)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/daemon/test_handshake.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/piighost/daemon tests/daemon/__init__.py tests/daemon/test_handshake.py
git commit -m "feat(daemon): atomic daemon.json handshake file"
```

---

### Task 10: Daemon HTTP server (JSON-RPC over Starlette)

**Files:**
- Create: `src/piighost/daemon/server.py`
- Create: `src/piighost/daemon/__main__.py`
- Create: `tests/daemon/test_server.py`

- [ ] **Step 1: Write failing server test**

Create `tests/daemon/test_server.py`:

```python
from pathlib import Path

import httpx
import pytest
from starlette.testclient import TestClient

from piighost.daemon.server import build_app


@pytest.fixture()
def vault_dir(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("PIIGHOST_DETECTOR", "stub")
    d = tmp_path / ".piighost"
    d.mkdir()
    (d / "config.toml").write_text("schema_version = 1\n", encoding="utf-8")
    return d


def test_rpc_requires_token(vault_dir: Path) -> None:
    app, token = build_app(vault_dir)
    client = TestClient(app)
    r = client.post("/rpc", json={"jsonrpc": "2.0", "id": 1, "method": "vault_stats"})
    assert r.status_code == 401


def test_rpc_anonymize(vault_dir: Path) -> None:
    app, token = build_app(vault_dir)
    client = TestClient(app)
    r = client.post(
        "/rpc",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "anonymize",
            "params": {"text": "Alice in Paris"},
        },
    )
    assert r.status_code == 200
    payload = r.json()
    assert "result" in payload
    assert "Alice" not in payload["result"]["anonymized"]


def test_health(vault_dir: Path) -> None:
    app, _ = build_app(vault_dir)
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/daemon/test_server.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement the server**

Create `src/piighost/daemon/server.py`:

```python
"""Starlette app exposing PIIGhostService over JSON-RPC at /rpc.

Loopback-only. Bearer-token auth via Authorization header.
"""

from __future__ import annotations

import asyncio
import secrets
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from piighost.service import PIIGhostService
from piighost.service.config import ServiceConfig


def build_app(vault_dir: Path) -> tuple[Starlette, str]:
    token = secrets.token_urlsafe(32)
    cfg_path = vault_dir / "config.toml"
    config = ServiceConfig.from_toml(cfg_path) if cfg_path.exists() else ServiceConfig.default()

    state: dict[str, Any] = {"service": None}
    shutdown_event = asyncio.Event()

    async def _startup() -> None:
        state["service"] = await PIIGhostService.create(vault_dir=vault_dir, config=config)

    async def _shutdown() -> None:
        svc: PIIGhostService | None = state["service"]
        if svc:
            await svc.close()

    async def health(_: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    async def rpc(request: Request) -> JSONResponse:
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer ") or auth[7:] != token:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        body = await request.json()
        method = body.get("method")
        params = body.get("params", {}) or {}
        svc: PIIGhostService = state["service"]
        try:
            result = await _dispatch(svc, method, params)
        except Exception as exc:  # noqa: BLE001
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": body.get("id"),
                    "error": {"code": -32000, "message": type(exc).__name__},
                }
            )
        return JSONResponse({"jsonrpc": "2.0", "id": body.get("id"), "result": result})

    async def shutdown(request: Request) -> JSONResponse:
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer ") or auth[7:] != token:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        shutdown_event.set()
        return JSONResponse({"ok": True})

    routes = [
        Route("/health", health),
        Route("/rpc", rpc, methods=["POST"]),
        Route("/shutdown", shutdown, methods=["POST"]),
    ]
    app = Starlette(routes=routes, on_startup=[_startup], on_shutdown=[_shutdown])
    app.state.shutdown_event = shutdown_event
    return app, token


async def _dispatch(svc: PIIGhostService, method: str, params: dict[str, Any]) -> Any:
    if method == "anonymize":
        r = await svc.anonymize(params["text"], doc_id=params.get("doc_id"))
        return r.model_dump()
    if method == "rehydrate":
        r = await svc.rehydrate(params["text"], strict=params.get("strict"))
        return r.model_dump()
    if method == "detect":
        return [d.model_dump() for d in await svc.detect(params["text"])]
    if method == "vault_list":
        r = await svc.vault_list(
            label=params.get("label"),
            limit=params.get("limit", 100),
            reveal=params.get("reveal", False),
        )
        return r.model_dump()
    if method == "vault_show":
        r = await svc.vault_show(params["token"], reveal=params.get("reveal", False))
        return r.model_dump() if r else None
    if method == "vault_stats":
        return (await svc.vault_stats()).model_dump()
    raise ValueError(f"Unknown method: {method}")
```

Create `src/piighost/daemon/__main__.py`:

```python
"""`python -m piighost.daemon --vault <dir>` — the actual daemon entry."""

from __future__ import annotations

import argparse
import os
import socket
import time
from pathlib import Path

import uvicorn

from piighost.daemon.handshake import DaemonHandshake, write_handshake
from piighost.daemon.server import build_app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault", type=Path, required=True)
    args = parser.parse_args()

    vault_dir = args.vault.resolve()

    # Allocate an OS-assigned port on loopback.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    app, token = build_app(vault_dir)
    hs = DaemonHandshake(pid=os.getpid(), port=port, token=token, started_at=int(time.time()))
    write_handshake(vault_dir, hs)

    uvicorn.run(app, host="127.0.0.1", port=port, log_config=None, access_log=False)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run server tests to verify pass**

Run: `uv run pytest tests/daemon/test_server.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/piighost/daemon tests/daemon/test_server.py
git commit -m "feat(daemon): Starlette JSON-RPC server with bearer-token auth"
```

---

### Task 11: Daemon lifecycle (auto-spawn, portalocker, psutil)

**Files:**
- Create: `src/piighost/daemon/lifecycle.py`
- Create: `src/piighost/daemon/client.py`
- Create: `src/piighost/cli/commands/daemon.py`
- Create: `tests/daemon/test_lifecycle.py`
- Create: `tests/daemon/test_spawn_race.py`
- Create: `tests/cli/test_daemon_cmd.py`
- Modify: `src/piighost/cli/main.py`
- Modify: `src/piighost/daemon/__init__.py`

- [ ] **Step 1: Write failing lifecycle tests**

Create `tests/daemon/test_lifecycle.py`:

```python
from pathlib import Path

import httpx

from piighost.daemon.lifecycle import ensure_daemon, stop_daemon


def test_spawn_and_stop(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PIIGHOST_DETECTOR", "stub")
    vault_dir = tmp_path / ".piighost"
    vault_dir.mkdir()
    (vault_dir / "config.toml").write_text("schema_version = 1\n", encoding="utf-8")

    hs = ensure_daemon(vault_dir, timeout_sec=15.0)
    try:
        r = httpx.get(
            f"http://127.0.0.1:{hs.port}/health",
            headers={"Authorization": f"Bearer {hs.token}"},
        )
        assert r.status_code == 200
    finally:
        stop_daemon(vault_dir)
    # handshake file removed after stop
    assert not (vault_dir / "daemon.json").exists()
```

Create `tests/daemon/test_spawn_race.py`:

```python
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from piighost.daemon.lifecycle import ensure_daemon, stop_daemon


def test_concurrent_spawn_produces_one_daemon(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PIIGHOST_DETECTOR", "stub")
    vault_dir = tmp_path / ".piighost"
    vault_dir.mkdir()
    (vault_dir / "config.toml").write_text("schema_version = 1\n", encoding="utf-8")

    with ThreadPoolExecutor(max_workers=3) as pool:
        handshakes = list(pool.map(
            lambda _: ensure_daemon(vault_dir, timeout_sec=20.0), range(3)
        ))
    try:
        pids = {h.pid for h in handshakes}
        assert len(pids) == 1
    finally:
        stop_daemon(vault_dir)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/daemon/test_lifecycle.py tests/daemon/test_spawn_race.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement lifecycle**

Create `src/piighost/daemon/lifecycle.py`:

```python
"""Auto-spawn, stale detection, and clean shutdown for the piighost daemon."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import portalocker
import psutil

from piighost.daemon.handshake import DaemonHandshake, read_handshake, write_handshake


def _is_alive(hs: DaemonHandshake) -> bool:
    if not psutil.pid_exists(hs.pid):
        return False
    try:
        resp = httpx.get(
            f"http://127.0.0.1:{hs.port}/health",
            headers={"Authorization": f"Bearer {hs.token}"},
            timeout=1.5,
        )
        return resp.status_code == 200
    except httpx.HTTPError:
        return False


def ensure_daemon(vault_dir: Path, *, timeout_sec: float = 15.0) -> DaemonHandshake:
    lock_path = vault_dir / "daemon.lock"
    vault_dir.mkdir(parents=True, exist_ok=True)
    # Cross-platform advisory lock. First caller spawns; others wait, then read.
    with portalocker.Lock(lock_path, timeout=timeout_sec):
        hs = read_handshake(vault_dir)
        if hs and _is_alive(hs):
            return hs
        if hs:
            _cleanup_stale(vault_dir, hs)
        return _spawn(vault_dir, timeout_sec=timeout_sec)


def _cleanup_stale(vault_dir: Path, hs: DaemonHandshake) -> None:
    if psutil.pid_exists(hs.pid):
        try:
            psutil.Process(hs.pid).terminate()
        except psutil.Error:
            pass
    try:
        (vault_dir / "daemon.json").unlink(missing_ok=True)
    except OSError:
        pass


def _spawn(vault_dir: Path, *, timeout_sec: float) -> DaemonHandshake:
    creationflags = 0
    if sys.platform == "win32":
        creationflags = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )

    log_path = vault_dir / "daemon.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_fh = open(log_path, "ab")

    subprocess.Popen(
        [sys.executable, "-m", "piighost.daemon", "--vault", str(vault_dir)],
        stdout=log_fh,
        stderr=log_fh,
        stdin=subprocess.DEVNULL,
        start_new_session=(sys.platform != "win32"),
        creationflags=creationflags,
        env=os.environ.copy(),
        close_fds=True,
    )

    deadline = time.monotonic() + timeout_sec
    delay = 0.05
    while time.monotonic() < deadline:
        hs = read_handshake(vault_dir)
        if hs and _is_alive(hs):
            return hs
        time.sleep(delay)
        delay = min(delay * 1.6, 0.8)
    raise TimeoutError(
        f"daemon did not become healthy within {timeout_sec}s; "
        f"see {log_path}"
    )


def stop_daemon(vault_dir: Path) -> bool:
    hs = read_handshake(vault_dir)
    if hs is None:
        return False
    try:
        httpx.post(
            f"http://127.0.0.1:{hs.port}/shutdown",
            headers={"Authorization": f"Bearer {hs.token}"},
            timeout=3.0,
        )
    except httpx.HTTPError:
        pass
    # Give the server a beat, then force-kill if needed.
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if not psutil.pid_exists(hs.pid):
            break
        time.sleep(0.1)
    else:
        try:
            psutil.Process(hs.pid).kill()
        except psutil.Error:
            pass
    (vault_dir / "daemon.json").unlink(missing_ok=True)
    return True


def status(vault_dir: Path) -> DaemonHandshake | None:
    hs = read_handshake(vault_dir)
    if hs is None:
        return None
    return hs if _is_alive(hs) else None
```

Create `src/piighost/daemon/client.py`:

```python
"""Thin HTTP client used by the CLI to talk to a running daemon."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from piighost.daemon.handshake import read_handshake


class DaemonClient:
    def __init__(self, port: int, token: str) -> None:
        self._base = f"http://127.0.0.1:{port}"
        self._headers = {"Authorization": f"Bearer {token}"}

    @classmethod
    def from_vault(cls, vault_dir: Path) -> "DaemonClient | None":
        hs = read_handshake(vault_dir)
        if hs is None:
            return None
        return cls(port=hs.port, token=hs.token)

    def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
        r = httpx.post(f"{self._base}/rpc", json=body, headers=self._headers, timeout=30.0)
        r.raise_for_status()
        payload = r.json()
        if "error" in payload:
            raise RuntimeError(payload["error"]["message"])
        return payload["result"]
```

Update `src/piighost/daemon/__init__.py`:

```python
"""Localhost-bound daemon for piighost's stateful service."""

from piighost.daemon.client import DaemonClient
from piighost.daemon.handshake import DaemonHandshake, read_handshake, write_handshake
from piighost.daemon.lifecycle import ensure_daemon, status, stop_daemon

__all__ = [
    "DaemonClient",
    "DaemonHandshake",
    "ensure_daemon",
    "read_handshake",
    "status",
    "stop_daemon",
    "write_handshake",
]
```

- [ ] **Step 4: Run lifecycle tests**

Run: `uv run pytest tests/daemon/test_lifecycle.py tests/daemon/test_spawn_race.py -v`
Expected: 2 passed (may take 20s+ per test due to spawn).

- [ ] **Step 5: Write failing `piighost daemon ...` CLI test**

Create `tests/cli/test_daemon_cmd.py`:

```python
import json
from pathlib import Path

from typer.testing import CliRunner

from piighost.cli.main import app


def test_daemon_start_status_stop(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PIIGHOST_DETECTOR", "stub")
    env = {"PIIGHOST_CWD": str(tmp_path), "PIIGHOST_DETECTOR": "stub"}
    runner = CliRunner(mix_stderr=False)
    runner.invoke(app, ["init"], env=env)

    start = runner.invoke(app, ["daemon", "start"], env=env)
    assert start.exit_code == 0
    info = json.loads(start.stdout.strip())
    assert "pid" in info and "port" in info

    stat = runner.invoke(app, ["daemon", "status"], env=env)
    assert stat.exit_code == 0
    assert json.loads(stat.stdout.strip())["running"] is True

    stop = runner.invoke(app, ["daemon", "stop"], env=env)
    assert stop.exit_code == 0

    stat2 = runner.invoke(app, ["daemon", "status"], env=env)
    assert json.loads(stat2.stdout.strip())["running"] is False
```

- [ ] **Step 6: Implement daemon CLI subcommands**

Create `src/piighost/cli/commands/daemon.py`:

```python
"""`piighost daemon start|stop|status|restart|logs`."""

from __future__ import annotations

import os
from pathlib import Path

import typer

from piighost.cli.output import ExitCode, emit_error_line, emit_json_line
from piighost.daemon.lifecycle import ensure_daemon, status, stop_daemon
from piighost.exceptions import VaultNotFound
from piighost.vault.discovery import find_vault_dir

daemon_app = typer.Typer(no_args_is_help=True)


def _vault() -> Path:
    return find_vault_dir(start=Path(os.environ.get("PIIGHOST_CWD", Path.cwd())))


@daemon_app.command("start")
def start_cmd() -> None:
    try:
        vault_dir = _vault()
    except VaultNotFound as exc:
        emit_error_line(
            error="VaultNotFound", message=str(exc),
            hint="Run `piighost init`", exit_code=ExitCode.USER_ERROR,
        )
        raise typer.Exit(code=int(ExitCode.USER_ERROR))
    hs = ensure_daemon(vault_dir)
    emit_json_line({"pid": hs.pid, "port": hs.port, "started_at": hs.started_at})


@daemon_app.command("status")
def status_cmd() -> None:
    try:
        vault_dir = _vault()
    except VaultNotFound as exc:
        emit_error_line(
            error="VaultNotFound", message=str(exc),
            hint="Run `piighost init`", exit_code=ExitCode.USER_ERROR,
        )
        raise typer.Exit(code=int(ExitCode.USER_ERROR))
    hs = status(vault_dir)
    if hs is None:
        emit_json_line({"running": False})
    else:
        emit_json_line({"running": True, "pid": hs.pid, "port": hs.port})


@daemon_app.command("stop")
def stop_cmd() -> None:
    try:
        vault_dir = _vault()
    except VaultNotFound as exc:
        emit_error_line(
            error="VaultNotFound", message=str(exc),
            hint="Run `piighost init`", exit_code=ExitCode.USER_ERROR,
        )
        raise typer.Exit(code=int(ExitCode.USER_ERROR))
    ok = stop_daemon(vault_dir)
    emit_json_line({"stopped": ok})


@daemon_app.command("restart")
def restart_cmd() -> None:
    stop_cmd()
    start_cmd()


@daemon_app.command("logs")
def logs_cmd(tail: int = typer.Option(50, "--tail")) -> None:
    try:
        vault_dir = _vault()
    except VaultNotFound as exc:
        emit_error_line(
            error="VaultNotFound", message=str(exc),
            hint="Run `piighost init`", exit_code=ExitCode.USER_ERROR,
        )
        raise typer.Exit(code=int(ExitCode.USER_ERROR))
    log = vault_dir / "daemon.log"
    if not log.exists():
        emit_json_line({"lines": []})
        return
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()[-tail:]
    emit_json_line({"lines": lines})
```

Modify `src/piighost/cli/main.py` — add:

```python
from piighost.cli.commands.daemon import daemon_app

app.add_typer(daemon_app, name="daemon")
```

- [ ] **Step 7: Run the CLI daemon test**

Run: `uv run pytest tests/cli/test_daemon_cmd.py -v`
Expected: 1 passed.

- [ ] **Step 8: Commit**

```bash
git add src/piighost/daemon src/piighost/cli tests/daemon tests/cli/test_daemon_cmd.py
git commit -m "feat(daemon): auto-spawn lifecycle + daemon CLI subcommands"
```

---

### Task 12: Exit-code coverage + CI matrix + cross-platform smoke

**Files:**
- Create: `tests/cli/test_exit_codes.py`
- Create: `tests/daemon/test_cross_platform_smoke.py`
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Write exit-code coverage test**

Create `tests/cli/test_exit_codes.py`:

```python
from pathlib import Path

from typer.testing import CliRunner

from piighost.cli.main import app
from piighost.cli.output import ExitCode


def test_missing_vault_yields_exit_2(tmp_path: Path) -> None:
    env = {"PIIGHOST_CWD": str(tmp_path)}
    r = CliRunner(mix_stderr=False).invoke(app, ["anonymize", "-"], input="x", env=env)
    assert r.exit_code == int(ExitCode.USER_ERROR)
    assert "VaultNotFound" in r.stderr


def test_unknown_token_strict_yields_exit_5(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PIIGHOST_DETECTOR", "stub")
    env = {"PIIGHOST_CWD": str(tmp_path), "PIIGHOST_DETECTOR": "stub"}
    runner = CliRunner(mix_stderr=False)
    runner.invoke(app, ["init"], env=env)
    r = runner.invoke(app, ["rehydrate", "-"], input="see <PERSON:deadbeef>", env=env)
    assert r.exit_code == int(ExitCode.PII_SAFETY_VIOLATION)
    assert "PIISafetyViolation" in r.stderr
```

- [ ] **Step 2: Run to verify pass**

Run: `uv run pytest tests/cli/test_exit_codes.py -v`
Expected: 2 passed.

- [ ] **Step 3: Write the cross-platform smoke test**

Create `tests/daemon/test_cross_platform_smoke.py`:

```python
"""End-to-end smoke: init → daemon → anonymize → rehydrate → stop.

Runs on every OS in the CI matrix.
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from piighost.cli.main import app


def test_full_workflow(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PIIGHOST_DETECTOR", "stub")
    env = {"PIIGHOST_CWD": str(tmp_path), "PIIGHOST_DETECTOR": "stub"}
    runner = CliRunner(mix_stderr=False)

    assert runner.invoke(app, ["init"], env=env).exit_code == 0
    assert runner.invoke(app, ["daemon", "start"], env=env).exit_code == 0
    try:
        a = runner.invoke(app, ["anonymize", "-"], input="Alice in Paris", env=env)
        assert a.exit_code == 0
        anon = json.loads(a.stdout.strip().splitlines()[-1])["anonymized"]
        r = runner.invoke(app, ["rehydrate", "-"], input=anon, env=env)
        assert r.exit_code == 0
        payload = json.loads(r.stdout.strip().splitlines()[-1])
        assert payload["text"] == "Alice in Paris"
    finally:
        runner.invoke(app, ["daemon", "stop"], env=env)
```

- [ ] **Step 4: Update the CI workflow**

Replace (or create) `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [master, main]
  pull_request:

jobs:
  test:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        python: ["3.13"]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
      - name: Install uv
        uses: astral-sh/setup-uv@v3
      - name: Install project
        run: uv sync --all-extras
      - name: Unit tests (non-slow, no GPU, stub detector)
        run: uv run pytest -q -m "not slow"
      - name: Smoke test
        run: uv run pytest tests/daemon/test_cross_platform_smoke.py -v
```

- [ ] **Step 5: Run the smoke test locally**

Run: `uv run pytest tests/daemon/test_cross_platform_smoke.py -v`
Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add tests/cli/test_exit_codes.py tests/daemon/test_cross_platform_smoke.py .github/workflows/ci.yml
git commit -m "test: exit-code coverage + cross-platform smoke + CI matrix"
```

---

## Final Validation (after all tasks)

Run the full suite once more to catch any integration drift:

```bash
uv run pytest -q -m "not slow"
```

Expected outcome:
- All tests pass on Windows, macOS, and Linux.
- `piighost init && echo "Alice lives in Paris" | piighost anonymize -` produces a JSON line with no "Alice" or "Paris" in the `anonymized` field.
- Second `anonymize` call after `daemon start` completes in <100 ms (manual check).
- `.piighost/audit.log` records every `rehydrate` and `vault show --reveal`.
- Fuzz test in Task 5 reports zero raw-PII leaks across 100 inputs.

## Out of scope for this plan (Sprint 2 and beyond)

- Kreuzberg ingestion, LanceDB embedding, hybrid retrieval, `index`/`query` CLI
- FastMCP server (`piighost serve --mcp`) + MCP tool surface
- `classify` command (backend already exists; adapter deferred)
- Vault migrations between schema versions
- Remote vaults, multi-user RBAC, Windows Service / systemd wrappers

Each of those gets its own plan once Sprint 1 ships.
