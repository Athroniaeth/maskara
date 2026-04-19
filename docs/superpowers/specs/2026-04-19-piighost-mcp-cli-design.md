# piighost CLI + MCP Server Design

**Date:** 2026-04-19
**Status:** Design approved, pending implementation plan
**Supersedes:** N/A (new subsystem)

## 1. Goal

Ship two new interfaces for the existing `piighost` library:

1. **CLI (`piighost`)** — agent-friendly command-line tool for GDPR-compliant PII anonymization workflows (detect, anonymize, rehydrate, index, query).
2. **MCP server (`piighost serve --mcp`)** — Model Context Protocol server exposing the same functionality to Claude Desktop / Cursor / any MCP-capable host.

Both must work well on Windows, macOS, and Linux, and share one stateful core so every feature is reachable from both interfaces with identical semantics.

## 2. Architecture

### 2.1 Three-layer model

```
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│   CLI        │  │   MCP        │  │  Daemon HTTP │
│  (typer)     │  │  (FastMCP)   │  │  (JSON-RPC)  │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                 │
       └─────────────────┴─────────────────┘
                         │
                 ┌───────▼────────┐
                 │  PIIGhostService│      ← stateful core
                 │   (async)       │
                 └───────┬────────┘
                         │
       ┌─────────────────┼─────────────────┐
       │                 │                 │
  ┌────▼─────┐    ┌──────▼──────┐   ┌──────▼──────┐
  │  Vault   │    │  Detector   │   │  Embedder   │
  │ (SQLite) │    │  (GLiNER2)  │   │   (Solon/   │
  │          │    │             │   │   Mistral)  │
  └──────────┘    └─────────────┘   └─────────────┘
```

**Rationale:** CLI, MCP, and daemon are thin adapters. All business logic lives in `PIIGhostService`. Test once, ship three interfaces. No duplicated anonymization/rehydration code paths.

### 2.2 Service layer API

`src/piighost/service/__init__.py`:

```python
class PIIGhostService:
    """Stateful core. One instance per vault. Thread-safe."""

    @classmethod
    async def create(cls, vault_dir: Path) -> "PIIGhostService":
        """Load config, open vault, warm detector, warm embedder."""

    # --- Core ops ---
    async def anonymize(self, text: str, *, doc_id: str | None = None) -> AnonymizeResult
    async def rehydrate(self, text: str, *, strict: bool = True) -> RehydrateResult
    async def detect(self, text: str) -> list[Detection]
    async def classify(self, text: str, schema: str) -> ClassifyResult

    # --- Vault ops ---
    async def vault_list(self, *, label: str | None = None, cursor: str | None = None,
                          limit: int = 100) -> VaultPage
    async def vault_show(self, token: str, *, reveal: bool = False) -> VaultEntry | None
    async def vault_stats(self) -> VaultStats
    async def vault_search(self, query: str, *, reveal: bool = False) -> list[VaultEntry]

    # --- Index ops (Sprint 2) ---
    async def index_path(self, path: Path, *, recursive: bool = True,
                          progress: ProgressCallback | None = None) -> IndexReport
    async def query(self, text: str, *, k: int = 5) -> QueryResult

    # --- Lifecycle ---
    async def flush(self) -> None
    async def close(self) -> None
```

**Invariants:**
- All methods async. CLI wraps with `asyncio.run` per call (cold mode) or reuses daemon event loop (warm mode).
- Return types are `pydantic` models → auto-serialize to JSON for CLI stdout and MCP tool results.
- Raw PII never appears in exceptions. Enforced by test (fuzz 1000 inputs, grep errors for originals).
- Vault is the single source of truth for `token ↔ original` mapping.
- `placeholder_factory` is always `HashPlaceholderFactory` — counter mode intentionally unsupported (breaks RAG determinism).

## 3. Vault

### 3.1 Scope and discovery

- One `.piighost/` directory per project.
- **Git-style upward walk** from cwd to find `.piighost/` (stops at drive root).
- `--vault <dir>` flag overrides auto-discovery.
- `piighost init` creates `.piighost/` in cwd with `config.toml`, empty `vault.db`, empty `audit.log`.

### 3.2 Storage: SQLite (not JSON)

File: `.piighost/vault.db`. WAL mode enabled (concurrent daemon + CLI access).

