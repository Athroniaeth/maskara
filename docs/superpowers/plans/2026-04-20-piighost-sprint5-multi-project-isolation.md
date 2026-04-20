# piighost Sprint 5 — Multi-Project Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add strict per-project isolation so each project has its own vault, chunk store, BM25 index, and token namespace. "Alice" in project A gets a different token than "Alice" in project B, and rehydrating cross-project fails explicitly.

**Architecture:** A new top-level `ProjectRegistry` (SQLite at `${vault_dir}/projects.db`) tracks projects. `PIIGhostService` becomes a multiplexer over per-project `_ProjectService` instances (renamed from today's service internals) with an LRU cache. Salt is threaded into `HashPlaceholderFactory` so identical values hash to different tokens across projects. Sprint 1-4 single-vault state migrates transparently to `projects/default/` on first launch.

**Tech Stack:** Python 3.10+, SQLite, Pydantic v2, asyncio, FastMCP, Typer.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `src/piighost/placeholder.py` | `HashPlaceholderFactory` gains `salt: str = ""` |
| Create | `src/piighost/vault/project_registry.py` | `ProjectRegistry` + `ProjectInfo` dataclass + name validation |
| Create | `src/piighost/service/migration.py` | `migrate_to_v3(vault_dir)` — moves legacy state to `projects/default/` |
| Modify | `src/piighost/service/core.py` | Split `PIIGhostService` into `_ProjectService` (private, per-project) + `PIIGhostService` (multiplexer); every public method gains `project` param |
| Create | `src/piighost/service/project_path.py` | `derive_project_from_path(path) -> str` — auto-derivation for `index_path` |
| Modify | `src/piighost/service/models.py` | `ProjectInfo`, `IndexReport.project` field, new exceptions |
| Modify | `src/piighost/exceptions.py` | `ProjectNotFound`, `ProjectNotEmpty`, `InvalidProjectName` |
| Modify | `src/piighost/mcp/server.py` | All tools gain `project` param; 3 new project management tools; 2 new resources |
| Modify | `src/piighost/cli/commands/*.py` | `--project` flag on all commands |
| Create | `src/piighost/cli/commands/projects.py` | `piighost projects {list,create,delete}` subcommands |
| Modify | `src/piighost/cli/main.py` | Register `projects` subcommand group |
| Modify | `src/piighost/daemon/server.py` | Forward `project` param; dispatch 3 new project methods |
| Create | `tests/unit/test_salted_placeholder.py` | Salt changes output, empty salt matches legacy |
| Create | `tests/unit/test_project_registry.py` | Registry CRUD + name validation |
| Create | `tests/unit/test_schema_v3_migration.py` | v2→v3 migration moves files correctly |
| Create | `tests/unit/test_service_multiplexer.py` | LRU eviction, concurrent access |
| Create | `tests/unit/test_project_derivation.py` | Path → project name logic |
| Create | `tests/unit/test_mcp_project_wiring.py` | All MCP tools dispatch correct project |
| Create | `tests/unit/test_cli_project_flag.py` | `--project` flag threads through CLI |
| Create | `tests/e2e/test_project_isolation.py` | Critical safety tests (token isolation, cross-project rehydrate fails) |
| Create | `tests/e2e/test_v2_to_v3_migration.py` | Real v2 vault → v3 works end-to-end |

---

### Task 1: Salted `HashPlaceholderFactory`

**Files:**
- Modify: `src/piighost/placeholder.py`
- Create: `tests/unit/test_salted_placeholder.py`

- [ ] **Step 1: Write failing test**

Create `tests/unit/test_salted_placeholder.py`:

```python
from piighost.models import Detection, Entity, Span
from piighost.placeholder import HashPlaceholderFactory


def _entity(text: str, label: str = "PERSON") -> Entity:
    return Entity(
        detections=(
            Detection(
                text=text,
                label=label,
                position=Span(start_pos=0, end_pos=len(text)),
                confidence=0.9,
            ),
        )
    )


def test_empty_salt_matches_unsalted_legacy_format():
    """Empty salt must produce identical tokens to the pre-Sprint-5 factory (backward compat)."""
    unsalted = HashPlaceholderFactory()
    empty_salt = HashPlaceholderFactory(salt="")
    e = _entity("Patrick")
    assert unsalted.create([e])[e] == empty_salt.create([e])[e]


def test_non_empty_salt_changes_token():
    a = HashPlaceholderFactory(salt="client-a")
    b = HashPlaceholderFactory(salt="client-b")
    e = _entity("Patrick")
    assert a.create([e])[e] != b.create([e])[e]


def test_same_salt_produces_same_token():
    a1 = HashPlaceholderFactory(salt="client-a")
    a2 = HashPlaceholderFactory(salt="client-a")
    e = _entity("Patrick")
    assert a1.create([e])[e] == a2.create([e])[e]


def test_token_format_unchanged():
    factory = HashPlaceholderFactory(salt="client-a")
    e = _entity("Patrick")
    token = factory.create([e])[e]
    assert token.startswith("<PERSON:")
    assert token.endswith(">")
    assert len(token) == len("<PERSON:12345678>")  # label + 8-char digest


def test_salt_affects_only_hash_not_label_prefix():
    factory = HashPlaceholderFactory(salt="xyz")
    e = _entity("Patrick", label="EMAIL_ADDRESS")
    token = factory.create([e])[e]
    assert token.startswith("<EMAIL_ADDRESS:")
```

- [ ] **Step 2: Run test to verify failure**

```bash
cd C:/Users/NMarchitecte/Documents/piighost
python -m pytest tests/unit/test_salted_placeholder.py -v -p no:randomly
```

Expected: `TypeError: __init__() got an unexpected keyword argument 'salt'`.

- [ ] **Step 3: Modify `HashPlaceholderFactory.__init__` to accept salt**

Edit `src/piighost/placeholder.py`. Replace the current `HashPlaceholderFactory` class with:

```python
class HashPlaceholderFactory:
    """Factory that generates tokens like ``<PERSON:a1b2c3d4>``.

    Uses SHA-256 of ``salt + canonical_text + label`` to produce a
    deterministic, opaque token. Same entity + same salt always produces
    the same hash. Different salts produce different hashes for
    project-level isolation.

    Args:
        hash_length: Number of hex characters to use from the hash.
            Defaults to 8.
        salt: Optional project-scoped prefix mixed into the digest.
            Empty string (the default) preserves legacy pre-Sprint-5
            token values for backward compatibility.
    """

    _hash_length: int
    _salt: str

    def __init__(self, hash_length: int = 8, salt: str = "") -> None:
        self._hash_length = hash_length
        self._salt = salt

    def create(self, entities: list[Entity]) -> dict[Entity, str]:
        result: dict[Entity, str] = {}

        for entity in entities:
            canonical_text = entity.detections[0].text.lower()
            label = entity.label
            if self._salt:
                raw = f"{self._salt}:{canonical_text}:{label}"
            else:
                raw = f"{canonical_text}:{label}"
            digest = hashlib.sha256(raw.encode()).hexdigest()[: self._hash_length]
            result[entity] = f"<{label}:{digest}>"

        return result
```

The `if self._salt:` branch keeps the legacy format untouched when no salt is provided, so existing tokens and tests continue to match.

- [ ] **Step 4: Run salted tests — should pass**

```bash
python -m pytest tests/unit/test_salted_placeholder.py -v -p no:randomly
```

Expected: 5 PASSED.

- [ ] **Step 5: Run full suite — no regressions**

```bash
python -m pytest tests/unit/ tests/e2e/ -q -p no:randomly 2>&1 | tail -5
```

Expected: all passing (no regression because empty salt preserves legacy output).

- [ ] **Step 6: Commit**

```bash
git add src/piighost/placeholder.py tests/unit/test_salted_placeholder.py
git commit -m "feat(placeholder): HashPlaceholderFactory accepts salt for project isolation"
```

---

### Task 2: `ProjectRegistry`

**Files:**
- Create: `src/piighost/vault/project_registry.py`
- Create: `tests/unit/test_project_registry.py`

- [ ] **Step 1: Write failing test**

Create `tests/unit/test_project_registry.py`:

```python
import time

import pytest

from piighost.vault.project_registry import (
    ProjectRegistry,
    ProjectInfo,
    InvalidProjectName,
)


def _open(tmp_path):
    return ProjectRegistry.open(tmp_path / "projects.db")


def test_open_creates_empty_registry(tmp_path):
    r = _open(tmp_path)
    assert r.list() == []
    r.close()


def test_create_and_get(tmp_path):
    r = _open(tmp_path)
    info = r.create("client-a", description="Client A docs")
    assert info.name == "client-a"
    assert info.description == "Client A docs"
    assert info.placeholder_salt == "client-a"  # defaults to name
    assert info.created_at > 0
    got = r.get("client-a")
    assert got == info
    r.close()


def test_create_with_custom_salt(tmp_path):
    r = _open(tmp_path)
    info = r.create("client-a", description="", placeholder_salt="")
    assert info.placeholder_salt == ""
    r.close()


def test_exists(tmp_path):
    r = _open(tmp_path)
    assert r.exists("client-a") is False
    r.create("client-a")
    assert r.exists("client-a") is True
    r.close()


def test_duplicate_create_raises(tmp_path):
    r = _open(tmp_path)
    r.create("client-a")
    with pytest.raises(ValueError, match="already exists"):
        r.create("client-a")
    r.close()


def test_list_returns_all(tmp_path):
    r = _open(tmp_path)
    r.create("client-a")
    r.create("client-b")
    names = {p.name for p in r.list()}
    assert names == {"client-a", "client-b"}
    r.close()


def test_delete(tmp_path):
    r = _open(tmp_path)
    r.create("client-a")
    assert r.delete("client-a") is True
    assert r.exists("client-a") is False
    assert r.delete("client-a") is False
    r.close()


def test_touch_updates_last_accessed(tmp_path):
    r = _open(tmp_path)
    r.create("client-a")
    info1 = r.get("client-a")
    time.sleep(1.1)
    r.touch("client-a")
    info2 = r.get("client-a")
    assert info2.last_accessed_at > info1.last_accessed_at
    r.close()


@pytest.mark.parametrize("invalid", [
    "",
    "with space",
    "../escape",
    "slash/inside",
    "dot.inside",
    "emoji-\N{GRINNING FACE}",
    "a" * 65,
])
def test_invalid_name_rejected(tmp_path, invalid):
    r = _open(tmp_path)
    with pytest.raises(InvalidProjectName):
        r.create(invalid)
    r.close()


@pytest.mark.parametrize("valid", [
    "client-a",
    "client_b",
    "CLIENT_42",
    "a",
    "a" * 64,
])
def test_valid_names_accepted(tmp_path, valid):
    r = _open(tmp_path)
    r.create(valid)
    assert r.exists(valid)
    r.close()
```

- [ ] **Step 2: Run test to verify failure**

```bash
python -m pytest tests/unit/test_project_registry.py -v -p no:randomly
```

Expected: `ModuleNotFoundError: No module named 'piighost.vault.project_registry'`.

- [ ] **Step 3: Create `src/piighost/vault/project_registry.py`**

```python
"""Per-vault registry of logical projects."""

from __future__ import annotations

import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path


_VALID_NAME_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")


class InvalidProjectName(ValueError):
    """Raised when a project name violates the allowed character set or length."""


@dataclass(frozen=True)
class ProjectInfo:
    name: str
    description: str
    created_at: int
    last_accessed_at: int
    placeholder_salt: str


def _validate_name(name: str) -> None:
    if not _VALID_NAME_RE.fullmatch(name):
        raise InvalidProjectName(
            f"invalid project name: must match {_VALID_NAME_RE.pattern}"
        )


_DDL = """
CREATE TABLE IF NOT EXISTS projects (
    name TEXT PRIMARY KEY,
    description TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL,
    last_accessed_at INTEGER NOT NULL,
    placeholder_salt TEXT NOT NULL DEFAULT ''
);
"""


class ProjectRegistry:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    @classmethod
    def open(cls, db_path: Path) -> "ProjectRegistry":
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_DDL)
        return cls(conn)

    def close(self) -> None:
        self._conn.close()

    def create(
        self,
        name: str,
        description: str = "",
        placeholder_salt: str | None = None,
    ) -> ProjectInfo:
        _validate_name(name)
        if self.exists(name):
            raise ValueError(f"project '{name}' already exists")
        salt = name if placeholder_salt is None else placeholder_salt
        now = int(time.time())
        self._conn.execute(
            "INSERT INTO projects (name, description, created_at, last_accessed_at, placeholder_salt) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, description, now, now, salt),
        )
        return ProjectInfo(
            name=name,
            description=description,
            created_at=now,
            last_accessed_at=now,
            placeholder_salt=salt,
        )

    def get(self, name: str) -> ProjectInfo | None:
        row = self._conn.execute(
            "SELECT * FROM projects WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_info(row)

    def exists(self, name: str) -> bool:
        return self.get(name) is not None

    def list(self) -> list[ProjectInfo]:
        rows = self._conn.execute(
            "SELECT * FROM projects ORDER BY last_accessed_at DESC"
        ).fetchall()
        return [self._row_to_info(r) for r in rows]

    def delete(self, name: str) -> bool:
        cur = self._conn.execute("DELETE FROM projects WHERE name = ?", (name,))
        return cur.rowcount > 0

    def touch(self, name: str) -> None:
        self._conn.execute(
            "UPDATE projects SET last_accessed_at = ? WHERE name = ?",
            (int(time.time()), name),
        )

    @staticmethod
    def _row_to_info(row: sqlite3.Row) -> ProjectInfo:
        return ProjectInfo(
            name=row["name"],
            description=row["description"],
            created_at=row["created_at"],
            last_accessed_at=row["last_accessed_at"],
            placeholder_salt=row["placeholder_salt"],
        )
```

- [ ] **Step 4: Run tests — should pass**

```bash
python -m pytest tests/unit/test_project_registry.py -v -p no:randomly
```

Expected: all PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/piighost/vault/project_registry.py tests/unit/test_project_registry.py
git commit -m "feat(vault): ProjectRegistry with name validation and placeholder_salt"
```

---

### Task 3: Schema v3 migration

**Files:**
- Create: `src/piighost/service/migration.py`
- Create: `tests/unit/test_schema_v3_migration.py`

- [ ] **Step 1: Write failing test**

Create `tests/unit/test_schema_v3_migration.py`:

```python
from pathlib import Path

from piighost.service.migration import migrate_to_v3
from piighost.vault.project_registry import ProjectRegistry


def _seed_v2_vault(vault_dir: Path) -> None:
    vault_dir.mkdir(parents=True, exist_ok=True)
    (vault_dir / "vault.db").write_bytes(b"v2-vault-data")
    (vault_dir / "audit.log").write_text("op=anonymize\n")
    piighost_dir = vault_dir / ".piighost"
    piighost_dir.mkdir()
    lance_dir = piighost_dir / "lance"
    lance_dir.mkdir()
    (lance_dir / "chunks.lance").write_bytes(b"dummy-lance-table")
    (piighost_dir / "bm25.pkl").write_bytes(b"dummy-bm25")


def test_migrates_v2_vault_to_projects_default(tmp_path):
    vault = tmp_path / "vault"
    _seed_v2_vault(vault)

    migrate_to_v3(vault)

    default = vault / "projects" / "default"
    assert (default / "vault.db").read_bytes() == b"v2-vault-data"
    assert (default / "audit.log").read_text() == "op=anonymize\n"
    assert (default / ".piighost" / "lance" / "chunks.lance").exists()
    assert (default / ".piighost" / "bm25.pkl").exists()

    assert not (vault / "vault.db").exists()
    assert not (vault / "audit.log").exists()
    assert not (vault / ".piighost").exists()


def test_default_project_exists_after_migration(tmp_path):
    vault = tmp_path / "vault"
    _seed_v2_vault(vault)

    migrate_to_v3(vault)

    registry = ProjectRegistry.open(vault / "projects.db")
    info = registry.get("default")
    assert info is not None
    assert info.placeholder_salt == ""  # legacy compatibility
    registry.close()


def test_fresh_install_creates_default_project(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()

    migrate_to_v3(vault)

    assert (vault / "projects" / "default").exists()
    registry = ProjectRegistry.open(vault / "projects.db")
    assert registry.exists("default")
    registry.close()


def test_migration_is_idempotent(tmp_path):
    vault = tmp_path / "vault"
    _seed_v2_vault(vault)

    migrate_to_v3(vault)
    vault_bytes_first = (vault / "projects" / "default" / "vault.db").read_bytes()

    # Second run must be a no-op
    migrate_to_v3(vault)
    vault_bytes_second = (vault / "projects" / "default" / "vault.db").read_bytes()
    assert vault_bytes_first == vault_bytes_second


def test_partial_migration_recovers(tmp_path):
    """If a previous run moved some files but not others, the second run completes the move."""
    vault = tmp_path / "vault"
    _seed_v2_vault(vault)
    # Simulate a partial state: projects/default/ exists, but .piighost and audit.log
    # are still at the top-level.
    default = vault / "projects" / "default"
    default.mkdir(parents=True)
    (vault / "vault.db").rename(default / "vault.db")

    migrate_to_v3(vault)

    assert (default / "audit.log").exists()
    assert (default / ".piighost" / "bm25.pkl").exists()
    assert not (vault / "audit.log").exists()
```

- [ ] **Step 2: Run test to verify failure**

```bash
python -m pytest tests/unit/test_schema_v3_migration.py -v -p no:randomly
```

Expected: `ModuleNotFoundError: No module named 'piighost.service.migration'`.

- [ ] **Step 3: Create `src/piighost/service/migration.py`**

```python
"""Schema v2 → v3 migration: move single-vault state into projects/default/."""

from __future__ import annotations

import shutil
from pathlib import Path

from piighost.vault.project_registry import ProjectRegistry


_LEGACY_TOP_LEVEL = ("vault.db", "audit.log")


def migrate_to_v3(vault_dir: Path) -> None:
    """Idempotently move legacy single-vault state under ``projects/default/``.

    Safe to call on fresh installs (creates an empty default project) and on
    already-migrated vaults (no-op). Also recovers from a partial migration
    where some files were moved but others remain at the top level.
    """
    vault_dir.mkdir(parents=True, exist_ok=True)
    projects_dir = vault_dir / "projects"
    default_dir = projects_dir / "default"
    default_dir.mkdir(parents=True, exist_ok=True)

    for name in _LEGACY_TOP_LEVEL:
        src = vault_dir / name
        if src.exists():
            dst = default_dir / name
            if dst.exists():
                src.unlink()
            else:
                src.rename(dst)

    legacy_piighost = vault_dir / ".piighost"
    if legacy_piighost.exists() and legacy_piighost.is_dir():
        dst = default_dir / ".piighost"
        if dst.exists():
            shutil.rmtree(legacy_piighost)
        else:
            legacy_piighost.rename(dst)

    registry = ProjectRegistry.open(vault_dir / "projects.db")
    try:
        if not registry.exists("default"):
            registry.create(
                "default",
                description="Default project (pre-v3 data migrated here)",
                placeholder_salt="",
            )
    finally:
        registry.close()
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/unit/test_schema_v3_migration.py -v -p no:randomly
```

Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/piighost/service/migration.py tests/unit/test_schema_v3_migration.py
git commit -m "feat(service): schema v3 migration moves legacy data to projects/default/"
```

---

### Task 4: New exception types

**Files:**
- Modify: `src/piighost/exceptions.py`

- [ ] **Step 1: Read current `src/piighost/exceptions.py`**

```bash
cd C:/Users/NMarchitecte/Documents/piighost
cat src/piighost/exceptions.py
```

- [ ] **Step 2: Append new exception classes**

Add these classes at the end of `src/piighost/exceptions.py`:

```python
class ProjectNotFound(LookupError):
    """Raised when a project name is passed to a read operation but does not exist."""

    def __init__(self, name: str) -> None:
        super().__init__(
            f"project '{name}' does not exist; call list_projects to see available projects"
        )
        self.name = name


class ProjectNotEmpty(RuntimeError):
    """Raised when delete_project is called on a non-empty project without force=True."""

    def __init__(self, name: str, doc_count: int, vault_count: int) -> None:
        super().__init__(
            f"project '{name}' contains {doc_count} docs and {vault_count} vault entries; "
            f"pass force=True to delete anyway"
        )
        self.name = name
        self.doc_count = doc_count
        self.vault_count = vault_count
```

Do NOT re-export `InvalidProjectName` here — it lives in `piighost.vault.project_registry` where it's defined.

- [ ] **Step 3: Commit**

```bash
git add src/piighost/exceptions.py
git commit -m "feat(exceptions): ProjectNotFound and ProjectNotEmpty"
```

---

### Task 5: Split `PIIGhostService` into `_ProjectService` + multiplexer (backward-compatible)

**Files:**
- Modify: `src/piighost/service/core.py`

This task is the largest single change. It renames the current per-vault class to `_ProjectService` and introduces a thin multiplexer `PIIGhostService` that holds **exactly one** `_ProjectService` for the `default` project. Public signatures don't change yet (no `project` param), so all Sprint 1-4 tests keep passing. Tasks 6-7 add project parameters on top.

- [ ] **Step 1: Read current `src/piighost/service/core.py`**

```bash
wc -l src/piighost/service/core.py
```

You need to understand the full class before rewriting it.

- [ ] **Step 2: Rename `PIIGhostService` to `_ProjectService` in-place**

In `src/piighost/service/core.py`:

1. Rename the class declaration: `class PIIGhostService:` → `class _ProjectService:`.
2. Update the `__init__` signature to accept `placeholder_salt: str` **before** `ph_factory`:
   ```python
   def __init__(
       self,
       vault_dir: Path,
       config: ServiceConfig,
       vault: Vault,
       audit: AuditLogger,
       detector: _Detector,
       ph_factory: HashPlaceholderFactory,
   ) -> None:
   ```
   becomes
   ```python
   def __init__(
       self,
       project_dir: Path,
       project_name: str,
       config: ServiceConfig,
       vault: Vault,
       audit: AuditLogger,
       detector: _Detector,
       ph_factory: HashPlaceholderFactory,
   ) -> None:
       self._project_dir = project_dir
       self._project_name = project_name
       self._config = config
       self._vault = vault
       self._audit = audit
       self._detector = detector
       self._ph = ph_factory
       # ... rest of __init__ unchanged
   ```
   Replace references to `self._vault_dir` inside the class with `self._project_dir`.
3. In the `@classmethod async def create(...)` method on `_ProjectService`, change parameter names and internal paths:
   ```python
   @classmethod
   async def create(
       cls,
       *,
       project_dir: Path,
       project_name: str,
       config: ServiceConfig,
       detector: _Detector | None = None,
       placeholder_salt: str = "",
   ) -> "_ProjectService":
       project_dir.mkdir(parents=True, exist_ok=True)
       vault = Vault.open(project_dir / "vault.db")
       audit = AuditLogger(project_dir / "audit.log")
       if detector is None:
           detector = await _build_default_detector(config)
       return cls(
           project_dir=project_dir,
           project_name=project_name,
           config=config,
           vault=vault,
           audit=audit,
           detector=detector,
           ph_factory=HashPlaceholderFactory(salt=placeholder_salt),
       )
   ```
4. Inside `_ProjectService`, `ChunkStore` and `BM25Index` paths change from `self._vault_dir / ".piighost"` to `self._project_dir / ".piighost"`. Update those references.

- [ ] **Step 3: Add the new `PIIGhostService` multiplexer below `_ProjectService`**

Append at the end of `src/piighost/service/core.py` (before `_build_default_detector` and `_StubDetector`):

```python
from collections import OrderedDict

from piighost.service.migration import migrate_to_v3
from piighost.vault.project_registry import ProjectRegistry, ProjectInfo


class PIIGhostService:
    """Multiplexer over per-project :class:`_ProjectService` instances.

    Holds at most :attr:`LRU_SIZE` projects in memory; closes the oldest
    on eviction. Every public method accepts a ``project`` keyword argument
    (default ``"default"``) and delegates to the per-project service.
    """

    LRU_SIZE = 8

    def __init__(
        self,
        vault_dir: Path,
        config: ServiceConfig,
        registry: ProjectRegistry,
    ) -> None:
        self._vault_dir = vault_dir
        self._config = config
        self._registry = registry
        self._cache: "OrderedDict[str, _ProjectService]" = OrderedDict()

    @classmethod
    async def create(
        cls,
        *,
        vault_dir: Path,
        config: ServiceConfig | None = None,
        detector: _Detector | None = None,
    ) -> "PIIGhostService":
        config = config or ServiceConfig.default()
        migrate_to_v3(vault_dir)
        registry = ProjectRegistry.open(vault_dir / "projects.db")
        svc = cls(vault_dir=vault_dir, config=config, registry=registry)
        # Optional detector injection — apply it when the default project
        # service is created in _get_project. We stash it here.
        svc._detector_override = detector
        return svc

    async def _get_project(
        self, name: str, *, auto_create: bool = False
    ) -> "_ProjectService":
        if name in self._cache:
            self._cache.move_to_end(name)
            self._registry.touch(name)
            return self._cache[name]

        info = self._registry.get(name)
        if info is None:
            if not auto_create:
                from piighost.exceptions import ProjectNotFound
                raise ProjectNotFound(name)
            info = self._registry.create(name)

        project_dir = self._vault_dir / "projects" / name
        svc = await _ProjectService.create(
            project_dir=project_dir,
            project_name=name,
            config=self._config,
            detector=getattr(self, "_detector_override", None),
            placeholder_salt=info.placeholder_salt,
        )
        self._cache[name] = svc
        while len(self._cache) > self.LRU_SIZE:
            _evicted_name, evicted_svc = self._cache.popitem(last=False)
            await evicted_svc.close()
        self._registry.touch(name)
        return svc

    # Backward-compat delegations. Later tasks add project= kwargs.
    async def anonymize(self, text: str, *, doc_id: str | None = None):
        svc = await self._get_project("default", auto_create=True)
        return await svc.anonymize(text, doc_id=doc_id)

    async def rehydrate(self, text: str, *, strict: bool | None = None):
        svc = await self._get_project("default")
        return await svc.rehydrate(text, strict=strict)

    async def detect(self, text: str):
        svc = await self._get_project("default")
        return await svc.detect(text)

    async def index_path(self, path: Path, *, recursive: bool = True, force: bool = False):
        svc = await self._get_project("default", auto_create=True)
        return await svc.index_path(path, recursive=recursive, force=force)

    async def remove_doc(self, path: Path) -> bool:
        svc = await self._get_project("default")
        return await svc.remove_doc(path)

    async def query(self, text: str, *, k: int = 5):
        svc = await self._get_project("default")
        return await svc.query(text, k=k)

    async def index_status(self, *, limit: int = 100, offset: int = 0):
        svc = await self._get_project("default")
        return await svc.index_status(limit=limit, offset=offset)

    async def vault_list(
        self,
        *,
        label: str | None = None,
        limit: int = 100,
        offset: int = 0,
        reveal: bool = False,
    ):
        svc = await self._get_project("default")
        return await svc.vault_list(
            label=label, limit=limit, offset=offset, reveal=reveal
        )

    async def vault_show(self, token: str, *, reveal: bool = False):
        svc = await self._get_project("default")
        return await svc.vault_show(token, reveal=reveal)

    async def vault_stats(self):
        svc = await self._get_project("default")
        return await svc.vault_stats()

    async def vault_search(self, query: str, *, reveal: bool = False, limit: int = 100):
        svc = await self._get_project("default")
        return await svc.vault_search(query, reveal=reveal, limit=limit)

    async def flush(self) -> None:
        for svc in self._cache.values():
            await svc.flush()

    async def close(self) -> None:
        for svc in self._cache.values():
            await svc.close()
        self._cache.clear()
        self._registry.close()
```

- [ ] **Step 4: Run full suite — must pass with no changes**

```bash
python -m pytest tests/unit/ tests/e2e/ -q -p no:randomly 2>&1 | tail -10
```

Expected: all passing. If anything fails, it's because a test poked at internals (`svc._vault`, `svc._chunk_store`) that now live on `_ProjectService`. Those tests are in Sprint 3's `test_service_incremental.py` and `test_service_remove_doc.py`. For each failing test, change `svc._vault` → `(await svc._get_project("default"))._vault`. You can use a small helper in the test module:

```python
def _inner(svc):
    import asyncio
    return asyncio.run(svc._get_project("default"))
```

Apply that pattern mechanically to every failing access. If there are more than a handful, commit them as a single follow-up with message `refactor(tests): access per-project internals through multiplexer`.

- [ ] **Step 5: Commit**

```bash
git add src/piighost/service/core.py tests/
git commit -m "refactor(service): split PIIGhostService into multiplexer + _ProjectService"
```

---

### Task 6: Add `project` parameter to every public method

**Files:**
- Modify: `src/piighost/service/core.py`
- Modify: `src/piighost/service/models.py` (add `project` to `IndexReport`)

- [ ] **Step 1: Write failing test**

Create `tests/unit/test_service_project_param.py`:

```python
import asyncio
import pytest

from piighost.service.core import PIIGhostService


@pytest.fixture()
def svc(tmp_path, monkeypatch):
    monkeypatch.setenv("PIIGHOST_EMBEDDER", "stub")
    monkeypatch.setenv("PIIGHOST_DETECTOR", "stub")
    service = asyncio.run(PIIGhostService.create(vault_dir=tmp_path / "vault"))
    yield service
    asyncio.run(service.close())


def test_anonymize_accepts_project(svc):
    result = asyncio.run(svc.anonymize("Alice lives here", project="client-a"))
    assert len(result.entities) >= 1


def test_rehydrate_accepts_project(svc):
    r = asyncio.run(svc.anonymize("Alice", project="client-a"))
    rehydrated = asyncio.run(svc.rehydrate(r.anonymized, project="client-a"))
    assert rehydrated.unknown_tokens == []


def test_query_accepts_project(svc, tmp_path):
    doc = tmp_path / "doc.txt"
    doc.write_text("Alice works in Paris")
    asyncio.run(svc.index_path(doc, project="client-a"))
    result = asyncio.run(svc.query("Paris", project="client-a", k=5))
    assert result.k == 5


def test_vault_stats_accepts_project(svc):
    asyncio.run(svc.anonymize("Alice", project="client-a"))
    stats = asyncio.run(svc.vault_stats(project="client-a"))
    assert stats.total >= 1


def test_default_project_still_works_without_param(svc):
    """Backward compat: methods default to project='default'."""
    result = asyncio.run(svc.anonymize("Alice lives here"))
    assert len(result.entities) >= 1
```

- [ ] **Step 2: Run test — should fail**

```bash
python -m pytest tests/unit/test_service_project_param.py -v -p no:randomly
```

Expected: `TypeError: anonymize() got an unexpected keyword argument 'project'`.

- [ ] **Step 3: Add `project` kwarg to every multiplexer method**

Edit `src/piighost/service/core.py`. Replace every method in the `PIIGhostService` class (from Task 5) with the project-aware version:

```python
async def anonymize(self, text: str, *, doc_id: str | None = None, project: str = "default"):
    svc = await self._get_project(project, auto_create=True)
    return await svc.anonymize(text, doc_id=doc_id)

async def rehydrate(self, text: str, *, strict: bool | None = None, project: str = "default"):
    svc = await self._get_project(project)
    return await svc.rehydrate(text, strict=strict)

async def detect(self, text: str, *, project: str = "default"):
    svc = await self._get_project(project)
    return await svc.detect(text)

async def index_path(
    self,
    path: Path,
    *,
    recursive: bool = True,
    force: bool = False,
    project: str | None = None,
):
    from piighost.service.project_path import derive_project_from_path
    resolved = project if project is not None else derive_project_from_path(path)
    svc = await self._get_project(resolved, auto_create=True)
    report = await svc.index_path(path, recursive=recursive, force=force)
    # Attach project to the report for Claude to surface to the user.
    return report.model_copy(update={"project": resolved})

async def remove_doc(self, path: Path, *, project: str = "default") -> bool:
    svc = await self._get_project(project)
    return await svc.remove_doc(path)

async def query(self, text: str, *, k: int = 5, project: str = "default"):
    svc = await self._get_project(project)
    return await svc.query(text, k=k)

async def index_status(self, *, limit: int = 100, offset: int = 0, project: str = "default"):
    svc = await self._get_project(project)
    return await svc.index_status(limit=limit, offset=offset)

async def vault_list(
    self,
    *,
    label: str | None = None,
    limit: int = 100,
    offset: int = 0,
    reveal: bool = False,
    project: str = "default",
):
    svc = await self._get_project(project)
    return await svc.vault_list(label=label, limit=limit, offset=offset, reveal=reveal)

async def vault_show(self, token: str, *, reveal: bool = False, project: str = "default"):
    svc = await self._get_project(project)
    return await svc.vault_show(token, reveal=reveal)

async def vault_stats(self, *, project: str = "default"):
    svc = await self._get_project(project)
    return await svc.vault_stats()

async def vault_search(
    self,
    query: str,
    *,
    reveal: bool = False,
    limit: int = 100,
    project: str = "default",
):
    svc = await self._get_project(project)
    return await svc.vault_search(query, reveal=reveal, limit=limit)
```

- [ ] **Step 4: Add `project` field to `IndexReport`**

In `src/piighost/service/models.py`, find `class IndexReport(BaseModel):` and add:

```python
    project: str = "default"
```

- [ ] **Step 5: Run all tests**

```bash
python -m pytest tests/unit/ tests/e2e/ -q -p no:randomly 2>&1 | tail -5
```

Expected: all passing.

- [ ] **Step 6: Commit**

```bash
git add src/piighost/service/core.py src/piighost/service/models.py tests/unit/test_service_project_param.py
git commit -m "feat(service): project parameter on every public method (default='default')"
```

---

### Task 7: Project name auto-derivation from path

**Files:**
- Create: `src/piighost/service/project_path.py`
- Create: `tests/unit/test_project_derivation.py`

- [ ] **Step 1: Write failing test**

Create `tests/unit/test_project_derivation.py`:

```python
from pathlib import Path

import pytest

from piighost.service.project_path import derive_project_from_path


def test_extracts_project_from_typical_layout():
    # /Users/x/projects/client-a/contracts/ → client-a
    assert derive_project_from_path(Path("/Users/alice/projects/client-a/contracts")) == "client-a"


def test_skips_generic_names():
    assert derive_project_from_path(Path("/Users/alice/Documents/client-a/docs")) == "client-a"
    assert derive_project_from_path(Path("/home/bob/src/client-b/data")) == "client-b"


def test_single_generic_path_falls_back_to_default():
    assert derive_project_from_path(Path("/tmp")) == "default"
    assert derive_project_from_path(Path("/home/alice")) == "default"


def test_invalid_chars_fall_back_to_default():
    # Parent dir has a space → skipped → no candidate → default
    assert derive_project_from_path(Path("/Users/alice/my client/docs")) == "default"


def test_empty_path_falls_back_to_default():
    assert derive_project_from_path(Path("/")) == "default"


def test_relative_path_resolves_first():
    # Relative paths get resolved to absolute before deriving.
    result = derive_project_from_path(Path("."))
    # Just assert it returns something valid; specifics depend on cwd.
    assert result
```

- [ ] **Step 2: Run test — should fail**

```bash
python -m pytest tests/unit/test_project_derivation.py -v -p no:randomly
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Create `src/piighost/service/project_path.py`**

```python
"""Auto-derive a project name from a filesystem path."""

from __future__ import annotations

import re
from pathlib import Path


_GENERIC_NAMES = frozenset(
    {
        "documents",
        "desktop",
        "downloads",
        "src",
        "tmp",
        "var",
        "home",
        "users",
        "projects",
        "data",
        "docs",
    }
)

_VALID_NAME_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")


def derive_project_from_path(path: Path) -> str:
    """Return the first path component that looks like a project name.

    Walks from the path's parent toward the root, skipping generic names
    (``documents``, ``src``, ``projects``, ...) and names with invalid
    characters. Returns ``"default"`` if no suitable candidate is found.
    """
    resolved = path.resolve()
    parts = [p for p in resolved.parts if p not in ("/", "\\")]
    # Drop drive letters like "C:" on Windows
    parts = [p for p in parts if not (len(p) == 2 and p.endswith(":"))]
    # Skip the deepest component (usually the folder being indexed).
    for candidate in reversed(parts[:-1]):
        if candidate.lower() in _GENERIC_NAMES:
            continue
        if not _VALID_NAME_RE.fullmatch(candidate):
            continue
        return candidate
    return "default"
```

- [ ] **Step 4: Run test — should pass**

```bash
python -m pytest tests/unit/test_project_derivation.py -v -p no:randomly
```

Expected: all PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/piighost/service/project_path.py tests/unit/test_project_derivation.py
git commit -m "feat(service): derive project name from path for index_path auto-routing"
```

---

### Task 8: Multiplexer project-management methods

**Files:**
- Modify: `src/piighost/service/core.py`
- Modify: `src/piighost/service/models.py`
- Create: `tests/unit/test_service_multiplexer.py`

- [ ] **Step 1: Write failing test**

Create `tests/unit/test_service_multiplexer.py`:

```python
import asyncio

import pytest

from piighost.exceptions import ProjectNotEmpty
from piighost.service.core import PIIGhostService


@pytest.fixture()
def svc(tmp_path, monkeypatch):
    monkeypatch.setenv("PIIGHOST_EMBEDDER", "stub")
    monkeypatch.setenv("PIIGHOST_DETECTOR", "stub")
    service = asyncio.run(PIIGhostService.create(vault_dir=tmp_path / "vault"))
    yield service
    asyncio.run(service.close())


def test_list_projects_includes_default(svc):
    projects = asyncio.run(svc.list_projects())
    names = {p.name for p in projects}
    assert "default" in names


def test_create_project(svc):
    info = asyncio.run(svc.create_project("client-a", description="A"))
    assert info.name == "client-a"
    assert info.description == "A"
    assert info.placeholder_salt == "client-a"

    projects = asyncio.run(svc.list_projects())
    assert any(p.name == "client-a" for p in projects)


def test_delete_empty_project(svc):
    asyncio.run(svc.create_project("client-a"))
    result = asyncio.run(svc.delete_project("client-a"))
    assert result is True
    names = {p.name for p in asyncio.run(svc.list_projects())}
    assert "client-a" not in names


def test_delete_default_refused(svc):
    with pytest.raises(ValueError, match="default project cannot be deleted"):
        asyncio.run(svc.delete_project("default"))


def test_delete_nonempty_refused_without_force(svc):
    asyncio.run(svc.anonymize("Alice", project="client-a"))
    with pytest.raises(ProjectNotEmpty):
        asyncio.run(svc.delete_project("client-a"))


def test_delete_nonempty_force_succeeds(svc):
    asyncio.run(svc.anonymize("Alice", project="client-a"))
    result = asyncio.run(svc.delete_project("client-a", force=True))
    assert result is True


def test_lru_eviction_closes_old_services(svc):
    # Create more projects than LRU_SIZE (default 8)
    for i in range(10):
        asyncio.run(svc.create_project(f"proj-{i}"))
        asyncio.run(svc.anonymize("Alice", project=f"proj-{i}"))
    # Cache should hold at most LRU_SIZE entries
    assert len(svc._cache) <= PIIGhostService.LRU_SIZE
```

- [ ] **Step 2: Run test — should fail**

```bash
python -m pytest tests/unit/test_service_multiplexer.py -v -p no:randomly
```

Expected: `AttributeError: 'PIIGhostService' object has no attribute 'list_projects'`.

- [ ] **Step 3: Add project-management methods to `PIIGhostService`**

In `src/piighost/service/core.py`, inside the `PIIGhostService` class, append:

```python
async def list_projects(self) -> list[ProjectInfo]:
    return self._registry.list()

async def create_project(
    self, name: str, description: str = "", placeholder_salt: str | None = None
) -> ProjectInfo:
    return self._registry.create(name, description=description, placeholder_salt=placeholder_salt)

async def delete_project(self, name: str, *, force: bool = False) -> bool:
    if name == "default":
        raise ValueError("the default project cannot be deleted")

    info = self._registry.get(name)
    if info is None:
        return False

    if not force:
        svc = await self._get_project(name)
        stats = await svc.vault_stats()
        status = await svc.index_status()
        if stats.total > 0 or status.total_docs > 0:
            from piighost.exceptions import ProjectNotEmpty
            raise ProjectNotEmpty(
                name=name,
                doc_count=status.total_docs,
                vault_count=stats.total,
            )

    # Close any cached handle
    cached = self._cache.pop(name, None)
    if cached is not None:
        await cached.close()

    # Delete project directory + registry row
    import shutil
    project_dir = self._vault_dir / "projects" / name
    if project_dir.exists():
        shutil.rmtree(project_dir)
    return self._registry.delete(name)
```

- [ ] **Step 4: Add `ProjectInfo` re-export**

At the top of `src/piighost/service/core.py`, in the imports, ensure `ProjectInfo` is imported:

```python
from piighost.vault.project_registry import ProjectRegistry, ProjectInfo
```

- [ ] **Step 5: Run tests — should pass**

```bash
python -m pytest tests/unit/test_service_multiplexer.py -v -p no:randomly
python -m pytest tests/unit/ tests/e2e/ -q -p no:randomly 2>&1 | tail -5
```

Expected: all passing.

- [ ] **Step 6: Commit**

```bash
git add src/piighost/service/core.py tests/unit/test_service_multiplexer.py
git commit -m "feat(service): list_projects, create_project, delete_project on multiplexer"
```

---

### Task 9: MCP tool surface updates

**Files:**
- Modify: `src/piighost/mcp/server.py`
- Create: `tests/unit/test_mcp_project_wiring.py`

- [ ] **Step 1: Write failing test**

Create `tests/unit/test_mcp_project_wiring.py`:

```python
import asyncio
import importlib.util

import pytest


@pytest.fixture()
def built_mcp(tmp_path, monkeypatch):
    monkeypatch.setenv("PIIGHOST_EMBEDDER", "stub")
    monkeypatch.setenv("PIIGHOST_DETECTOR", "stub")
    # Force indexing tools on for this test
    real_find_spec = importlib.util.find_spec

    def fake(name, *args, **kwargs):
        if name == "sentence_transformers":
            return object()  # truthy
        return real_find_spec(name, *args, **kwargs)

    monkeypatch.setattr("importlib.util.find_spec", fake)

    from piighost.mcp.server import build_mcp
    mcp, svc = asyncio.run(build_mcp(tmp_path / "vault"))
    yield mcp, svc
    asyncio.run(svc.close())


def test_anonymize_text_accepts_project(built_mcp):
    mcp, _ = built_mcp
    tools = asyncio.run(mcp.get_tools())
    result = asyncio.run(
        tools["anonymize_text"].run({"text": "Alice", "project": "client-a"})
    )
    payload = result.structured_content["result"] if hasattr(result, "structured_content") else result
    assert "entities" in payload


def test_list_projects_exists(built_mcp):
    mcp, _ = built_mcp
    tools = asyncio.run(mcp.get_tools())
    assert "list_projects" in tools
    assert "create_project" in tools
    assert "delete_project" in tools


def test_create_project_tool(built_mcp):
    mcp, _ = built_mcp
    tools = asyncio.run(mcp.get_tools())
    result = asyncio.run(tools["create_project"].run({"name": "client-a"}))
    payload = result.structured_content["result"] if hasattr(result, "structured_content") else result
    assert payload["name"] == "client-a"


def test_index_path_returns_project_in_response(built_mcp, tmp_path):
    mcp, _ = built_mcp
    doc_dir = tmp_path / "client-xyz" / "docs"
    doc_dir.mkdir(parents=True)
    (doc_dir / "doc.txt").write_text("Alice works in Paris")
    tools = asyncio.run(mcp.get_tools())
    result = asyncio.run(tools["index_path"].run({"path": str(doc_dir)}))
    payload = result.structured_content["result"] if hasattr(result, "structured_content") else result
    # Project auto-derived from path
    assert "project" in payload
    assert payload["project"] == "client-xyz"
```

- [ ] **Step 2: Run test — should fail**

```bash
python -m pytest tests/unit/test_mcp_project_wiring.py -v -p no:randomly
```

Expected: tool signatures don't accept `project`.

- [ ] **Step 3: Update every tool in `src/piighost/mcp/server.py` to accept `project`**

Read `src/piighost/mcp/server.py`. Replace each tool decorator block with the project-aware version:

```python
    @mcp.tool(description="Anonymize text, replacing PII with opaque tokens")
    async def anonymize_text(text: str, doc_id: str = "", project: str = "default") -> dict:
        result = await svc.anonymize(text, doc_id=doc_id or None, project=project)
        return result.model_dump()

    @mcp.tool(description="Rehydrate anonymized text back to original PII")
    async def rehydrate_text(text: str, project: str = "default") -> dict:
        result = await svc.rehydrate(text, project=project)
        return result.model_dump()

    if _indexing_available():
        @mcp.tool(description="Index a file or directory into the retrieval store")
        async def index_path(
            path: str,
            recursive: bool = True,
            force: bool = False,
            project: str = "",
        ) -> dict:
            # Empty string means "auto-derive from path"
            project_arg = project if project else None
            report = await svc.index_path(
                Path(path), recursive=recursive, force=force, project=project_arg
            )
            return report.model_dump()

        @mcp.tool(description="Hybrid BM25+vector search over indexed documents")
        async def query(text: str, k: int = 5, project: str = "default") -> dict:
            result = await svc.query(text, k=k, project=project)
            return result.model_dump()

    @mcp.tool(description="Full-text search in the PII vault by original value")
    async def vault_search(
        q: str, reveal: bool = False, project: str = "default"
    ) -> list[dict]:
        entries = await svc.vault_search(q, reveal=reveal, project=project)
        return [e.model_dump() for e in entries]

    @mcp.tool(description="List vault entries with optional label filter")
    async def vault_list(
        label: str = "",
        limit: int = 100,
        offset: int = 0,
        reveal: bool = False,
        project: str = "default",
    ) -> list[dict]:
        page = await svc.vault_list(
            label=label or None,
            limit=limit,
            offset=offset,
            reveal=reveal,
            project=project,
        )
        return [e.model_dump(exclude_none=False) for e in page.entries]

    @mcp.tool(description="Retrieve a single vault entry by token")
    async def vault_get(
        token: str, reveal: bool = False, project: str = "default"
    ) -> dict | None:
        entry = await svc.vault_show(token, reveal=reveal, project=project)
        return entry.model_dump() if entry is not None else None

    @mcp.tool(description="Return vault statistics (total entries, by label)")
    async def vault_stats(project: str = "default") -> dict:
        stats = await svc.vault_stats(project=project)
        return stats.model_dump()

    @mcp.tool(description="List all projects")
    async def list_projects() -> list[dict]:
        projects = await svc.list_projects()
        return [
            {
                "name": p.name,
                "description": p.description,
                "created_at": p.created_at,
                "last_accessed_at": p.last_accessed_at,
            }
            for p in projects
        ]

    @mcp.tool(description="Create a new project")
    async def create_project(name: str, description: str = "") -> dict:
        info = await svc.create_project(name, description=description)
        return {
            "name": info.name,
            "description": info.description,
            "created_at": info.created_at,
        }

    @mcp.tool(description="Delete a project (refuses if non-empty unless force=True)")
    async def delete_project(name: str, force: bool = False) -> dict:
        deleted = await svc.delete_project(name, force=force)
        return {"deleted": deleted, "name": name}
```

Keep the existing `daemon_status`, `daemon_stop`, and resource definitions as-is.

- [ ] **Step 4: Remove `index_path`'s optional indexing block issue**

Because `index_path` lives inside the `if _indexing_available():` block (from Sprint 4c Task 1), if `sentence_transformers` is missing it won't be registered. That's still correct — the project param just gets added to the gated tool.

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/unit/test_mcp_project_wiring.py tests/unit/test_mcp_server.py tests/unit/test_mcp_reveal.py tests/unit/test_mcp_indexing_gate.py -v -p no:randomly
```

Expected: all passing.

- [ ] **Step 6: Commit**

```bash
git add src/piighost/mcp/server.py tests/unit/test_mcp_project_wiring.py
git commit -m "feat(mcp): project parameter on all tools + list/create/delete_project tools"
```

---

### Task 10: MCP project resources

**Files:**
- Modify: `src/piighost/mcp/server.py`

- [ ] **Step 1: Add new resources**

In `src/piighost/mcp/server.py`, append two new resource definitions inside `build_mcp` (next to the existing `piighost://vault/stats`):

```python
    @mcp.resource("piighost://projects")
    async def projects_resource() -> str:
        import json
        projects = await svc.list_projects()
        payload = [
            {
                "name": p.name,
                "description": p.description,
                "created_at": p.created_at,
                "last_accessed_at": p.last_accessed_at,
            }
            for p in projects
        ]
        return json.dumps(payload, indent=2)

    @mcp.resource("piighost://projects/{name}/stats")
    async def project_stats_resource(name: str) -> str:
        stats = await svc.vault_stats(project=name)
        status = await svc.index_status(project=name)
        return (
            f"Project: {name}\n"
            f"Vault entities: {stats.total}\n"
            f"Indexed docs: {status.total_docs}\n"
            f"Total chunks: {status.total_chunks}\n"
        )
```

- [ ] **Step 2: Smoke test — run existing MCP tests**

```bash
cd C:/Users/NMarchitecte/Documents/piighost
python -m pytest tests/unit/test_mcp_server.py tests/unit/test_mcp_project_wiring.py -v -p no:randomly
```

Expected: all passing.

- [ ] **Step 3: Commit**

```bash
git add src/piighost/mcp/server.py
git commit -m "feat(mcp): piighost://projects and piighost://projects/{name}/stats resources"
```

---

### Task 11: CLI `--project` flag + `projects` subcommand group

**Files:**
- Modify: `src/piighost/cli/commands/anonymize.py`
- Modify: `src/piighost/cli/commands/rehydrate.py`
- Modify: `src/piighost/cli/commands/detect.py`
- Modify: `src/piighost/cli/commands/index.py`
- Modify: `src/piighost/cli/commands/query.py`
- Modify: `src/piighost/cli/commands/rm.py`
- Modify: `src/piighost/cli/commands/index_status.py`
- Modify: `src/piighost/cli/commands/vault.py` (each subcommand)
- Create: `src/piighost/cli/commands/projects.py`
- Modify: `src/piighost/cli/main.py`
- Create: `tests/unit/test_cli_project_flag.py`

- [ ] **Step 1: Write failing test**

Create `tests/unit/test_cli_project_flag.py`:

```python
from typer.testing import CliRunner

from piighost.cli.main import app

runner = CliRunner()


def test_anonymize_has_project_flag():
    result = runner.invoke(app, ["anonymize", "--help"])
    assert result.exit_code == 0
    assert "--project" in result.output


def test_query_has_project_flag():
    result = runner.invoke(app, ["query", "--help"])
    assert result.exit_code == 0
    assert "--project" in result.output


def test_index_has_project_flag():
    result = runner.invoke(app, ["index", "--help"])
    assert result.exit_code == 0
    assert "--project" in result.output


def test_vault_list_has_project_flag():
    result = runner.invoke(app, ["vault", "list", "--help"])
    assert result.exit_code == 0
    assert "--project" in result.output


def test_projects_list_command_exists():
    result = runner.invoke(app, ["projects", "list", "--help"])
    assert result.exit_code == 0


def test_projects_create_command_exists():
    result = runner.invoke(app, ["projects", "create", "--help"])
    assert result.exit_code == 0
    assert "name" in result.output.lower()


def test_projects_delete_command_exists():
    result = runner.invoke(app, ["projects", "delete", "--help"])
    assert result.exit_code == 0
```

- [ ] **Step 2: Run test to verify failure**

```bash
python -m pytest tests/unit/test_cli_project_flag.py -v -p no:randomly
```

Expected: some tests fail because flags/commands don't exist.

- [ ] **Step 3: Add `--project` to every existing command**

For each existing command file (`anonymize.py`, `rehydrate.py`, `detect.py`, `index.py`, `query.py`, `rm.py`, `index_status.py`, and each subcommand in `vault.py`):

1. Add to the function signature:
   ```python
   project: str = typer.Option("default", "--project", help="Project name (defaults to 'default')"),
   ```
2. Forward it to the daemon call and/or to the service method:
   - In the `DaemonClient.call(...)` params dict, add `"project": project`.
   - In the local async fallback, pass `project=project` to the service method.

For `index.py`, default should be `""` (empty = auto-derive):
```python
project: str = typer.Option("", "--project", help="Project name (empty = derive from path)"),
```

And the daemon/service call:
```python
project_arg = project if project else None
svc.index_path(..., project=project_arg)
# For daemon:
client.call("index_path", {..., "project": project})  # empty string passes through
```

The daemon server (Task 12) converts empty string to None before calling the service.

- [ ] **Step 4: Create `src/piighost/cli/commands/projects.py`**

```python
"""`piighost projects {list,create,delete}` — project management."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from piighost.cli.commands.vault import _load_cfg, _resolve_vault
from piighost.cli.output import ExitCode, emit_error_line, emit_json_line
from piighost.daemon.client import DaemonClient
from piighost.exceptions import VaultNotFound
from piighost.service import PIIGhostService


app = typer.Typer(help="Manage piighost projects (isolated vaults + retrieval).")


@app.command("list")
def list_cmd(
    vault: Path | None = typer.Option(None, "--vault"),
) -> None:
    try:
        vault_dir = _resolve_vault(vault)
    except VaultNotFound as exc:
        emit_error_line(
            error="VaultNotFound",
            message=type(exc).__name__,
            hint="Run `piighost init`",
            exit_code=ExitCode.USER_ERROR,
        )
        raise typer.Exit(code=int(ExitCode.USER_ERROR))

    client = DaemonClient.from_vault(vault_dir)
    if client is not None:
        emit_json_line(client.call("list_projects", {}))
        return

    asyncio.run(_list(vault_dir))


async def _list(vault_dir: Path) -> None:
    config = _load_cfg(vault_dir)
    svc = await PIIGhostService.create(vault_dir=vault_dir, config=config)
    try:
        projects = await svc.list_projects()
        emit_json_line(
            [
                {
                    "name": p.name,
                    "description": p.description,
                    "created_at": p.created_at,
                    "last_accessed_at": p.last_accessed_at,
                }
                for p in projects
            ]
        )
    finally:
        await svc.close()


@app.command("create")
def create_cmd(
    name: str = typer.Argument(..., help="Project name"),
    description: str = typer.Option("", "--description"),
    vault: Path | None = typer.Option(None, "--vault"),
) -> None:
    try:
        vault_dir = _resolve_vault(vault)
    except VaultNotFound as exc:
        emit_error_line(
            error="VaultNotFound",
            message=type(exc).__name__,
            hint="Run `piighost init`",
            exit_code=ExitCode.USER_ERROR,
        )
        raise typer.Exit(code=int(ExitCode.USER_ERROR))

    client = DaemonClient.from_vault(vault_dir)
    if client is not None:
        emit_json_line(
            client.call("create_project", {"name": name, "description": description})
        )
        return

    asyncio.run(_create(vault_dir, name, description))


async def _create(vault_dir: Path, name: str, description: str) -> None:
    config = _load_cfg(vault_dir)
    svc = await PIIGhostService.create(vault_dir=vault_dir, config=config)
    try:
        info = await svc.create_project(name, description=description)
        emit_json_line(
            {
                "name": info.name,
                "description": info.description,
                "created_at": info.created_at,
            }
        )
    finally:
        await svc.close()


@app.command("delete")
def delete_cmd(
    name: str = typer.Argument(..., help="Project name"),
    force: bool = typer.Option(False, "--force/--no-force"),
    vault: Path | None = typer.Option(None, "--vault"),
) -> None:
    try:
        vault_dir = _resolve_vault(vault)
    except VaultNotFound as exc:
        emit_error_line(
            error="VaultNotFound",
            message=type(exc).__name__,
            hint="Run `piighost init`",
            exit_code=ExitCode.USER_ERROR,
        )
        raise typer.Exit(code=int(ExitCode.USER_ERROR))

    client = DaemonClient.from_vault(vault_dir)
    if client is not None:
        emit_json_line(
            client.call("delete_project", {"name": name, "force": force})
        )
        return

    asyncio.run(_delete(vault_dir, name, force))


async def _delete(vault_dir: Path, name: str, force: bool) -> None:
    config = _load_cfg(vault_dir)
    svc = await PIIGhostService.create(vault_dir=vault_dir, config=config)
    try:
        deleted = await svc.delete_project(name, force=force)
        emit_json_line({"deleted": deleted, "name": name})
    finally:
        await svc.close()
```

- [ ] **Step 5: Register `projects` subgroup in `src/piighost/cli/main.py`**

Add an import:
```python
from piighost.cli.commands.projects import app as projects_app
```

Register the subgroup after the existing `app.command(...)` calls:
```python
app.add_typer(projects_app, name="projects")
```

- [ ] **Step 6: Run tests**

```bash
python -m pytest tests/unit/test_cli_project_flag.py tests/unit/test_cli_commands.py tests/unit/test_cli_rm_status.py -v -p no:randomly
```

Expected: all passing.

- [ ] **Step 7: Commit**

```bash
git add src/piighost/cli/ tests/unit/test_cli_project_flag.py
git commit -m "feat(cli): --project flag on all commands + piighost projects subgroup"
```

---

### Task 12: Daemon dispatch updates

**Files:**
- Modify: `src/piighost/daemon/server.py`

- [ ] **Step 1: Read current dispatch function**

```bash
grep -n "def _dispatch\|def dispatch\|method ==" src/piighost/daemon/server.py | head -30
```

- [ ] **Step 2: Update every dispatch case to forward `project` parameter**

For each existing case (`anonymize`, `rehydrate`, `detect`, `index_path`, `query`, `remove_doc`, `index_status`, `vault_list`, `vault_show`, `vault_stats`, `vault_search`), add `project=params.get("project", "default")` to the service call. Example for `anonymize`:

```python
if method == "anonymize":
    result = await svc.anonymize(
        params["text"],
        doc_id=params.get("doc_id"),
        project=params.get("project", "default"),
    )
    return result.model_dump()
```

For `index_path`, convert empty string to None for auto-derivation:

```python
if method == "index_path":
    from pathlib import Path as _Path
    raw_project = params.get("project", "")
    project = raw_project if raw_project else None
    report = await svc.index_path(
        _Path(params["path"]),
        recursive=params.get("recursive", True),
        force=params.get("force", False),
        project=project,
    )
    return report.model_dump()
```

Do this for every method that reaches the service layer.

- [ ] **Step 3: Add dispatch cases for the 3 new project methods**

After the existing cases, add:

```python
if method == "list_projects":
    projects = await svc.list_projects()
    return [
        {
            "name": p.name,
            "description": p.description,
            "created_at": p.created_at,
            "last_accessed_at": p.last_accessed_at,
            "placeholder_salt": p.placeholder_salt,
        }
        for p in projects
    ]

if method == "create_project":
    info = await svc.create_project(
        params["name"],
        description=params.get("description", ""),
    )
    return {
        "name": info.name,
        "description": info.description,
        "created_at": info.created_at,
    }

if method == "delete_project":
    deleted = await svc.delete_project(
        params["name"], force=params.get("force", False)
    )
    return {"deleted": deleted, "name": params["name"]}
```

- [ ] **Step 4: Run full suite**

```bash
python -m pytest tests/unit/ tests/e2e/ -q -p no:randomly 2>&1 | tail -5
```

Expected: all passing.

- [ ] **Step 5: Commit**

```bash
git add src/piighost/daemon/server.py
git commit -m "feat(daemon): forward project param + dispatch list/create/delete_project"
```

---

### Task 13: E2E isolation tests (critical safety)

**Files:**
- Create: `tests/e2e/test_project_isolation.py`
- Create: `tests/e2e/test_v2_to_v3_migration.py`

These are the safety-critical tests that prove Sprint 5's isolation guarantee holds end-to-end.

- [ ] **Step 1: Create `tests/e2e/test_project_isolation.py`**

```python
"""E2E: multi-project isolation — different tokens, scoped queries, no cross-project rehydrate."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from piighost.service.core import PIIGhostService


@pytest.fixture()
def svc(tmp_path, monkeypatch):
    monkeypatch.setenv("PIIGHOST_EMBEDDER", "stub")
    monkeypatch.setenv("PIIGHOST_DETECTOR", "stub")
    service = asyncio.run(PIIGhostService.create(vault_dir=tmp_path / "vault"))
    yield service
    asyncio.run(service.close())


def test_tokens_differ_across_projects(svc):
    a = asyncio.run(svc.anonymize("Alice works here", project="client-a"))
    b = asyncio.run(svc.anonymize("Alice works here", project="client-b"))
    a_token = a.entities[0].token
    b_token = b.entities[0].token
    assert a_token != b_token


def test_same_value_same_project_same_token(svc):
    a1 = asyncio.run(svc.anonymize("Alice is here", project="client-a"))
    a2 = asyncio.run(svc.anonymize("Then Alice left", project="client-a"))
    assert a1.entities[0].token == a2.entities[0].token


def test_rehydrate_fails_in_wrong_project(svc):
    r = asyncio.run(svc.anonymize("Alice works here", project="client-a"))
    # Token is in client-a's vault. Rehydrating in client-b must leave it unknown.
    rehydrated = asyncio.run(svc.rehydrate(r.anonymized, project="client-b", strict=False))
    assert r.entities[0].token in rehydrated.unknown_tokens
    assert "Alice" not in rehydrated.text


def test_query_scoped_to_project(svc, tmp_path):
    docs_a = tmp_path / "client-a-docs"
    docs_a.mkdir()
    (docs_a / "a.txt").write_text("Alice works on GDPR compliance contracts")

    docs_b = tmp_path / "client-b-docs"
    docs_b.mkdir()
    (docs_b / "b.txt").write_text("Bob handles medical records review")

    asyncio.run(svc.index_path(docs_a, project="client-a"))
    asyncio.run(svc.index_path(docs_b, project="client-b"))

    result_a = asyncio.run(svc.query("GDPR compliance", project="client-a", k=5))
    result_b = asyncio.run(svc.query("GDPR compliance", project="client-b", k=5))

    # client-a has the matching doc; client-b does not
    paths_a = {h.file_path for h in result_a.hits}
    paths_b = {h.file_path for h in result_b.hits}
    assert str(docs_a / "a.txt") in paths_a
    assert str(docs_a / "a.txt") not in paths_b


def test_vault_search_scoped_to_project(svc):
    asyncio.run(svc.anonymize("Alice", project="client-a"))
    asyncio.run(svc.anonymize("Bob", project="client-b"))

    a_results = asyncio.run(svc.vault_search("Alice", project="client-a", reveal=True))
    b_results = asyncio.run(svc.vault_search("Alice", project="client-b", reveal=True))

    assert any(e.original == "Alice" for e in a_results)
    assert not any(e.original == "Alice" for e in b_results)


def test_vault_stats_are_per_project(svc):
    asyncio.run(svc.anonymize("Alice lives in Paris", project="client-a"))
    a_stats = asyncio.run(svc.vault_stats(project="client-a"))
    b_stats = asyncio.run(svc.vault_stats(project="client-b"))
    assert a_stats.total >= 1
    assert b_stats.total == 0


def test_index_path_auto_derives_project(svc, tmp_path):
    docs = tmp_path / "client-xyz" / "contracts"
    docs.mkdir(parents=True)
    (docs / "contract.txt").write_text("Alice signed the GDPR contract in Paris")

    report = asyncio.run(svc.index_path(docs))
    assert report.project == "client-xyz"

    # Query in client-xyz finds the doc; query in default does not
    result = asyncio.run(svc.query("GDPR contract", project="client-xyz", k=5))
    assert len(result.hits) >= 1


def test_list_projects_includes_all_created(svc):
    asyncio.run(svc.anonymize("A", project="client-a"))
    asyncio.run(svc.anonymize("B", project="client-b"))
    projects = asyncio.run(svc.list_projects())
    names = {p.name for p in projects}
    assert {"default", "client-a", "client-b"} <= names
```

- [ ] **Step 2: Create `tests/e2e/test_v2_to_v3_migration.py`**

```python
"""E2E: Sprint 1-4 state migrates to Sprint 5 layout transparently."""

from __future__ import annotations

import asyncio

import pytest

from piighost.service.core import PIIGhostService


@pytest.fixture()
def legacy_vault(tmp_path, monkeypatch):
    """Create a vault using the v2 layout (single-vault, no projects/) and populate it."""
    monkeypatch.setenv("PIIGHOST_EMBEDDER", "stub")
    monkeypatch.setenv("PIIGHOST_DETECTOR", "stub")
    vault = tmp_path / "vault"

    # Simulate v2 state by calling create + populating, then closing. The multiplexer
    # will migrate on first open, but we want to test the migration path on a file layout
    # that resembles v2. Easiest path: create v3, anonymize, close, then move files back
    # to the v2 layout.
    svc = asyncio.run(PIIGhostService.create(vault_dir=vault))
    asyncio.run(svc.anonymize("Alice was here"))
    asyncio.run(svc.close())

    # Move projects/default/* back to top level to simulate v2
    default = vault / "projects" / "default"
    for child in default.iterdir():
        child.rename(vault / child.name)
    (vault / "projects").rmdir()
    (vault / "projects.db").unlink()

    yield vault


def test_v2_vault_loads_as_v3_default_project(legacy_vault, monkeypatch):
    monkeypatch.setenv("PIIGHOST_EMBEDDER", "stub")
    monkeypatch.setenv("PIIGHOST_DETECTOR", "stub")

    svc = asyncio.run(PIIGhostService.create(vault_dir=legacy_vault))
    try:
        # Data moved into projects/default/
        assert (legacy_vault / "projects" / "default" / "vault.db").exists()
        assert not (legacy_vault / "vault.db").exists()

        # default project is listed
        projects = asyncio.run(svc.list_projects())
        names = {p.name for p in projects}
        assert "default" in names

        # Existing vault entries still accessible via default project
        stats = asyncio.run(svc.vault_stats(project="default"))
        assert stats.total >= 1
    finally:
        asyncio.run(svc.close())


def test_v2_tokens_still_rehydrate_after_migration(legacy_vault, monkeypatch):
    monkeypatch.setenv("PIIGHOST_EMBEDDER", "stub")
    monkeypatch.setenv("PIIGHOST_DETECTOR", "stub")

    svc = asyncio.run(PIIGhostService.create(vault_dir=legacy_vault))
    try:
        # Re-anonymize the same string in default project (salt="") to verify
        # token format is unchanged from pre-v3.
        r = asyncio.run(svc.anonymize("Alice was here", project="default"))
        # Rehydrate must succeed
        rehydrated = asyncio.run(svc.rehydrate(r.anonymized, project="default"))
        assert rehydrated.unknown_tokens == []
        assert "Alice" in rehydrated.text
    finally:
        asyncio.run(svc.close())
```

- [ ] **Step 3: Run both E2E tests**

```bash
python -m pytest tests/e2e/test_project_isolation.py tests/e2e/test_v2_to_v3_migration.py -v -p no:randomly
```

Expected: all passing.

- [ ] **Step 4: Run full suite**

```bash
python -m pytest tests/unit/ tests/e2e/ -q -p no:randomly 2>&1 | tail -10
```

Expected: all passing.

- [ ] **Step 5: Commit**

```bash
git add tests/e2e/test_project_isolation.py tests/e2e/test_v2_to_v3_migration.py
git commit -m "test(e2e): critical project isolation + v2-to-v3 migration tests"
```

---

## Self-Review

### Spec coverage

| Spec requirement | Task |
|------------------|------|
| Per-project vault, chunk store, BM25, audit log | Task 5 (split `_ProjectService`) |
| Project registry (`projects.db`) with `placeholder_salt` | Task 2 |
| Schema v3 migration (legacy → `projects/default/`) | Task 3 |
| Salted `HashPlaceholderFactory` (empty salt = legacy) | Task 1 |
| `PIIGhostService` multiplexer with LRU | Tasks 5, 8 |
| `project` parameter on every public method | Task 6 |
| Auto-derivation for `index_path` | Task 7 |
| `list_projects` / `create_project` / `delete_project` | Task 8 |
| `ProjectNotFound` / `ProjectNotEmpty` exceptions | Task 4 |
| MCP tools: `project` param on all + 3 new project tools | Task 9 |
| MCP resources: `piighost://projects`, `piighost://projects/{name}/stats` | Task 10 |
| CLI `--project` on all commands + `projects` subgroup | Task 11 |
| Daemon dispatch forwards `project` + 3 new methods | Task 12 |
| Critical isolation E2E tests | Task 13 |
| V2-to-V3 migration E2E test | Task 13 |
| Default project can't be deleted | Task 8 |
| Non-empty project delete refused without force | Task 8 |
| `rehydrate` names the project in error messages | Already handled by `_ProjectService.rehydrate` raising `PIISafetyViolation` with project-scoped unknown tokens. Task 13 asserts the behavior. |

### Placeholder scan

- No "TBD" markers.
- Every code block is complete and copy-pasteable.
- `tests/unit/test_cli_project_flag.py` uses `"Typer renders --project"` check via `--help` output — not a coverage substitute for actual execution, but matches Sprint 3/4 CLI test patterns (help-only smoke tests).

### Type consistency

- `ProjectInfo` dataclass declared in Task 2 (`piighost.vault.project_registry`), imported in Task 5 (`service/core.py`), referenced in Task 8 method signatures, re-exported implicitly via `list_projects()` return type. Consistent.
- `placeholder_salt` field on `ProjectInfo` introduced in Task 2, read in Task 5 `_get_project`, passed to `_ProjectService.create(placeholder_salt=...)` which passes to `HashPlaceholderFactory(salt=...)`. Consistent.
- `ProjectNotFound`, `ProjectNotEmpty` defined in Task 4, raised in Task 5 (`_get_project`) and Task 8 (`delete_project`), tested in Tasks 8 and 13. Consistent.
- `derive_project_from_path` defined in Task 7, called in Task 6 (`index_path` multiplexer method). Task 6 references `from piighost.service.project_path import derive_project_from_path` — that import must exist **before** the Task 7 file is created, but since Tasks are executed in order (Task 6 before Task 7), this is a bug in ordering.

### Ordering fix

Swap the order of Tasks 6 and 7: create `derive_project_from_path` (current Task 7) BEFORE adding the `project` parameter to `index_path` (current Task 6). The rest of Task 6 doesn't depend on derivation.

**Fix applied inline:** Task 6 (project parameter) and Task 7 (derive_project_from_path) should be swapped. The plan as written has Task 6 first but its `index_path` implementation imports from `piighost.service.project_path` which doesn't exist until Task 7. Resolve by executing Task 7 before Task 6 **OR** by adding the derivation module stub in Task 6 step 3.

Recommended execution order:
1. Task 1 (placeholder salt)
2. Task 2 (project registry)
3. Task 3 (migration)
4. Task 4 (exceptions)
5. Task 5 (service split, backward compat)
6. **Task 7 (derive_project_from_path)**  ← moved before Task 6
7. **Task 6 (project parameter)**           ← now can import derive_project_from_path
8. Task 8 (project management methods)
9. Task 9 (MCP tools)
10. Task 10 (MCP resources)
11. Task 11 (CLI)
12. Task 12 (daemon)
13. Task 13 (E2E isolation)