```sql
CREATE TABLE entities (
    token TEXT PRIMARY KEY,          -- <PERSON:a1b2c3d4>
    original TEXT NOT NULL,          -- raw string (never returned without reveal=true)
    label TEXT NOT NULL,             -- PERSON, LOC, ORG, ...
    confidence REAL,                 -- last-seen confidence
    first_seen_at INTEGER NOT NULL,  -- unix seconds
    last_seen_at INTEGER NOT NULL,
    occurrence_count INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE doc_entities (
    doc_id TEXT NOT NULL,
    token TEXT NOT NULL REFERENCES entities(token),
    start_pos INTEGER,
    end_pos INTEGER,
    PRIMARY KEY (doc_id, token, start_pos)
);

CREATE TABLE audit_log (
    ts INTEGER NOT NULL,
    caller_pid INTEGER,
    caller_kind TEXT,               -- "cli" | "mcp" | "daemon-http"
    op TEXT NOT NULL,               -- "rehydrate" | "vault_show_reveal" | "vault_search"
    token TEXT,
    metadata_json TEXT
);

CREATE INDEX idx_entities_label ON entities(label);
CREATE INDEX idx_doc_entities_doc ON doc_entities(doc_id);
CREATE INDEX idx_audit_ts ON audit_log(ts);
```

### 3.3 Placeholder factory

**Hash only.** `<LABEL:8-hex>` where hex is `sha256(original.lower() + ":" + label)[:8]`.

Rationale: deterministic token identity across sessions is required for RAG (BM25/vector token match between doc path and query path). Counter mode was rejected during brainstorming.

For human-readable output, optional cosmetic rendering exists but does not change stored state.

## 4. CLI

### 4.1 Command surface

**Sprint 1 (MVP):**
- `piighost init` — create `.piighost/`
- `piighost anonymize <path|->` — detect + anonymize; writes to vault; prints result
- `piighost rehydrate <path|->` — reverse lookup via vault
- `piighost detect <path|->` — detection only, no vault mutation
- `piighost vault list [--label X] [--limit N]`
- `piighost vault show <token> [--reveal]`
- `piighost vault stats`
- `piighost daemon start|stop|status|restart|logs`

**Sprint 2:**
- `piighost index <dir> [--recursive]` — Kreuzberg ingest + anonymize + embed
- `piighost query "<text>" [-k 5]` — anonymize query, hybrid retrieve, rehydrate
- `piighost classify <path> --schema gdpr`
- `piighost serve --mcp [--stdio|--sse]`
- `piighost vault search <query> [--reveal]`

### 4.2 Output contract

**Default:** JSON Lines on stdout, human messages on stderr.

```bash
$ echo "Alice lives in Paris" | piighost anonymize -
{"doc_id":"<stdin>","anonymized":"<PERSON:a1b2c3d4> lives in <LOC:ff009922>.","entities":[...],"stats":{"chars_in":20,"chars_out":46,"ms":42}}
```

**`--pretty`** → Rich-formatted, colorized output for humans.

**Batch:** one JSON line per input file; stream line-by-line.

**Errors:** structured JSON on stderr, nonzero exit code:

```json
{"error":"VaultNotFound","message":"No .piighost/ in cwd or ancestors","hint":"Run `piighost init` or pass --vault","exit_code":2}
```

### 4.3 Exit code taxonomy

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Unexpected error (bug — file issue) |
| 2 | User/config error (no vault, bad path, bad flag) |
| 3 | Detection/anonymization failed (whole op aborted; no partial output) |
| 4 | Daemon unreachable (distinct so agents retry-with-spawn) |
| 5 | PII safety violation (unknown token in strict rehydrate, etc.) |

### 4.4 Config precedence

CLI flag > env var (`PIIGHOST_*`) > `config.toml` > built-in default.

## 5. Daemon

### 5.1 Purpose

Avoid 2s GLiNER2 cold-start per CLI invocation. Agents calling `piighost` 10× should not pay 20s startup.

### 5.2 Transport

- **TCP on `127.0.0.1` + token.** Cross-platform. No Unix-socket / Windows named-pipe branching.
- Daemon writes `.piighost/daemon.json = {pid, port, token, started_at}` atomically (`write_tmp + os.replace`).
- CLI reads the file, connects, sends `Authorization: Bearer <token>`.
- Protocol: **JSON-RPC 2.0 over HTTP** (`POST /rpc`, methods = service layer methods). Same wire format MCP can tunnel if needed.

### 5.3 Lifecycle

- **Auto-spawn on first call.** CLI checks `daemon.json`; stale or missing → spawn; alive → connect.
- **Spawn race guard:** `portalocker` on `.piighost/daemon.lock`. First acquirer spawns; others wait + read `daemon.json`.
- **Process detach:** `subprocess.Popen(creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP)` on Windows; `start_new_session=True` on POSIX.
- **Stale detection:** via `psutil` — PID dead OR port unreachable OR `daemon.json` > 30 days old → kill remnants, respawn.
- **Idle timeout:** config-driven (`[daemon] idle_timeout_sec = 3600`). Daemon self-exits after idle.
- **Shutdown:** `piighost daemon stop` → HTTP `POST /shutdown` with token → flush vault, exit. Fallback: `psutil.Process(pid).terminate()` then `.kill()` after 5s.
- **Scope:** one daemon per vault. Two projects = two daemons on two OS-assigned ports.
- **Escape hatch:** `piighost --no-daemon <cmd>` runs inline (cold start). For CI where spawning background procs is undesirable.

### 5.4 Windows hardening

- `psutil` for all process operations.
- `portalocker` for cross-platform file locking.
- Path handling via `pathlib.Path`, never string concatenation.
- Daemon logs to `.piighost/daemon.log` (rotating, 10MB × 3) — no tty for detached process.
- Token file ACLs: best-effort. Loopback-bound + bearer token make this acceptable.
- CI matrix: `windows-latest`, `ubuntu-latest`, `macos-latest`. Smoke test per platform: spawn → anonymize → stop.

## 6. MCP Server

### 6.1 Framework

**FastMCP.** New dependency added via `piighost[mcp]` extra. Supports stdio (Claude Desktop) and sse/streamable-http (remote) transports from the same codebase.

### 6.2 Tool surface

| Tool | Service method | Sensitive | Notes |
|---|---|---|---|
| `anonymize_text` | `anonymize` | no | stdin-like single string |
| `anonymize_document` | `anonymize` + Kreuzberg | no | file path arg |
| `rehydrate` | `rehydrate` | **yes** | audit-logged |
| `detect` | `detect` | no | no vault mutation |
| `vault_list` | `vault_list` | no | pagination via `cursor` |
| `vault_show` | `vault_show` | **yes if `reveal=true`** | redacted by default |
| `vault_stats` | `vault_stats` | no | |
| `vault_search` | `vault_search` | **yes** | gated; audit-logged |
| `index_folder` | `index_path` | no | progress notifications |
| `query` | `query` | no | RAG endpoint; rehydrates results |
| `classify` | `classify` | no | |

Sensitive tools write to `audit.log`. `vault_show` returns redacted originals (`J*** D***`) by default; `reveal=true` reveals full original and logs caller identity.

### 6.3 Resource endpoints

Expose read-only vault metadata as MCP resources (don't burn tool-call budget):

- `piighost://vault/stats`
- `piighost://vault/config`
- `piighost://vault/labels`

### 6.4 Long-running tools

`index_folder` and `query` (large k) use FastMCP progress notifications:

```json
{"progress": 0.4, "stage": "embedding", "message": "45/120 docs"}
```

### 6.5 Client configuration

Example `.mcp.json` for Claude Desktop:

```json
{
  "mcpServers": {
    "piighost": {
      "command": "piighost",
      "args": ["serve", "--mcp", "--vault", "/abs/path/to/.piighost"]
    }
  }
}
```

MCP server auto-connects to a running daemon if present; otherwise spawns one. Same logic as CLI.

## 7. Config schema (`.piighost/config.toml`)

```toml
schema_version = 1

[vault]
placeholder_factory = "hash"       # hash only — counter unsupported
audit_log = true

[detector]
backend = "gliner2"                # gliner2 | regex_only (extension points reserved, not shipped Sprint 1)
gliner2_model = "fastino/gliner2-multi-v1"
threshold = 0.5
labels = ["PERSON", "LOC", "ORG", "EMAIL", "PHONE", "IBAN", "CREDIT_CARD", "ID"]

[embedder]
backend = "local"                  # local | mistral | none
local_model = "OrdalieTech/Solon-embeddings-base-0.1"
mistral_model = "mistral-embed"
# MISTRAL_API_KEY from env

[index]
store = "lancedb"
chunk_size = 512
chunk_overlap = 64
bm25_weight = 0.4
vector_weight = 0.6

[daemon]
idle_timeout_sec = 3600
log_level = "info"
max_workers = 4

[safety]
strict_rehydrate = true            # unknown tokens → error, not pass-through
max_doc_bytes = 10_485_760         # 10MB per doc
redact_errors = true               # never leak PII in error messages
```

## 8. Dependencies

### New runtime dependencies

- `typer` or `click` — CLI framework
- `rich` — pretty output
- `httpx` — daemon client (already dev-pinned)
- `psutil` — cross-platform process management
- `portalocker` — cross-platform file locking
- `fastmcp` (via `piighost[mcp]` extra)
- `kreuzberg` — promoted from test-only to base dep (all doc types supported OOTB)
- `sqlite3` — stdlib, no install

### New optional extras

- `piighost[mcp]` → adds `fastmcp`
- Existing: `piighost[gliner2]`, `piighost[langchain]`, `piighost[haystack]`, etc.

Install weight target: base `pip install piighost` ≤ 300 MB (dominated by kreuzberg + gliner2 + onnxruntime).

## 9. Safety invariants

1. **Raw PII never in errors.** Enforced by fuzz test (1000 synthetic inputs, grep stderr).
2. **Strict rehydration.** Unknown tokens → error, not silent pass-through (configurable).
3. **Audit every sensitive op.** `rehydrate`, `vault_show --reveal`, `vault_search` append to `audit.log`.
4. **Redact by default.** MCP `vault_show` returns masked originals unless `reveal=true` (then audited).
5. **No partial anonymization.** If any stage fails mid-doc, abort the whole doc. No `"Alice lives in <LOC:...>"` leakage.
6. **Hash-only placeholders.** Counter factory is a compile-time reject in Service init.
7. **Vault access is local.** Daemon binds `127.0.0.1`. No remote vault in Sprint 1-2.

## 10. Sprints

### Sprint 1 — CLI + daemon (2 weeks)

1. `Service` layer scaffolding + async methods over existing `piighost` core
2. SQLite vault schema + migrations + audit log
3. CLI commands: `init`, `anonymize`, `rehydrate`, `detect`, `vault list/show/stats`
4. Daemon: auto-spawn, TCP+token, JSON-RPC endpoints, `psutil` lifecycle, `portalocker` race guard
5. Windows/macOS/Linux CI matrix with smoke tests
6. JSON output contract + exit code taxonomy + `--pretty` mode
7. Snapshot tests per command (`tests/cli/snapshots/`)
8. PII-in-errors fuzz test

### Sprint 2 — MCP + indexing (2-3 weeks)

1. Kreuzberg integration in `Service.index_path` (all doc types)
2. LanceDB embed/store (Solon local, Mistral optional)
3. Hybrid BM25 + vector retrieval (reuse LangChain `EnsembleRetriever` work)
4. FastMCP server adapter, all 11 tools (see §6.2), resource endpoints, progress notifications
5. Claude Desktop integration guide + example `.mcp.json`
6. E2E test: index corpus → query → rehydrate → verify token identity + zero raw-PII leak to cloud embedder (httpx.MockTransport proof)

### Deferred (Sprint 3+)

- `classify` as first-class CLI/MCP surface (backend already exists in `Service`)
- Vault migration tooling (schema version bumps)
- Remote vault (HTTPS + auth)
- Multi-user / RBAC
- Windows Service / systemd unit wrappers for daemon

## 11. Acceptance criteria

### Sprint 1

- [ ] `pip install piighost && piighost init && echo "Alice lives in Paris" | piighost anonymize -` works on Windows, macOS, Linux
- [ ] Second `anonymize` call (daemon warm) completes in <100 ms
- [ ] Cold-start (`--no-daemon`) completes in <3 s on laptop CPU
- [ ] Fuzz test: 1000 synthetic inputs × all commands → 0 raw-PII leaks in stderr
- [ ] `piighost daemon stop && piighost daemon status` round-trips cleanly on all platforms
- [ ] `audit.log` records every `rehydrate` and `vault_show --reveal` call with timestamp + caller metadata
- [ ] Concurrent CLI spawn race (2 processes, empty vault) produces exactly 1 daemon

### Sprint 2

- [ ] `piighost index <dir>` processes 100 mixed PDF/DOCX/TXT docs in <2 min on laptop
- [ ] `piighost query "Alice"` via MCP returns correct documents with rehydrated answers
- [ ] `httpx.MockTransport` proof test: zero raw-PII strings appear in outbound Mistral embed requests
- [ ] Claude Desktop user can install + connect via `.mcp.json` in <5 min from quickstart
- [ ] Hybrid retrieval test: indexed "Alain Dupont" documents retrievable via anonymized query, BM25 leg proven to hit via token-identity assertion

## 12. Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Windows daemon detach flakiness | Medium | `psutil`-only process ops; CI on `windows-latest`; `--no-daemon` escape hatch |
| Kreuzberg install size balloon | Low | Base install measured in CI; limit 300 MB |
| Agent accidentally dumps full vault via `vault_list` | Medium | Redact-by-default; `--reveal` gated + audited |
| Port collision in daemon spawn | Low | OS-assigned port (`bind(..., 0)`) |
| Concurrent vault writes corrupt SQLite | Low | WAL mode + short transactions; all writes serialized through daemon when present |
| Hash collision in 8-hex token space | Very low | 2^32 entities per label before collision; detected at insert; escalate to 12-hex if needed |
| GLiNER2 model download at first run | High | Document; pre-pull in `piighost init` with `--warm-models` flag |

## 13. Out of scope

- Counter-mode placeholders (explicitly rejected — breaks RAG)
- Cross-vault operations (merging, remote sync)
- Multi-tenant daemon (one daemon per vault, period)
- Authentication beyond local token (no OAuth, no SSO)
- GPU inference paths for GLiNER2 (CPU only for Sprint 1-2)
- Real-time streaming anonymization (batch-only)
