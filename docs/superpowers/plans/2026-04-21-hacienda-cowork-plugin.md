# Hacienda Cowork Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a Claude Desktop Cowork plugin named `hacienda` that wraps piighost's MCP server with a PII-safe, folder-scoped knowledge-base experience for regulated professionals — published to the official Anthropic marketplace.

**Architecture:** Pure configuration + prose + small Python hook scripts on top of a vendored piighost MCP server. No new server code. Redacted-transit confidentiality v1: outbound PreToolUse hook redacts via the `piighost` CLI; inbound retrieval results are already redacted server-side. Folder↔project mapping is a deterministic hash of the Cowork-active path. FR + EN localization. MIT license + external paid-support contracts.

**Tech Stack:** Python 3.11 (hooks + bootstrap), JSON (manifests), Markdown+YAML (skills/commands/agents), pytest + pytest-mock for tests, `uv` for the vendored piighost runtime, GitHub Actions for CI, `mcpb` CLI for packaging.

**Spec:** `docs/superpowers/specs/2026-04-21-hacienda-cowork-plugin-design.md`

**Target repo layout:** `C:\Users\NMarchitecte\Documents\hacienda\` (new, separate repo).

**Cowork plugin contract (per confirmed Cowork guidance — NOT the Claude Code plugin reference; Cowork ≠ Claude Code):**
- **Skills are passive markdown.** `skills/<name>/SKILL.md` frontmatter accepts only `name` and `description`. No `allowed-tools`, no Python, no executables. Skills describe procedure; tool availability comes from `.mcp.json`, commands, or agents.
- **Commands can invoke tools** via `allowed-tools` in their frontmatter. To run Python: `allowed-tools: Bash(python:*)` invoking a script from `scripts/`.
- **Agents declare tools** via `tools: [...]` allowlist in frontmatter. To run Python: include `Bash` in `tools` and have the agent shell out to a `scripts/*.py` script.
- **Python lives in `hooks/` or `scripts/`** — never in `skills/`. Skill-creator precedent uses `scripts/`.
- **MCP servers** declared in `.mcp.json` expose Python capabilities as tools.

**Open questions (flagged, NOT assumed):**
- **Env var name for the plugin root**: the plan uses `${CLAUDE_PLUGIN_ROOT}` in hook/command/monitor paths. Claude Code documents this name; I have not verified it for Cowork. Before Task 1 ships, the implementer MUST check the Cowork plugin docs (or a reference Cowork plugin) and, if different, do a single global find-and-replace across `hooks.json`, `.mcp.json`, `monitors.json`, and the bootstrap entry. Every path in the plan flows through this one variable name, so the fix is mechanical.
- **Valid hook events**: the plan uses `PreToolUse` and `PostToolUse` (both standard). If Cowork uses a different event vocabulary, adjust `hooks/hooks.json` accordingly — the Python hook scripts themselves are event-name-agnostic.

---

## File Structure (final target)

```
hacienda/
├── .claude-plugin/
│   └── plugin.json
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── vendor-sync.yml
├── skills/
│   ├── knowledge-base/
│   │   ├── SKILL.md
│   │   └── SKILL.fr.md
│   └── redact-outbound/
│       ├── SKILL.md
│       └── SKILL.fr.md
├── commands/
│   ├── index.md
│   ├── kb-status.md
│   ├── audit.md
│   ├── brief.md
│   └── draft-reply.md
├── agents/
│   └── redaction-agent.md
├── hooks/
│   ├── hooks.json
│   ├── redact.py
│   ├── rehydrate.py
│   └── _hacienda_hooks/
│       ├── __init__.py
│       ├── project_resolver.py
│       ├── piighost_cli.py
│       └── audit_log.py
├── monitors/
│   └── monitors.json
├── scripts/
│   ├── hacienda-bootstrap
│   ├── hacienda-bootstrap.cmd
│   ├── vendor-piighost.sh
│   ├── package-mcpb.sh
│   └── _hacienda_bootstrap/
│       ├── __init__.py
│       ├── datadir.py
│       ├── keychain.py
│       └── daemon.py
├── tests/
│   ├── conftest.py
│   ├── test_project_resolver.py
│   ├── test_redact_hook.py
│   ├── test_rehydrate_hook.py
│   ├── test_audit_log.py
│   ├── test_piighost_cli.py
│   ├── test_bootstrap_datadir.py
│   ├── test_bootstrap_keychain.py
│   ├── test_manifest_schema.py
│   ├── test_hooks_json_schema.py
│   ├── test_skill_frontmatter.py
│   └── test_mcp_json_schema.py
├── vendor/
│   └── piighost/                 # populated by scripts/vendor-piighost.sh (gitignored below a pinned marker)
├── locales/
│   ├── en.json
│   └── fr.json
├── .mcp.json
├── settings.json
├── icon.png
├── LICENSE
├── README.md
├── README.fr.md
├── pyproject.toml                # dev-only; deps for hooks + tests
├── .gitignore
└── .python-version
```

---

## Task 0: Repo bootstrap

**Files:**
- Create: `C:\Users\NMarchitecte\Documents\hacienda\.gitignore`
- Create: `C:\Users\NMarchitecte\Documents\hacienda\.python-version`
- Create: `C:\Users\NMarchitecte\Documents\hacienda\LICENSE`
- Create: `C:\Users\NMarchitecte\Documents\hacienda\README.md` (stub)
- Create: `C:\Users\NMarchitecte\Documents\hacienda\pyproject.toml`

- [ ] **Step 1: Initialize repo**

```bash
mkdir -p "C:/Users/NMarchitecte/Documents/hacienda"
cd "C:/Users/NMarchitecte/Documents/hacienda"
git init -b main
```

- [ ] **Step 2: Write `.gitignore`**

```
# Python
__pycache__/
*.py[cod]
.venv/
.pytest_cache/
.ruff_cache/

# Vendor (pulled by scripts/vendor-piighost.sh — deterministic, not tracked)
vendor/piighost/
!vendor/piighost/.gitkeep

# OS
.DS_Store
Thumbs.db

# Local data
.hacienda/
```

- [ ] **Step 3: Write `.python-version`**

```
3.11
```

- [ ] **Step 4: Write `LICENSE` (MIT, 2026, piighost team)**

Copy the standard MIT license text with copyright line:
```
Copyright (c) 2026 piighost team
```
Full MIT text body follows standard template from https://opensource.org/licenses/MIT.

- [ ] **Step 5: Write `README.md` stub**

```markdown
# hacienda

The Cowork plugin that makes Claude Desktop safe under professional secrecy.

PII-safe RAG over your client folders, directly inside Claude Desktop.

**Status:** pre-alpha — see `docs/superpowers/plans/2026-04-21-hacienda-cowork-plugin.md`.

## License

MIT — see [LICENSE](LICENSE).
```

- [ ] **Step 6: Write `pyproject.toml`** (dev-only; hooks are zero-dep at runtime, pytest is dev-only)

```toml
[project]
name = "hacienda-plugin-dev"
version = "0.0.0"
description = "Dev-time tooling for the hacienda Claude Desktop Cowork plugin"
requires-python = ">=3.11"
dependencies = []

[project.optional-dependencies]
dev = [
  "pytest>=8",
  "pytest-mock>=3.12",
  "jsonschema>=4.21",
  "pyyaml>=6.0",
  "ruff>=0.4",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["hooks", "scripts"]

[tool.ruff]
line-length = 100
target-version = "py311"
```

- [ ] **Step 7: Create empty `vendor/piighost/.gitkeep`**

```bash
mkdir -p vendor/piighost
touch vendor/piighost/.gitkeep
```

- [ ] **Step 8: Commit**

```bash
git add .
git commit -m "chore: initialize hacienda plugin repo"
```

---

## Task 1: Plugin manifest

**Files:**
- Create: `.claude-plugin/plugin.json`
- Create: `tests/test_manifest_schema.py`

- [ ] **Step 1: Write the failing test**

`tests/test_manifest_schema.py`:
```python
import json
from pathlib import Path

import jsonschema

MANIFEST = Path(__file__).parent.parent / ".claude-plugin" / "plugin.json"

MANIFEST_SCHEMA = {
    "type": "object",
    "required": ["name", "version", "description", "author", "license", "homepage"],
    "properties": {
        "name": {"type": "string", "pattern": "^[a-z][a-z0-9-]{1,63}$"},
        "version": {"type": "string", "pattern": r"^\d+\.\d+\.\d+(?:-[a-z0-9.-]+)?$"},
        "description": {"type": "string", "minLength": 20, "maxLength": 200},
        "author": {
            "type": "object",
            "required": ["name"],
            "properties": {"name": {"type": "string"}, "email": {"type": "string"}},
        },
        "license": {"type": "string"},
        "homepage": {"type": "string", "format": "uri"},
        "categories": {"type": "array", "items": {"type": "string"}},
        "keywords": {"type": "array", "items": {"type": "string"}},
    },
}


def test_manifest_exists():
    assert MANIFEST.is_file()


def test_manifest_schema_valid():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    jsonschema.validate(data, MANIFEST_SCHEMA)


def test_manifest_name_is_hacienda():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert data["name"] == "hacienda"


def test_manifest_license_is_mit():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert data["license"] == "MIT"
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
cd "C:/Users/NMarchitecte/Documents/hacienda" && uv run --with ".[dev]" pytest tests/test_manifest_schema.py -v
```
Expected: 4 tests fail — `FileNotFoundError` on `plugin.json`.

- [ ] **Step 3: Write manifest**

`.claude-plugin/plugin.json`:
```json
{
  "name": "hacienda",
  "version": "0.1.0",
  "description": "PII-safe RAG over your client folders, directly inside Claude Desktop. Built for regulated professionals bound by professional secrecy.",
  "author": {
    "name": "piighost team",
    "email": "jamon8888@users.noreply.github.com"
  },
  "license": "MIT",
  "homepage": "https://github.com/jamon8888/hacienda",
  "categories": ["knowledge", "security", "productivity"],
  "keywords": ["rag", "pii", "gdpr", "legal", "professional-secrecy", "knowledge-base"]
}
```

- [ ] **Step 4: Run test — expect PASS**

```bash
uv run --with ".[dev]" pytest tests/test_manifest_schema.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add .claude-plugin/plugin.json tests/test_manifest_schema.py
git commit -m "feat: plugin manifest with schema test"
```

---

## Task 2: Vendor piighost MCP server

**Files:**
- Create: `scripts/vendor-piighost.sh`
- Create: `.mcp.json`
- Create: `tests/test_mcp_json_schema.py`

- [ ] **Step 1: Write the failing test**

`tests/test_mcp_json_schema.py`:
```python
import json
from pathlib import Path

import jsonschema

MCP_JSON = Path(__file__).parent.parent / ".mcp.json"

MCP_SCHEMA = {
    "type": "object",
    "required": ["mcpServers"],
    "properties": {
        "mcpServers": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "required": ["command"],
                "properties": {
                    "command": {"type": "string"},
                    "args": {"type": "array", "items": {"type": "string"}},
                    "env": {"type": "object"},
                    "type": {"type": "string"},
                },
            },
        }
    },
}


def test_mcp_json_exists():
    assert MCP_JSON.is_file()


def test_mcp_json_schema_valid():
    data = json.loads(MCP_JSON.read_text(encoding="utf-8"))
    jsonschema.validate(data, MCP_SCHEMA)


def test_mcp_json_exposes_hacienda_server():
    data = json.loads(MCP_JSON.read_text(encoding="utf-8"))
    assert "hacienda" in data["mcpServers"]
    server = data["mcpServers"]["hacienda"]
    assert "piighost" in server["command"] or any("piighost" in a for a in server.get("args", []))


def test_mcp_json_uses_plugin_dir_variable():
    raw = MCP_JSON.read_text(encoding="utf-8")
    assert "${CLAUDE_PLUGIN_ROOT}" in raw, "server path must be relocatable via CLAUDE_PLUGIN_ROOT"
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
uv run --with ".[dev]" pytest tests/test_mcp_json_schema.py -v
```
Expected: `FileNotFoundError` on `.mcp.json`.

- [ ] **Step 3: Write vendor sync script**

`scripts/vendor-piighost.sh`:
```bash
#!/usr/bin/env bash
# Copy the piighost "full" bundle into vendor/piighost.
# Called manually on piighost release bumps; mirrored by .github/workflows/vendor-sync.yml.
set -euo pipefail

SRC="${PIIGHOST_BUNDLE_SRC:-../piighost/bundles/full}"
DST="vendor/piighost"

if [ ! -d "$SRC" ]; then
  echo "error: piighost bundle source not found at $SRC" >&2
  echo "set PIIGHOST_BUNDLE_SRC to override" >&2
  exit 1
fi

rm -rf "$DST"
mkdir -p "$DST"
cp -R "$SRC/." "$DST/"
touch "$DST/.gitkeep"

# Record the pinned version for reproducibility
if [ -f "$SRC/manifest.json" ]; then
  python3 -c "import json,sys; m=json.load(open('$SRC/manifest.json')); print(m.get('version','unknown'))" > "$DST/.version"
fi

echo "Vendored piighost $(cat $DST/.version 2>/dev/null || echo 'unknown') into $DST"
```

Make it executable:
```bash
chmod +x scripts/vendor-piighost.sh
```

- [ ] **Step 4: Run vendor script**

```bash
PIIGHOST_BUNDLE_SRC="../piighost/bundles/full" bash scripts/vendor-piighost.sh
```

Expected output: `Vendored piighost 0.X.Y into vendor/piighost`. `ls vendor/piighost/manifest.json` must succeed.

- [ ] **Step 5: Write `.mcp.json`**

```json
{
  "mcpServers": {
    "hacienda": {
      "command": "uv",
      "args": [
        "run",
        "--project",
        "${CLAUDE_PLUGIN_ROOT}/vendor/piighost",
        "piighost",
        "mcp",
        "serve"
      ],
      "env": {
        "PIIGHOST_DATA_DIR": "${HOME}/.hacienda",
        "PIIGHOST_VAULT_KEY_SOURCE": "keychain:hacienda"
      }
    }
  }
}
```

- [ ] **Step 6: Run test — expect PASS**

```bash
uv run --with ".[dev]" pytest tests/test_mcp_json_schema.py -v
```
Expected: 4 passed.

- [ ] **Step 7: Commit**

```bash
git add scripts/vendor-piighost.sh .mcp.json tests/test_mcp_json_schema.py vendor/piighost/.gitkeep
git commit -m "feat: vendor piighost MCP server + .mcp.json wiring"
```

*(Note: `vendor/piighost/` contents are gitignored except the marker files. The vendor-sync workflow in Task 17 repopulates on every build.)*

---

## Task 3: Project resolver

**Files:**
- Create: `hooks/_hacienda_hooks/__init__.py`
- Create: `hooks/_hacienda_hooks/project_resolver.py`
- Create: `tests/test_project_resolver.py`

Design: the Cowork-active folder path is passed to every hook via the `HACIENDA_ACTIVE_FOLDER` environment variable (set by the bootstrap — see Task 7). The resolver converts that to a stable short project name for piighost.

- [ ] **Step 1: Write the failing test**

`tests/test_project_resolver.py`:
```python
from pathlib import Path

import pytest

from _hacienda_hooks.project_resolver import resolve_project_name


def test_resolve_project_name_is_deterministic():
    p = Path("Z:/Dossiers/ACME")
    assert resolve_project_name(p) == resolve_project_name(p)


def test_resolve_project_name_prefix_is_folder_basename_lowercased():
    assert resolve_project_name(Path("Z:/Dossiers/ACME")).startswith("acme-")


def test_resolve_project_name_hash_is_six_hex_chars():
    name = resolve_project_name(Path("Z:/Dossiers/ACME"))
    _, suffix = name.rsplit("-", 1)
    assert len(suffix) == 6
    assert all(c in "0123456789abcdef" for c in suffix)


def test_resolve_project_name_differs_across_folders():
    a = resolve_project_name(Path("Z:/Dossiers/ACME"))
    b = resolve_project_name(Path("Z:/Dossiers/BETA"))
    assert a != b


def test_resolve_project_name_sanitizes_unicode_and_spaces():
    # "Société ALPHA" → strip accents, replace spaces with '-', lowercase
    name = resolve_project_name(Path("Z:/Dossiers/Société ALPHA"))
    prefix, _ = name.rsplit("-", 1)
    assert prefix == "societe-alpha"


def test_resolve_project_name_caps_prefix_at_32_chars():
    long = Path("Z:/Dossiers/" + "A" * 100)
    prefix, _ = resolve_project_name(long).rsplit("-", 1)
    assert len(prefix) <= 32


def test_resolve_project_name_requires_absolute_path():
    with pytest.raises(ValueError, match="absolute"):
        resolve_project_name(Path("relative/path"))
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
uv run --with ".[dev]" pytest tests/test_project_resolver.py -v
```
Expected: `ModuleNotFoundError: _hacienda_hooks`.

- [ ] **Step 3: Write `hooks/_hacienda_hooks/__init__.py`**

```python
"""Internal helpers shared by hacienda hook scripts. Not a public API."""
```

- [ ] **Step 4: Write `hooks/_hacienda_hooks/project_resolver.py`**

```python
"""Map a Cowork-active folder path to a deterministic piighost project name."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path

_PREFIX_MAX = 32
_HASH_LEN = 6


def resolve_project_name(folder: Path) -> str:
    """Return a stable short name of the form ``<slug>-<hex6>``.

    - ``slug`` is the folder basename: Unicode-normalised, stripped of accents,
      non-alphanumerics replaced by ``-``, lower-cased, capped at 32 chars.
    - ``hex6`` is the first 6 chars of ``sha256(absolute_path)``.

    Deterministic per absolute path; differs across folders even if basenames
    collide.
    """
    if not folder.is_absolute():
        raise ValueError(f"folder must be an absolute path, got {folder!r}")

    basename = folder.name or "folder"
    normalised = unicodedata.normalize("NFKD", basename)
    ascii_only = normalised.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_only).strip("-").lower() or "folder"
    slug = slug[:_PREFIX_MAX]

    digest = hashlib.sha256(str(folder).encode("utf-8")).hexdigest()[:_HASH_LEN]
    return f"{slug}-{digest}"
```

- [ ] **Step 5: Run test — expect PASS**

```bash
uv run --with ".[dev]" pytest tests/test_project_resolver.py -v
```
Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add hooks/_hacienda_hooks/__init__.py hooks/_hacienda_hooks/project_resolver.py tests/test_project_resolver.py
git commit -m "feat(hooks): deterministic folder→project resolver"
```

---

## Task 4: piighost CLI shim

**Files:**
- Create: `hooks/_hacienda_hooks/piighost_cli.py`
- Create: `tests/test_piighost_cli.py`

Design: thin wrapper around `uv run --project <vendor> piighost ...` subprocess calls for `anonymize` and `rehydrate`. Hooks never call MCP directly — they shell out to the CLI that piighost already exposes.

- [ ] **Step 1: Write the failing test**

`tests/test_piighost_cli.py`:
```python
import json
from pathlib import Path

import pytest

from _hacienda_hooks.piighost_cli import PiighostCLI


@pytest.fixture
def cli(tmp_path):
    return PiighostCLI(vendor_dir=tmp_path / "vendor" / "piighost")


def test_anonymize_invokes_correct_subprocess(cli, mocker, tmp_path):
    mock_run = mocker.patch("_hacienda_hooks.piighost_cli.subprocess.run")
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = json.dumps(
        {"text": "Hello «PER_001»", "placeholders": {"«PER_001»": "_handle_abc_"}}
    )
    mock_run.return_value.stderr = ""

    result = cli.anonymize("Hello Jean", project="acme-abc123")

    assert result.text == "Hello «PER_001»"
    assert result.placeholders == {"«PER_001»": "_handle_abc_"}

    args = mock_run.call_args[0][0]
    assert args[0] == "uv"
    assert "run" in args
    assert "--project" in args
    assert str(cli.vendor_dir) in args
    assert "piighost" in args
    assert "anonymize" in args
    assert "--project" in args
    assert "acme-abc123" in args
    assert "--json" in args


def test_anonymize_sends_text_on_stdin(cli, mocker):
    mock_run = mocker.patch("_hacienda_hooks.piighost_cli.subprocess.run")
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = json.dumps({"text": "x", "placeholders": {}})
    mock_run.return_value.stderr = ""

    cli.anonymize("Hello Jean", project="acme-abc123")

    assert mock_run.call_args.kwargs["input"] == "Hello Jean"


def test_anonymize_raises_on_nonzero_exit(cli, mocker):
    mock_run = mocker.patch("_hacienda_hooks.piighost_cli.subprocess.run")
    mock_run.return_value.returncode = 2
    mock_run.return_value.stdout = ""
    mock_run.return_value.stderr = "vault key not found"

    with pytest.raises(RuntimeError, match="vault key not found"):
        cli.anonymize("Hello", project="acme-abc123")


def test_rehydrate_round_trips(cli, mocker):
    mock_run = mocker.patch("_hacienda_hooks.piighost_cli.subprocess.run")
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = "Hello Jean"
    mock_run.return_value.stderr = ""

    text = cli.rehydrate("Hello «PER_001»", project="acme-abc123")

    assert text == "Hello Jean"
    args = mock_run.call_args[0][0]
    assert "rehydrate" in args
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
uv run --with ".[dev]" pytest tests/test_piighost_cli.py -v
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write `hooks/_hacienda_hooks/piighost_cli.py`**

```python
"""Thin subprocess shim around the vendored piighost CLI.

Hooks call this instead of speaking MCP directly — keeps the
'no new server code' invariant and avoids spinning up a second MCP
session per hook invocation.
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AnonymizeResult:
    text: str
    placeholders: dict[str, str]


class PiighostCLI:
    def __init__(self, vendor_dir: Path | None = None):
        if vendor_dir is None:
            plugin_dir = os.environ.get("CLAUDE_PLUGIN_ROOT")
            if not plugin_dir:
                raise RuntimeError("CLAUDE_PLUGIN_ROOT not set")
            vendor_dir = Path(plugin_dir) / "vendor" / "piighost"
        self.vendor_dir = Path(vendor_dir)

    def _base_argv(self) -> list[str]:
        return ["uv", "run", "--project", str(self.vendor_dir), "piighost"]

    def anonymize(self, text: str, *, project: str) -> AnonymizeResult:
        argv = self._base_argv() + ["anonymize", "--project", project, "--json", "--stdin"]
        proc = subprocess.run(argv, input=text, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or "piighost anonymize failed")
        data = json.loads(proc.stdout)
        return AnonymizeResult(text=data["text"], placeholders=data.get("placeholders", {}))

    def rehydrate(self, text: str, *, project: str) -> str:
        argv = self._base_argv() + ["rehydrate", "--project", project, "--stdin"]
        proc = subprocess.run(argv, input=text, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or "piighost rehydrate failed")
        return proc.stdout
```

- [ ] **Step 4: Run test — expect PASS**

```bash
uv run --with ".[dev]" pytest tests/test_piighost_cli.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add hooks/_hacienda_hooks/piighost_cli.py tests/test_piighost_cli.py
git commit -m "feat(hooks): piighost CLI subprocess shim"
```

---

## Task 5: Audit log

**Files:**
- Create: `hooks/_hacienda_hooks/audit_log.py`
- Create: `tests/test_audit_log.py`

- [ ] **Step 1: Write the failing test**

`tests/test_audit_log.py`:
```python
import json
from pathlib import Path

from _hacienda_hooks.audit_log import AuditLog


def test_audit_log_appends_jsonl(tmp_path):
    log_path = tmp_path / "session.audit.jsonl"
    log = AuditLog(log_path)

    log.record(event="redact", tool="Write", project="acme-abc", placeholders={"«PER_001»": "Jean"})
    log.record(event="rehydrate", tool="mcp__hacienda__hybrid_search", project="acme-abc", placeholders={})

    lines = log_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    entry0 = json.loads(lines[0])
    assert entry0["event"] == "redact"
    assert entry0["tool"] == "Write"
    assert entry0["project"] == "acme-abc"
    assert entry0["placeholders"] == {"«PER_001»": "Jean"}
    assert "ts" in entry0


def test_audit_log_creates_parent_directories(tmp_path):
    log_path = tmp_path / "deep" / "nested" / "session.audit.jsonl"
    log = AuditLog(log_path)
    log.record(event="redact", tool="Write", project="p", placeholders={})
    assert log_path.is_file()


def test_audit_log_timestamp_is_iso8601(tmp_path):
    log_path = tmp_path / "s.jsonl"
    log = AuditLog(log_path)
    log.record(event="redact", tool="Write", project="p", placeholders={})
    entry = json.loads(log_path.read_text(encoding="utf-8").strip())
    # Will raise ValueError if not ISO-8601
    from datetime import datetime
    datetime.fromisoformat(entry["ts"].rstrip("Z"))
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
uv run --with ".[dev]" pytest tests/test_audit_log.py -v
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write `hooks/_hacienda_hooks/audit_log.py`**

```python
"""Append-only JSONL session audit log.

One file per Claude Desktop session, stored under ``~/.hacienda/sessions/``.
Every redact/rehydrate event is recorded so ``/hacienda:audit`` can
surface a full transparency report.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class AuditLog:
    path: Path

    def record(self, *, event: str, tool: str, project: str, placeholders: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "tool": tool,
            "project": project,
            "placeholders": placeholders,
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
```

- [ ] **Step 4: Run test — expect PASS**

```bash
uv run --with ".[dev]" pytest tests/test_audit_log.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add hooks/_hacienda_hooks/audit_log.py tests/test_audit_log.py
git commit -m "feat(hooks): append-only session audit log"
```

---

## Task 6: Redaction hook (`hooks/redact.py`)

**Files:**
- Create: `hooks/redact.py`
- Create: `tests/test_redact_hook.py`

Contract (Claude Desktop hook protocol):
- stdin: `{"session_id": "...", "tool_name": "...", "tool_input": {...}}`
- stdout: `{"decision": "modify", "tool_input": {...}}` OR `{}` (pass-through)

- [ ] **Step 1: Write the failing test**

`tests/test_redact_hook.py`:
```python
import json
import subprocess
import sys
from pathlib import Path

import pytest


HOOK = Path(__file__).parent.parent / "hooks" / "redact.py"


def run_hook(payload: dict, env: dict) -> dict:
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout) if proc.stdout.strip() else {}


@pytest.fixture
def env(tmp_path, monkeypatch):
    return {
        "HACIENDA_ACTIVE_FOLDER": str(tmp_path / "Dossiers" / "ACME"),
        "HACIENDA_DATA_DIR": str(tmp_path / ".hacienda"),
        "CLAUDE_PLUGIN_ROOT": str(Path(__file__).parent.parent),
        "PATH": "/usr/bin:/bin",
    }


def test_redact_hook_modifies_text_fields(env, mocker):
    mocker.patch(
        "_hacienda_hooks.piighost_cli.PiighostCLI.anonymize",
        return_value=type("R", (), {"text": "Hello «PER_001»", "placeholders": {"«PER_001»": "h"}})(),
    )

    payload = {
        "session_id": "sess_abc",
        "tool_name": "Write",
        "tool_input": {"file_path": "/tmp/x", "content": "Hello Jean"},
    }
    result = run_hook(payload, env)

    assert result["decision"] == "modify"
    assert result["tool_input"]["content"] == "Hello «PER_001»"
    # Non-text fields are untouched
    assert result["tool_input"]["file_path"] == "/tmp/x"


def test_redact_hook_passes_through_when_no_pii(env, mocker):
    mocker.patch(
        "_hacienda_hooks.piighost_cli.PiighostCLI.anonymize",
        return_value=type("R", (), {"text": "Hello", "placeholders": {}})(),
    )
    payload = {
        "session_id": "sess_abc",
        "tool_name": "Write",
        "tool_input": {"file_path": "/tmp/x", "content": "Hello"},
    }
    result = run_hook(payload, env)
    assert result == {} or result.get("decision") != "modify"


def test_redact_hook_refuses_without_active_folder(env, mocker):
    del env["HACIENDA_ACTIVE_FOLDER"]
    payload = {"session_id": "s", "tool_name": "Write", "tool_input": {"content": "Hello Jean"}}
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    # No active folder → safe default: block outbound with clear reason
    assert proc.returncode == 0
    result = json.loads(proc.stdout)
    assert result["decision"] == "block"
    assert "active folder" in result["reason"].lower()


def test_redact_hook_size_cap_blocks_huge_payloads(env, mocker):
    mocker.patch("_hacienda_hooks.piighost_cli.PiighostCLI.anonymize")
    huge = "x" * (5 * 1024 * 1024 + 1)
    payload = {"session_id": "s", "tool_name": "Write", "tool_input": {"content": huge}}
    result = run_hook(payload, env)
    assert result["decision"] == "block"
    assert "5mb" in result["reason"].lower() or "size" in result["reason"].lower()


def test_redact_hook_writes_audit_entry(env, mocker, tmp_path):
    mocker.patch(
        "_hacienda_hooks.piighost_cli.PiighostCLI.anonymize",
        return_value=type("R", (), {"text": "Hi «PER_001»", "placeholders": {"«PER_001»": "h"}})(),
    )
    payload = {
        "session_id": "sess_xyz",
        "tool_name": "Write",
        "tool_input": {"content": "Hi Jean"},
    }
    run_hook(payload, env)

    audit = Path(env["HACIENDA_DATA_DIR"]) / "sessions" / "sess_xyz.audit.jsonl"
    assert audit.is_file()
    entry = json.loads(audit.read_text(encoding="utf-8").strip())
    assert entry["event"] == "redact"
    assert entry["placeholders"] == {"«PER_001»": "h"}
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
uv run --with ".[dev]" pytest tests/test_redact_hook.py -v
```
Expected: `FileNotFoundError` on `hooks/redact.py`.

- [ ] **Step 3: Write `hooks/redact.py`**

```python
#!/usr/bin/env python3
"""PreToolUse hook: redact outbound PII before it leaves the laptop.

Protocol:
  stdin  : {"session_id": "...", "tool_name": "...", "tool_input": {...}}
  stdout : {"decision": "modify", "tool_input": {...}}
           or {"decision": "block", "reason": "..."}
           or {} (pass-through)

Invariants:
  - Never emit raw PII on stdout/stderr or into the audit log values.
  - If the active folder is unknown, BLOCK rather than leak. Fail-closed.
  - Cap per-call payload at 5MB — above that we block and ask the user
    to narrow the operation.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Make the sibling _hacienda_hooks package importable when invoked as a script.
sys.path.insert(0, str(Path(__file__).parent))

from _hacienda_hooks.audit_log import AuditLog
from _hacienda_hooks.piighost_cli import PiighostCLI
from _hacienda_hooks.project_resolver import resolve_project_name

MAX_PAYLOAD_BYTES = 5 * 1024 * 1024
TEXT_FIELDS = ("content", "new_string", "old_string", "text", "prompt", "query", "body", "message")


def _emit(obj: dict) -> None:
    json.dump(obj, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


def _block(reason: str) -> None:
    _emit({"decision": "block", "reason": reason})
    sys.exit(0)


def _payload_size(obj: object) -> int:
    return len(json.dumps(obj, ensure_ascii=False).encode("utf-8"))


def main() -> None:
    payload = json.load(sys.stdin)
    tool_input = payload.get("tool_input", {}) or {}
    session_id = payload.get("session_id", "unknown")
    tool_name = payload.get("tool_name", "unknown")

    if _payload_size(tool_input) > MAX_PAYLOAD_BYTES:
        _block("Payload exceeds 5MB hacienda size cap; narrow the operation or split the input.")

    active = os.environ.get("HACIENDA_ACTIVE_FOLDER")
    if not active:
        _block(
            "hacienda cannot determine the active Cowork folder. "
            "Open a client folder before using outbound tools."
        )

    project = resolve_project_name(Path(active))
    cli = PiighostCLI()
    data_dir = Path(os.environ.get("HACIENDA_DATA_DIR", Path.home() / ".hacienda"))
    audit = AuditLog(data_dir / "sessions" / f"{session_id}.audit.jsonl")

    modified = dict(tool_input)
    any_change = False
    all_placeholders: dict[str, str] = {}

    for field in TEXT_FIELDS:
        val = modified.get(field)
        if not isinstance(val, str) or not val:
            continue
        result = cli.anonymize(val, project=project)
        if result.text != val:
            modified[field] = result.text
            any_change = True
            all_placeholders.update(result.placeholders)

    if not any_change:
        _emit({})
        return

    audit.record(event="redact", tool=tool_name, project=project, placeholders=all_placeholders)
    _emit({"decision": "modify", "tool_input": modified})


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test — expect PASS**

```bash
uv run --with ".[dev]" pytest tests/test_redact_hook.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add hooks/redact.py tests/test_redact_hook.py
git commit -m "feat(hooks): PreToolUse redaction hook with fail-closed policy"
```

---

## Task 7: Rehydration hook (`hooks/rehydrate.py`)

**Files:**
- Create: `hooks/rehydrate.py`
- Create: `tests/test_rehydrate_hook.py`

Contract: PostToolUse receives `{"tool_name", "tool_response", "session_id"}`. Rehydrates placeholders in retrieval results **only for display**, not for model context. In v1 this means: write a rehydrated copy to `~/.hacienda/sessions/<id>.display.jsonl` that `/hacienda:audit` can surface. Model context stays redacted.

- [ ] **Step 1: Write the failing test**

`tests/test_rehydrate_hook.py`:
```python
import json
import subprocess
import sys
from pathlib import Path

import pytest


HOOK = Path(__file__).parent.parent / "hooks" / "rehydrate.py"


def run_hook(payload: dict, env: dict) -> dict:
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout) if proc.stdout.strip() else {}


@pytest.fixture
def env(tmp_path):
    return {
        "HACIENDA_ACTIVE_FOLDER": str(tmp_path / "Dossiers" / "ACME"),
        "HACIENDA_DATA_DIR": str(tmp_path / ".hacienda"),
        "CLAUDE_PLUGIN_ROOT": str(Path(__file__).parent.parent),
        "PATH": "/usr/bin:/bin",
    }


def test_rehydrate_is_pass_through_for_tool_response(env, mocker):
    mocker.patch(
        "_hacienda_hooks.piighost_cli.PiighostCLI.rehydrate",
        return_value="Hello Jean",
    )
    payload = {
        "session_id": "s",
        "tool_name": "mcp__hacienda__hybrid_search",
        "tool_response": {"results": [{"text": "Hello «PER_001»"}]},
    }
    result = run_hook(payload, env)
    # Model context is NOT modified — only the display sidecar is written.
    assert result == {}


def test_rehydrate_writes_display_sidecar(env, mocker):
    mocker.patch(
        "_hacienda_hooks.piighost_cli.PiighostCLI.rehydrate",
        return_value="Hello Jean",
    )
    payload = {
        "session_id": "sess_rehyd",
        "tool_name": "mcp__hacienda__hybrid_search",
        "tool_response": {"results": [{"text": "Hello «PER_001»"}]},
    }
    run_hook(payload, env)
    display = Path(env["HACIENDA_DATA_DIR"]) / "sessions" / "sess_rehyd.display.jsonl"
    assert display.is_file()
    entry = json.loads(display.read_text(encoding="utf-8").strip())
    assert entry["tool"] == "mcp__hacienda__hybrid_search"
    assert entry["rehydrated"] == "Hello Jean"


def test_rehydrate_no_active_folder_is_noop(env, mocker):
    del env["HACIENDA_ACTIVE_FOLDER"]
    mocker.patch("_hacienda_hooks.piighost_cli.PiighostCLI.rehydrate")
    payload = {
        "session_id": "s",
        "tool_name": "mcp__hacienda__hybrid_search",
        "tool_response": {"results": []},
    }
    # Should succeed (exit 0, no decision) — post-hook must not crash on missing folder
    result = run_hook(payload, env)
    assert result == {}
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
uv run --with ".[dev]" pytest tests/test_rehydrate_hook.py -v
```
Expected: `FileNotFoundError` on `rehydrate.py`.

- [ ] **Step 3: Write `hooks/rehydrate.py`**

```python
#!/usr/bin/env python3
"""PostToolUse hook: rehydrate retrieval results for local display.

Writes a display-side JSONL sidecar — does NOT modify the tool_response
seen by the model. Model context stays redacted. Only /hacienda:audit
surfaces the real values.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _hacienda_hooks.piighost_cli import PiighostCLI
from _hacienda_hooks.project_resolver import resolve_project_name


def main() -> None:
    payload = json.load(sys.stdin)
    tool_response = payload.get("tool_response") or {}
    session_id = payload.get("session_id", "unknown")
    tool_name = payload.get("tool_name", "unknown")

    active = os.environ.get("HACIENDA_ACTIVE_FOLDER")
    if not active:
        return  # no-op, post-hook must not crash

    project = resolve_project_name(Path(active))
    cli = PiighostCLI()
    data_dir = Path(os.environ.get("HACIENDA_DATA_DIR", Path.home() / ".hacienda"))
    sidecar = data_dir / "sessions" / f"{session_id}.display.jsonl"
    sidecar.parent.mkdir(parents=True, exist_ok=True)

    blob = json.dumps(tool_response, ensure_ascii=False)
    try:
        rehydrated = cli.rehydrate(blob, project=project)
    except RuntimeError:
        return  # rehydration failure is never fatal — the redacted view still works

    entry = {"tool": tool_name, "rehydrated": rehydrated}
    with sidecar.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test — expect PASS**

```bash
uv run --with ".[dev]" pytest tests/test_rehydrate_hook.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add hooks/rehydrate.py tests/test_rehydrate_hook.py
git commit -m "feat(hooks): PostToolUse rehydration sidecar"
```

---

## Task 8: hooks.json wiring

**Files:**
- Create: `hooks/hooks.json`
- Create: `tests/test_hooks_json_schema.py`

- [ ] **Step 1: Write the failing test**

`tests/test_hooks_json_schema.py`:
```python
import json
from pathlib import Path

import jsonschema

HOOKS = Path(__file__).parent.parent / "hooks" / "hooks.json"

SCHEMA = {
    "type": "object",
    "required": ["hooks"],
    "properties": {
        "hooks": {
            "type": "object",
            "properties": {
                "PreToolUse": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["matcher", "hooks"],
                        "properties": {
                            "matcher": {"type": "string"},
                            "hooks": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "required": ["type", "command"],
                                    "properties": {
                                        "type": {"const": "command"},
                                        "command": {"type": "string"},
                                    },
                                },
                            },
                        },
                    },
                },
                "PostToolUse": {"type": "array"},
            },
        }
    },
}


def test_hooks_json_schema_valid():
    data = json.loads(HOOKS.read_text(encoding="utf-8"))
    jsonschema.validate(data, SCHEMA)


def test_pretooluse_covers_outbound_tools():
    data = json.loads(HOOKS.read_text(encoding="utf-8"))
    matcher = data["hooks"]["PreToolUse"][0]["matcher"]
    for required in ["Write", "Edit", "WebFetch", "WebSearch", "slack", "gmail", "drive"]:
        assert required in matcher, f"PreToolUse matcher missing {required!r}"


def test_posttooluse_covers_retrieval_tools():
    data = json.loads(HOOKS.read_text(encoding="utf-8"))
    matcher = data["hooks"]["PostToolUse"][0]["matcher"]
    assert "mcp__hacienda__hybrid_search" in matcher
    assert "mcp__hacienda__vault_get" in matcher


def test_commands_reference_plugin_dir_variable():
    raw = HOOKS.read_text(encoding="utf-8")
    assert "${CLAUDE_PLUGIN_ROOT}/hooks/redact.py" in raw
    assert "${CLAUDE_PLUGIN_ROOT}/hooks/rehydrate.py" in raw
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
uv run --with ".[dev]" pytest tests/test_hooks_json_schema.py -v
```
Expected: `FileNotFoundError`.

- [ ] **Step 3: Write `hooks/hooks.json`**

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit|MultiEdit|WebFetch|WebSearch|.*slack.*|.*gmail.*|.*email.*|.*docusign.*|.*drive.*",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/redact.py"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "mcp__hacienda__hybrid_search|mcp__hacienda__vault_get",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/rehydrate.py"
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 4: Run test — expect PASS**

```bash
uv run --with ".[dev]" pytest tests/test_hooks_json_schema.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add hooks/hooks.json tests/test_hooks_json_schema.py
git commit -m "feat(hooks): hooks.json wiring (PreToolUse outbound, PostToolUse retrieval)"
```

---

## Task 9: Knowledge-base skill

**Files:**
- Create: `skills/knowledge-base/SKILL.md`
- Create: `tests/test_skill_frontmatter.py`

- [ ] **Step 1: Write the failing test**

`tests/test_skill_frontmatter.py`:
```python
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent

SKILLS = [
    ROOT / "skills" / "knowledge-base" / "SKILL.md",
    ROOT / "skills" / "redact-outbound" / "SKILL.md",
]

# Cowork skill contract: only `name` and `description` allowed. Anything else
# (`allowed-tools`, `tools`, shebangs, exec bits) is a plugin validation error.
SKILL_FRONTMATTER_ALLOWED_KEYS = {"name", "description"}


def _parse_frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path} missing YAML frontmatter"
    _, fm, _ = text.split("---\n", 2)
    return yaml.safe_load(fm)


def test_all_skills_have_name_and_description():
    for path in SKILLS:
        if not path.is_file():
            continue
        fm = _parse_frontmatter(path)
        assert "name" in fm, f"{path} missing name"
        assert "description" in fm, f"{path} missing description"
        assert len(fm["description"]) >= 40


def test_skill_frontmatter_has_no_forbidden_keys():
    """Skills are passive markdown — no allowed-tools, tools, or other fields."""
    for path in SKILLS:
        if not path.is_file():
            continue
        fm = _parse_frontmatter(path)
        forbidden = set(fm.keys()) - SKILL_FRONTMATTER_ALLOWED_KEYS
        assert not forbidden, (
            f"{path}: forbidden frontmatter keys {forbidden} "
            f"(skills accept only {SKILL_FRONTMATTER_ALLOWED_KEYS})"
        )


def test_knowledge_base_body_mentions_citations_and_status_resource():
    path = ROOT / "skills" / "knowledge-base" / "SKILL.md"
    body = path.read_text(encoding="utf-8").split("---\n", 2)[2]
    assert "cite" in body.lower() or "citation" in body.lower()
    assert "hacienda://kb/status" in body


def test_knowledge_base_body_references_required_mcp_tools():
    """Tool *names* appear in the prose (guidance), not in frontmatter (forbidden)."""
    path = ROOT / "skills" / "knowledge-base" / "SKILL.md"
    body = path.read_text(encoding="utf-8").split("---\n", 2)[2]
    for tool in ("mcp__hacienda__hybrid_search", "mcp__hacienda__index_path"):
        assert tool in body, f"knowledge-base skill body must reference {tool}"
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
uv run --with ".[dev]" pytest tests/test_skill_frontmatter.py -v
```
Expected: 3 tests fail or skip (files missing).

- [ ] **Step 3: Write `skills/knowledge-base/SKILL.md`**

```markdown
---
name: knowledge-base
description: >
  Search and answer questions from the user's current client folder using
  hybrid BM25 + semantic vector retrieval. Use whenever the user asks about
  documents, emails, contracts, notes, or any content in the folder Cowork
  is currently pointed at. Always cite sources with file paths and excerpts.
---

# Knowledge-base over the active Cowork folder

You have access to a local, PII-safe RAG pipeline over the folder the user
currently has open in Cowork. Follow this procedure for every question that
concerns the folder's contents.

## 1. Check index status first

Before any search, read the MCP resource `hacienda://kb/status` using
`ReadMcpResourceTool`. Three outcomes:

- **`state: "ready"`** — proceed to step 2.
- **`state: "indexing"`** — tell the user the index is still building
  (`progress.done / progress.total` files done), then still proceed to step 2.
  The partial index is searchable.
- **`state: "unknown"` or missing** — call `mcp__hacienda__index_path` with
  the folder path, tell the user indexing has started, then proceed to step 2
  once at least a few files are indexed.

## 2. Search

Always use `mcp__hacienda__hybrid_search` with:
- `query`: the user's question, rephrased if needed for retrieval
- `top_k`: 10
- `rerank`: true
- `project`: the project name reported by `hacienda://kb/status`

Do not use any other search tool. Do not try to read files directly with
`Read` unless the user explicitly asks you to inspect a specific file by
path — reads bypass the redaction layer and leak PII into context.

## 3. Cite every claim

Every factual claim in your answer must carry a citation of the form:

- `[path/to/file.pdf p.12]` for paginated documents
- `[path/to/file.eml]` for emails
- `[path/to/file.txt:42-58]` for line-ranged text

Quote excerpts verbatim — do not paraphrase inside quotation marks.

If `hybrid_search` returns no results for the question, say so plainly.
Do not fabricate citations.

## 4. Cross-client safety

You see exactly one folder at a time: the one Cowork is pointed at now.
If the user asks about a client whose folder is not open, refuse and
suggest they switch folders in Cowork. Never search across folders.

## 5. Placeholders in results

Search results will contain placeholder tokens like `«PER_001»`,
`«ORG_014»`, `«IBAN_003»`. These represent redacted PII — the real values
stay on the user's laptop. Preserve placeholders verbatim in quotes. When
drafting non-quoted prose, you may refer to entities by their placeholder
(e.g., "the counterparty «ORG_014»") or ask the user for clarification.
Do not invent real names for placeholders.
```

- [ ] **Step 4: Run test — expect PASS**

```bash
uv run --with ".[dev]" pytest tests/test_skill_frontmatter.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/knowledge-base/SKILL.md tests/test_skill_frontmatter.py
git commit -m "feat(skills): knowledge-base skill with hybrid search + citations"
```

---

## Task 10: Redact-outbound skill

**Files:**
- Create: `skills/redact-outbound/SKILL.md`

- [ ] **Step 1: Add a test assertion to `tests/test_skill_frontmatter.py`**

Append to that file:
```python
def test_redact_outbound_body_explains_placeholders():
    path = ROOT / "skills" / "redact-outbound" / "SKILL.md"
    body = path.read_text(encoding="utf-8").split("---\n", 2)[2]
    assert "«PER_" in body
    assert "placeholder" in body.lower()
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
uv run --with ".[dev]" pytest tests/test_skill_frontmatter.py::test_redact_outbound_body_explains_placeholders -v
```
Expected: FileNotFoundError.

- [ ] **Step 3: Write `skills/redact-outbound/SKILL.md`**

```markdown
---
name: redact-outbound
description: >
  Understand how hacienda's redacted-transit placeholders work so you can
  draft emails, documents, and messages that refer to real-world entities
  without leaking their real names to the cloud. Invoked automatically
  when you see tokens of the form «TYPE_NNN» in your context.
---

# Redacted-transit placeholders

The user's client data is subject to professional secrecy. Before anything
leaves the laptop, hacienda replaces identifiable values with placeholder
tokens. You see only the placeholders. The user sees the real values.

## Placeholder vocabulary

- `«PER_NNN»` — a person's name (e.g., `«PER_001»` = "Jean Martin" locally)
- `«ORG_NNN»` — an organisation, company, or institution
- `«LOC_NNN»` — a location, address, or city
- `«IBAN_NNN»` — a bank account number
- `«PHONE_NNN»` — a phone number
- `«EMAIL_NNN»` — an email address
- `«DATE_NNN»` — a specific date (only when sensitive per context)
- `«ID_NNN»` — any identifier (SIRET, national ID, case number, …)

## Rules for drafting

1. **In quotes: verbatim.** If you quote a source text, preserve placeholders
   exactly — never substitute back real values you guessed.

2. **In prose: placeholders are usable.** You may write
   *"per «ORG_014»'s response of «DATE_002», the delivery is scheduled for
   «DATE_007»"*. The user's laptop will rehydrate these on display.

3. **Consistency matters.** The same `«PER_001»` refers to the same real
   person across the whole session. Do not conflate different placeholders.

4. **Never invent mappings.** You cannot know which real name sits behind
   `«PER_001»`. If the user asks "who is «PER_001»?", tell them to check
   their local audit view (`/hacienda:audit`) — you do not have that answer.

5. **If placeholders seem wrong, say so.** If a placeholder's context
   suggests it should be e.g. an IBAN but it's typed `«PER_…»`, flag the
   inconsistency rather than pressing on.
```

- [ ] **Step 4: Run test — expect PASS**

```bash
uv run --with ".[dev]" pytest tests/test_skill_frontmatter.py -v
```
Expected: all tests passed.

- [ ] **Step 5: Commit**

```bash
git add skills/redact-outbound/SKILL.md tests/test_skill_frontmatter.py
git commit -m "feat(skills): redact-outbound placeholder explainer"
```

---

## Task 11: Slash commands (v1 core)

**Files:**
- Create: `commands/index.md`
- Create: `commands/kb-status.md`
- Create: `commands/audit.md`

- [ ] **Step 1: Add a schema test for commands**

Append to `tests/test_skill_frontmatter.py`:
```python
COMMANDS = [
    ROOT / "commands" / "index.md",
    ROOT / "commands" / "kb-status.md",
    ROOT / "commands" / "audit.md",
]


def test_all_commands_have_description():
    for path in COMMANDS:
        if not path.is_file():
            continue
        fm = _parse_frontmatter(path)
        assert "description" in fm
        assert len(fm["description"]) >= 20


def test_all_v1_commands_exist():
    missing = [p.name for p in COMMANDS if not p.is_file()]
    assert not missing, f"missing command files: {missing}"
```

- [ ] **Step 2: Run tests — expect FAIL** (`missing command files: ['index.md', …]`)

```bash
uv run --with ".[dev]" pytest tests/test_skill_frontmatter.py::test_all_v1_commands_exist -v
```

- [ ] **Step 3: Write `commands/index.md`**

```markdown
---
description: Force (re)index the folder currently open in Cowork
allowed-tools:
  - mcp__hacienda__index_path
  - ReadMcpResourceTool
---

Resolve the active Cowork folder path from the current session context.
Call `mcp__hacienda__index_path` with `path=<active folder>`,
`force_reindex=true`, and `recursive=true`.

Then poll `hacienda://kb/status` every few seconds until `state == "ready"`
(or `"error"`), showing the user the `progress.done / progress.total`
counter as it updates.

On completion, report:
- Total documents indexed
- Any files that failed (with the error message, not the file contents)
- Time elapsed

On error, surface the `errors[]` array from the status resource. Do not
retry automatically — ask the user whether to retry the failed files.
```

- [ ] **Step 4: Write `commands/kb-status.md`**

```markdown
---
description: Show the hacienda knowledge-base state for the active folder
allowed-tools:
  - ReadMcpResourceTool
---

Read `hacienda://kb/status` and render it as a short, human-readable
summary:

- Folder path
- Project name (e.g., `acme-a1b2c3`)
- State (`ready` / `indexing` / `error`)
- Progress (if indexing): `done / total` files
- Last update timestamp
- Any errors

If `state == "error"`, also tell the user they can retry with
`/hacienda:index`.
```

- [ ] **Step 5: Write `commands/audit.md`**

```markdown
---
description: Show this session's PII redaction and rehydration audit trail
---

Read the current session's audit file at
`${HACIENDA_DATA_DIR:-$HOME/.hacienda}/sessions/<session_id>.audit.jsonl`
and the display sidecar at the same path with `.display.jsonl` suffix.

Render a summary table with:
- Timestamp
- Event (`redact` or `rehydrate`)
- Tool name
- Count of placeholders generated/resolved

Then for each `redact` entry, show the placeholders with their local
rehydrated values (these never left the laptop — the audit file references
vault handles, and you rehydrate by calling `mcp__hacienda__vault_get` on
each handle).

Warn the user that this output contains real PII and should not be
copy-pasted outside this Cowork session.
```

- [ ] **Step 6: Run tests — expect PASS**

```bash
uv run --with ".[dev]" pytest tests/test_skill_frontmatter.py -v
```
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add commands/index.md commands/kb-status.md commands/audit.md tests/test_skill_frontmatter.py
git commit -m "feat(commands): v1 core — index, kb-status, audit"
```

---

## Task 12: Slash commands (stretch — brief, draft-reply)

**Files:**
- Create: `commands/brief.md`
- Create: `commands/draft-reply.md`

- [ ] **Step 1: Add stretch commands to schema test**

Append to `tests/test_skill_frontmatter.py`:
```python
STRETCH_COMMANDS = [
    ROOT / "commands" / "brief.md",
    ROOT / "commands" / "draft-reply.md",
]


def test_stretch_commands_have_description():
    for path in STRETCH_COMMANDS:
        if not path.is_file():
            continue
        fm = _parse_frontmatter(path)
        assert "description" in fm
```

- [ ] **Step 2: Write `commands/brief.md`**

```markdown
---
description: Produce a structured intake brief for the current client folder
allowed-tools:
  - mcp__hacienda__hybrid_search
  - ReadMcpResourceTool
---

Produce a one-page brief of the client folder currently open in Cowork.

Steps:
1. Read `hacienda://kb/status` to confirm the folder is indexed.
2. Run six `mcp__hacienda__hybrid_search` calls, top_k=5 each, with queries:
   - "parties and roles"
   - "contracts and agreements"
   - "pending deadlines and obligations"
   - "financial amounts and payment terms"
   - "recent correspondence"
   - "open issues or disputes"
3. Assemble a brief in this structure:
   ## Parties
   ## Key documents
   ## Timeline and obligations
   ## Financials
   ## Recent activity
   ## Open items

Every bullet cites its source with `[path p.N]`. Placeholders stay as-is;
do not try to rehydrate in the brief text itself.
```

- [ ] **Step 3: Write `commands/draft-reply.md`**

```markdown
---
description: Draft a reply to the last email in the current folder using surrounding context
allowed-tools:
  - mcp__hacienda__hybrid_search
---

Identify the most recent email in the client folder:

1. Run `mcp__hacienda__hybrid_search` with `query="latest email"`,
   `top_k=3`, `file_type="eml"`.
2. Pick the top hit; ask the user to confirm it's the right one before
   drafting. Show: sender placeholder, subject, date.

Once confirmed:
3. Run a second `hybrid_search` with the email's subject and key terms
   as the query to pull in context (prior threads, referenced documents).
4. Draft a reply in the same language as the original email. Address the
   recipient by their placeholder (`«PER_…»`); the user's laptop will
   rehydrate on display.
5. Preserve formal register and professional tone. No US legal references.
6. End with the user's signature placeholder (`«SIGNATURE»`) — the user
   will replace that manually before sending.

Present the draft in a ```text block so the user can copy-paste.
```

- [ ] **Step 4: Run test — expect PASS**

```bash
uv run --with ".[dev]" pytest tests/test_skill_frontmatter.py -v
```

- [ ] **Step 5: Commit**

```bash
git add commands/brief.md commands/draft-reply.md tests/test_skill_frontmatter.py
git commit -m "feat(commands): stretch — brief, draft-reply"
```

---

## Task 13: Redaction subagent

**Files:**
- Create: `agents/redaction-agent.md`

- [ ] **Step 1: Write the file**

```markdown
---
name: redaction-agent
description: Specialist subagent for auditing large redaction jobs or investigating suspected leaks. Invoke when the user reports a suspected PII leak, when an outbound payload was blocked at the 5MB cap, or when the user wants an end-to-end walk-through of what left the laptop in a session.
tools:
  - Read
  - Glob
  - Grep
  - Bash
  - mcp__hacienda__vault_search
  - mcp__hacienda__vault_get
  - mcp__hacienda__vault_stats
---

You are the hacienda redaction auditor. Your job is to answer three
questions on demand:

1. **What placeholders were generated in this session?** Read the session
   audit log at `${HACIENDA_DATA_DIR:-$HOME/.hacienda}/sessions/<id>.audit.jsonl`
   and aggregate placeholders by type.

2. **What real values sit behind them?** Call `mcp__hacienda__vault_get`
   on each placeholder handle. Present the result in a table the user can
   review locally. Warn the user that the table contains raw PII.

3. **Did anything slip through?** Scan outbound tool calls in the audit
   log for text fields that still contain obvious patterns the regex
   engine should have caught (IBANs: `[A-Z]{2}\d{2}[A-Z0-9]{10,30}`,
   French phone: `0\d{9}` or `\+33\d{9}`, email: `\S+@\S+\.\S+`). Report
   any hits as suspected leaks and recommend the user rotate their vault
   key.

Never output real values unless the user explicitly asks for the vault
dump (question 2). Default to placeholders.
```

- [ ] **Step 2: Add schema test**

Append to `tests/test_skill_frontmatter.py`:
```python
def test_agent_frontmatter_valid():
    """Cowork agent frontmatter — name, description, tools (allowlist).

    Cowork agents declare their tools with a `tools:` list (per the
    Cowork plugin contract the product team confirmed). Not to be
    confused with the Claude Code agent schema which uses
    `disallowedTools` — Cowork ≠ Claude Code.
    """
    path = ROOT / "agents" / "redaction-agent.md"
    fm = _parse_frontmatter(path)
    assert fm.get("name") == "redaction-agent"
    assert "description" in fm and len(fm["description"]) >= 40
    assert "tools" in fm, "Cowork agents declare a tools allowlist"
    # Core vault-read tools the auditor needs
    assert "mcp__hacienda__vault_get" in fm["tools"]
    # Must NOT grant any outbound write/send capability — auditor is read-only
    for forbidden in ("Write", "Edit", "MultiEdit", "WebFetch", "WebSearch"):
        assert forbidden not in fm["tools"], (
            f"redaction-agent is read-only; {forbidden} must not be in tools"
        )
```

- [ ] **Step 3: Run test — expect PASS**

```bash
uv run --with ".[dev]" pytest tests/test_skill_frontmatter.py::test_agent_frontmatter_valid -v
```

- [ ] **Step 4: Commit**

```bash
git add agents/redaction-agent.md tests/test_skill_frontmatter.py
git commit -m "feat(agents): redaction-agent subagent for audits"
```

---

## Task 14: Bootstrap — data directory

**Files:**
- Create: `scripts/_hacienda_bootstrap/__init__.py`
- Create: `scripts/_hacienda_bootstrap/datadir.py`
- Create: `tests/test_bootstrap_datadir.py`

- [ ] **Step 1: Write the failing test**

`tests/test_bootstrap_datadir.py`:
```python
from pathlib import Path

from _hacienda_bootstrap.datadir import ensure_data_dir


def test_ensure_data_dir_creates_layout(tmp_path):
    root = tmp_path / ".hacienda"
    ensure_data_dir(root)

    assert root.is_dir()
    assert (root / "sessions").is_dir()
    assert (root / "projects").is_dir()
    assert (root / "logs").is_dir()


def test_ensure_data_dir_sets_restrictive_perms_on_posix(tmp_path):
    import os
    root = tmp_path / ".hacienda"
    ensure_data_dir(root)
    if os.name == "posix":
        mode = root.stat().st_mode & 0o777
        assert mode == 0o700, f"expected 0o700, got {oct(mode)}"


def test_ensure_data_dir_is_idempotent(tmp_path):
    root = tmp_path / ".hacienda"
    ensure_data_dir(root)
    ensure_data_dir(root)  # second call must not raise
    assert root.is_dir()
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
uv run --with ".[dev]" pytest tests/test_bootstrap_datadir.py -v
```

- [ ] **Step 3: Write `scripts/_hacienda_bootstrap/__init__.py`**

```python
"""First-run bootstrap helpers for the hacienda plugin."""
```

- [ ] **Step 4: Write `scripts/_hacienda_bootstrap/datadir.py`**

```python
"""Create the ~/.hacienda layout on first run."""
from __future__ import annotations

import os
from pathlib import Path


def ensure_data_dir(root: Path) -> None:
    """Create root/ and required subdirs; chmod 0o700 on POSIX.

    Idempotent — safe to call on every plugin activation.
    """
    for sub in ("", "sessions", "projects", "logs"):
        path = root / sub if sub else root
        path.mkdir(parents=True, exist_ok=True)

    if os.name == "posix":
        os.chmod(root, 0o700)
```

- [ ] **Step 5: Update `pyproject.toml` pythonpath**

Edit `pyproject.toml` section `[tool.pytest.ini_options]`:
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["hooks", "scripts"]
```
(Already present from Task 0 — verify.)

- [ ] **Step 6: Run test — expect PASS**

```bash
uv run --with ".[dev]" pytest tests/test_bootstrap_datadir.py -v
```

- [ ] **Step 7: Commit**

```bash
git add scripts/_hacienda_bootstrap/__init__.py scripts/_hacienda_bootstrap/datadir.py tests/test_bootstrap_datadir.py
git commit -m "feat(bootstrap): ensure_data_dir idempotent + chmod 0700"
```

---

## Task 15: Bootstrap — OS keychain vault key

**Files:**
- Create: `scripts/_hacienda_bootstrap/keychain.py`
- Create: `tests/test_bootstrap_keychain.py`

- [ ] **Step 1: Write the failing test**

`tests/test_bootstrap_keychain.py`:
```python
import pytest

from _hacienda_bootstrap.keychain import KeychainBackend, ensure_vault_key


class FakeBackend:
    def __init__(self):
        self.store = {}

    def get(self, service: str, account: str) -> str | None:
        return self.store.get((service, account))

    def set(self, service: str, account: str, value: str) -> None:
        self.store[(service, account)] = value


def test_ensure_vault_key_generates_when_missing():
    backend = FakeBackend()
    key = ensure_vault_key(backend, service="hacienda", account="default")
    assert len(key) == 64  # 32 bytes hex-encoded
    assert backend.store[("hacienda", "default")] == key


def test_ensure_vault_key_returns_existing():
    backend = FakeBackend()
    backend.store[("hacienda", "default")] = "a" * 64
    key = ensure_vault_key(backend, service="hacienda", account="default")
    assert key == "a" * 64


def test_ensure_vault_key_uses_secrets_not_random():
    # Statistical check: key must be high-entropy hex
    backend = FakeBackend()
    key = ensure_vault_key(backend, service="hacienda", account="default")
    unique_chars = len(set(key))
    assert unique_chars >= 10, "vault key looks non-random"
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
uv run --with ".[dev]" pytest tests/test_bootstrap_keychain.py -v
```

- [ ] **Step 3: Write `scripts/_hacienda_bootstrap/keychain.py`**

```python
"""OS-keychain-backed vault key management.

Abstracts over macOS Keychain / Windows Credential Manager / libsecret
via a tiny ``KeychainBackend`` protocol so tests can inject a fake.
"""
from __future__ import annotations

import secrets
import sys
from typing import Protocol


class KeychainBackend(Protocol):
    def get(self, service: str, account: str) -> str | None: ...
    def set(self, service: str, account: str, value: str) -> None: ...


def ensure_vault_key(backend: KeychainBackend, *, service: str, account: str) -> str:
    """Return the vault key, creating a new 256-bit random key if missing."""
    existing = backend.get(service, account)
    if existing:
        return existing
    key = secrets.token_hex(32)  # 32 bytes -> 64 hex chars
    backend.set(service, account, key)
    return key


def default_backend() -> KeychainBackend:
    """Return the platform-appropriate backend using the ``keyring`` package."""
    import keyring

    class KeyringBackend:
        def get(self, service: str, account: str) -> str | None:
            return keyring.get_password(service, account)

        def set(self, service: str, account: str, value: str) -> None:
            keyring.set_password(service, account, value)

    return KeyringBackend()
```

- [ ] **Step 4: Add `keyring` to dev deps in `pyproject.toml`**

Edit `[project.optional-dependencies]`:
```toml
dev = [
  "pytest>=8",
  "pytest-mock>=3.12",
  "jsonschema>=4.21",
  "pyyaml>=6.0",
  "ruff>=0.4",
  "keyring>=24",
]
```

- [ ] **Step 5: Run test — expect PASS**

```bash
uv run --with ".[dev]" pytest tests/test_bootstrap_keychain.py -v
```

- [ ] **Step 6: Commit**

```bash
git add scripts/_hacienda_bootstrap/keychain.py tests/test_bootstrap_keychain.py pyproject.toml
git commit -m "feat(bootstrap): vault key in OS keychain (pluggable backend)"
```

---

## Task 16: Bootstrap — daemon spawn + CLI entrypoint

**Files:**
- Create: `scripts/_hacienda_bootstrap/daemon.py`
- Create: `scripts/hacienda-bootstrap`
- Create: `scripts/hacienda-bootstrap.cmd`

- [ ] **Step 1: Write `scripts/_hacienda_bootstrap/daemon.py`**

```python
"""Spawn (or no-op attach to) the vendored piighost daemon."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


def start_daemon(vendor_dir: Path, data_dir: Path) -> None:
    """Start the piighost daemon in the background.

    If a daemon is already running (detected via ``piighost daemon status``
    exit code 0), this is a no-op.
    """
    status = subprocess.run(
        ["uv", "run", "--project", str(vendor_dir), "piighost", "daemon", "status"],
        capture_output=True,
        text=True,
        check=False,
    )
    if status.returncode == 0:
        return

    env = os.environ.copy()
    env["PIIGHOST_DATA_DIR"] = str(data_dir)
    subprocess.Popen(
        ["uv", "run", "--project", str(vendor_dir), "piighost", "daemon", "start"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=(os.name != "nt"),
    )
```

- [ ] **Step 2: Write `scripts/hacienda-bootstrap` (POSIX shebang entry)**

```python
#!/usr/bin/env python3
"""First-run entrypoint — idempotent, safe to call on every activation."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _hacienda_bootstrap.datadir import ensure_data_dir
from _hacienda_bootstrap.daemon import start_daemon
from _hacienda_bootstrap.keychain import default_backend, ensure_vault_key


def main() -> int:
    plugin_dir = Path(os.environ.get("CLAUDE_PLUGIN_ROOT", Path(__file__).parent.parent))
    data_dir = Path(os.environ.get("HACIENDA_DATA_DIR", Path.home() / ".hacienda"))
    vendor_dir = plugin_dir / "vendor" / "piighost"

    ensure_data_dir(data_dir)
    ensure_vault_key(default_backend(), service="hacienda", account="default")
    start_daemon(vendor_dir=vendor_dir, data_dir=data_dir)

    print(f"hacienda: ready at {data_dir}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Make it executable:
```bash
chmod +x scripts/hacienda-bootstrap
```

- [ ] **Step 3: Write `scripts/hacienda-bootstrap.cmd` (Windows wrapper)**

```batch
@echo off
python "%~dp0hacienda-bootstrap" %*
```

- [ ] **Step 4: Smoke-test the entrypoint**

```bash
HACIENDA_DATA_DIR=/tmp/hacienda-smoke CLAUDE_PLUGIN_ROOT="$PWD" python3 scripts/hacienda-bootstrap
```
Expected stderr: `hacienda: ready at /tmp/hacienda-smoke`.
Then `ls /tmp/hacienda-smoke/` shows `sessions/ projects/ logs/`.

Clean up:
```bash
rm -rf /tmp/hacienda-smoke
```

- [ ] **Step 5: Commit**

```bash
git add scripts/_hacienda_bootstrap/daemon.py scripts/hacienda-bootstrap scripts/hacienda-bootstrap.cmd
git commit -m "feat(bootstrap): CLI entrypoint — datadir + keychain + daemon"
```

---

## Task 17: Monitors (watcher notifications)

**Files:**
- Create: `monitors/monitors.json`

- [ ] **Step 1: Write `monitors/monitors.json`**

```json
{
  "monitors": [
    {
      "name": "hacienda-watcher",
      "description": "Stream piighost file-watcher events as Claude notifications",
      "command": "uv",
      "args": [
        "run",
        "--project",
        "${CLAUDE_PLUGIN_ROOT}/vendor/piighost",
        "piighost",
        "watcher",
        "tail",
        "--format",
        "oneline"
      ],
      "env": {
        "PIIGHOST_DATA_DIR": "${HOME}/.hacienda"
      },
      "enabled_by_default": true
    }
  ]
}
```

- [ ] **Step 2: Add a smoke test**

`tests/test_monitors_json_schema.py`:
```python
import json
from pathlib import Path

import jsonschema

MONITORS = Path(__file__).parent.parent / "monitors" / "monitors.json"

SCHEMA = {
    "type": "object",
    "required": ["monitors"],
    "properties": {
        "monitors": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "command", "args"],
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "command": {"type": "string"},
                    "args": {"type": "array", "items": {"type": "string"}},
                    "env": {"type": "object"},
                    "enabled_by_default": {"type": "boolean"},
                },
            },
        }
    },
}


def test_monitors_schema_valid():
    jsonschema.validate(json.loads(MONITORS.read_text(encoding="utf-8")), SCHEMA)


def test_monitor_uses_plugin_dir_variable():
    raw = MONITORS.read_text(encoding="utf-8")
    assert "${CLAUDE_PLUGIN_ROOT}" in raw
```

- [ ] **Step 3: Run test — expect PASS**

```bash
uv run --with ".[dev]" pytest tests/test_monitors_json_schema.py -v
```

- [ ] **Step 4: Commit**

```bash
git add monitors/monitors.json tests/test_monitors_json_schema.py
git commit -m "feat(monitors): piighost watcher event stream → Claude notifications"
```

---

## Task 18: Plugin settings

**Files:**
- Create: `settings.json`

- [ ] **Step 1: Write `settings.json`**

```json
{
  "$schema": "https://json.schemastore.org/claude-plugin-settings",
  "settings": {
    "hacienda.notifications.enabled": {
      "type": "boolean",
      "default": true,
      "title": "Enable folder-watcher notifications",
      "title.fr": "Activer les notifications de surveillance du dossier"
    },
    "hacienda.indexing.network_poll_seconds": {
      "type": "integer",
      "default": 600,
      "minimum": 60,
      "title": "Polling interval for network folders (seconds)",
      "title.fr": "Intervalle d'interrogation pour les dossiers reseau (secondes)"
    },
    "hacienda.redaction.size_cap_mb": {
      "type": "integer",
      "default": 5,
      "minimum": 1,
      "maximum": 50,
      "title": "Outbound payload size cap (MB)",
      "title.fr": "Limite de taille des requetes sortantes (Mo)"
    },
    "hacienda.telemetry.install_counter": {
      "type": "boolean",
      "default": false,
      "title": "Send anonymous install counter (off by default)",
      "title.fr": "Envoyer un compteur d'installation anonyme (desactive par defaut)"
    }
  }
}
```

- [ ] **Step 2: Add schema test**

`tests/test_settings_schema.py`:
```python
import json
from pathlib import Path

SETTINGS = Path(__file__).parent.parent / "settings.json"


def test_settings_every_entry_has_default_and_title():
    data = json.loads(SETTINGS.read_text(encoding="utf-8"))
    for key, entry in data["settings"].items():
        assert "default" in entry, f"{key} missing default"
        assert "title" in entry, f"{key} missing title"


def test_telemetry_is_opt_in():
    data = json.loads(SETTINGS.read_text(encoding="utf-8"))
    assert data["settings"]["hacienda.telemetry.install_counter"]["default"] is False
```

- [ ] **Step 3: Run test — expect PASS**

```bash
uv run --with ".[dev]" pytest tests/test_settings_schema.py -v
```

- [ ] **Step 4: Commit**

```bash
git add settings.json tests/test_settings_schema.py
git commit -m "feat: plugin settings (telemetry opt-in, size caps, poll interval)"
```

---

## Task 19: French localization

**Files:**
- Create: `locales/en.json`
- Create: `locales/fr.json`
- Create: `skills/knowledge-base/SKILL.fr.md`
- Create: `skills/redact-outbound/SKILL.fr.md`
- Create: `README.fr.md`

- [ ] **Step 1: Write `locales/en.json`**

```json
{
  "bootstrap.ready": "hacienda: ready at {data_dir}",
  "redact.block.no_active_folder": "hacienda cannot determine the active Cowork folder. Open a client folder before using outbound tools.",
  "redact.block.size_cap": "Payload exceeds {mb}MB hacienda size cap; narrow the operation or split the input.",
  "status.ready": "hacienda KB ready ({docs} docs)",
  "status.indexing": "hacienda indexing {done}/{total} files ({percent}%)",
  "status.error": "hacienda indexing error: {reason}"
}
```

- [ ] **Step 2: Write `locales/fr.json`**

```json
{
  "bootstrap.ready": "hacienda : pret dans {data_dir}",
  "redact.block.no_active_folder": "hacienda ne peut determiner le dossier Cowork actif. Ouvrez un dossier client avant d'utiliser les outils sortants.",
  "redact.block.size_cap": "La requete depasse la limite hacienda de {mb} Mo ; reduisez l'operation ou decoupez l'entree.",
  "status.ready": "Base de connaissances hacienda prete ({docs} documents)",
  "status.indexing": "hacienda indexe {done}/{total} fichiers ({percent}%)",
  "status.error": "Erreur d'indexation hacienda : {reason}"
}
```

- [ ] **Step 3: Add locale parity test**

`tests/test_locales.py`:
```python
import json
from pathlib import Path

LOCALES = Path(__file__).parent.parent / "locales"


def test_en_and_fr_have_same_keys():
    en = json.loads((LOCALES / "en.json").read_text(encoding="utf-8"))
    fr = json.loads((LOCALES / "fr.json").read_text(encoding="utf-8"))
    assert set(en.keys()) == set(fr.keys()), (
        f"locale mismatch: only in en {set(en)-set(fr)}, only in fr {set(fr)-set(en)}"
    )


def test_all_values_non_empty():
    for name in ("en.json", "fr.json"):
        data = json.loads((LOCALES / name).read_text(encoding="utf-8"))
        for k, v in data.items():
            assert isinstance(v, str) and v, f"{name}:{k} is empty"
```

Run:
```bash
uv run --with ".[dev]" pytest tests/test_locales.py -v
```
Expected: 2 passed.

- [ ] **Step 4: Write `skills/knowledge-base/SKILL.fr.md`**

French translation of the knowledge-base skill. Frontmatter carries **only** `name: knowledge-base` and a French `description:` (Cowork skill contract — no other keys). Same section headings translated (`## 1. Verifier l'etat de l'index d'abord`, etc.). Code/tool names stay in English (they're identifiers, not prose).

Also extend `tests/test_skill_frontmatter.py` — append the FR files to `SKILLS`:
```python
SKILLS = [
    ROOT / "skills" / "knowledge-base" / "SKILL.md",
    ROOT / "skills" / "knowledge-base" / "SKILL.fr.md",
    ROOT / "skills" / "redact-outbound" / "SKILL.md",
    ROOT / "skills" / "redact-outbound" / "SKILL.fr.md",
]
```
so the frontmatter contract is enforced on both language variants.

Key translations:
- "Check index status first" → "Verifier l'etat de l'index d'abord"
- "Search" → "Rechercher"
- "Cite every claim" → "Citer chaque affirmation"
- "Cross-client safety" → "Etancheite entre clients"
- "Placeholders in results" → "Marqueurs dans les resultats"

Full text mirrors `SKILL.md` 1:1 in French.

- [ ] **Step 5: Write `skills/redact-outbound/SKILL.fr.md`**

French translation of the redact-outbound skill, same structure.

Key translations:
- "Placeholder vocabulary" → "Vocabulaire des marqueurs"
- "Rules for drafting" → "Regles de redaction"
- "Consistency matters" → "La coherence compte"
- "Never invent mappings" → "Ne jamais inventer de correspondances"

- [ ] **Step 6: Write `README.fr.md`**

French version of the README. Install steps, usage examples, license section.

- [ ] **Step 7: Commit**

```bash
git add locales/ skills/knowledge-base/SKILL.fr.md skills/redact-outbound/SKILL.fr.md README.fr.md tests/test_locales.py
git commit -m "feat: French localization (locales + skills + README)"
```

---

## Task 20: README + marketplace assets

**Files:**
- Modify: `README.md` (replace stub)
- Create: `icon.png` (placeholder, commissioned-replace later)

- [ ] **Step 1: Write full `README.md`**

```markdown
# hacienda

**The Cowork plugin that makes Claude Desktop safe under professional secrecy.**

PII-safe RAG over your client folders, directly inside Claude Desktop.
Built for avocats, notaires, experts-comptables, medecins, and every
professional bound by *secret professionnel*.

## What it does

- **Knowledge base over your active Cowork folder.** Ask questions.
  Get answers with citations. Hybrid BM25 + semantic retrieval.
- **Redacted-transit.** Before anything leaves your laptop, personal data
  is replaced with placeholders. The mappings stay on your machine.
- **Zero setup.** Install from the marketplace. Open a folder. Ask.

## Install

From the Anthropic Cowork marketplace — search for **hacienda**.

Or install from GitHub:
```bash
# From the Cowork plugin manager
> /plugin install https://github.com/jamon8888/hacienda
```

## First use

1. Open Claude Desktop.
2. Enter Cowork mode.
3. Click the folder icon and pick your client folder.
4. A chip appears: *"hacienda: indexing…"*. Wait for *"ready"*.
5. Ask: *"What are the outstanding deliverables from this client?"*

## Commands

- `/hacienda:index` — force a re-index
- `/hacienda:kb-status` — show index state
- `/hacienda:audit` — show PII audit trail for this session
- `/hacienda:brief` — one-page intake brief of the folder
- `/hacienda:draft-reply` — draft a reply to the latest email

## What gets sent to Anthropic

Only placeholders. Real names, IBANs, phone numbers, addresses, and case
numbers are redacted before leaving your machine. The vault key is stored
in your OS keychain and never logged.

See [`docs/data-flow.md`](docs/data-flow.md) for the full diagram.

## License

MIT. See [LICENSE](LICENSE).

Commercial support (SLA, onboarding, custom vertical profiles) available —
see https://piighost.com/support.

## Français

Voir [README.fr.md](README.fr.md).
```

- [ ] **Step 2: Generate placeholder icon**

Create a 512x512 PNG placeholder (walled-estate silhouette, dark green on cream). For v0.1.0 any square PNG of at least 256x256 is acceptable — it will be replaced before the marketplace submission. Generate with any image tool or use a solid-color placeholder:

```bash
python3 -c "
from PIL import Image, ImageDraw, ImageFont
img = Image.new('RGB', (512, 512), '#f5f0e1')
d = ImageDraw.Draw(img)
d.rectangle([64, 128, 448, 448], fill='#2d4a2b')
d.rectangle([128, 192, 192, 448], fill='#f5f0e1')
d.rectangle([320, 192, 384, 448], fill='#f5f0e1')
d.text((220, 64), 'H', fill='#2d4a2b')
img.save('icon.png')
"
```

Or drop in any pre-made PNG at `icon.png`. Commit whichever:

- [ ] **Step 3: Commit**

```bash
git add README.md icon.png
git commit -m "docs: full README + placeholder icon"
```

---

## Task 21: CI pipeline

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Write `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  test:
    name: Tests + lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
        with:
          python-version: "3.11"
      - name: Install dev deps
        run: uv sync --extra dev --no-progress -q
      - name: Lint
        run: uv run ruff check .
      - name: Run tests
        run: uv run pytest -v

  schema-validate:
    name: Schema validation
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
        with:
          python-version: "3.11"
      - run: uv sync --extra dev --no-progress -q
      - run: uv run pytest tests/test_manifest_schema.py tests/test_mcp_json_schema.py tests/test_hooks_json_schema.py tests/test_monitors_json_schema.py tests/test_settings_schema.py -v
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: lint + pytest + schema validation"
```

- [ ] **Step 3: Push branch and verify CI green**

```bash
git push -u origin main
```

Watch `gh run watch` or the Actions tab. If anything fails, fix and push again.

---

## Task 22: mcpb packaging script

**Files:**
- Create: `scripts/package-mcpb.sh`

- [ ] **Step 1: Write `scripts/package-mcpb.sh`**

```bash
#!/usr/bin/env bash
# Package the plugin as a .mcpb bundle for marketplace distribution.
# Assumes `mcpb` CLI is installed (npm i -g @anthropic-ai/mcpb).
set -euo pipefail

VERSION=$(python3 -c "import json; print(json.load(open('.claude-plugin/plugin.json'))['version'])")
OUT="dist/hacienda-${VERSION}.mcpb"

mkdir -p dist

# Ensure vendor/piighost/ is populated before packaging
if [ ! -f vendor/piighost/manifest.json ]; then
  echo "error: vendor/piighost/ not populated. Run scripts/vendor-piighost.sh first." >&2
  exit 1
fi

mcpb pack . "$OUT"

echo "Packaged $OUT ($(du -h $OUT | cut -f1))"
```

Make executable:
```bash
chmod +x scripts/package-mcpb.sh
```

- [ ] **Step 2: Dry-run (vendor directory must be populated)**

```bash
PIIGHOST_BUNDLE_SRC="../piighost/bundles/full" bash scripts/vendor-piighost.sh
bash scripts/package-mcpb.sh || echo "mcpb CLI not installed locally — will run in CI"
```

- [ ] **Step 3: Commit**

```bash
git add scripts/package-mcpb.sh
git commit -m "build: mcpb packaging script"
```

---

## Task 23: Vendor-sync workflow

**Files:**
- Create: `.github/workflows/vendor-sync.yml`

- [ ] **Step 1: Write `.github/workflows/vendor-sync.yml`**

```yaml
name: Vendor sync

on:
  workflow_dispatch:
    inputs:
      piighost_ref:
        description: "piighost git ref to vendor"
        required: true
        default: "main"

permissions:
  contents: write
  pull-requests: write

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Checkout piighost
        uses: actions/checkout@v4
        with:
          repository: jamon8888/piighost
          path: piighost-src
          ref: ${{ inputs.piighost_ref }}
      - name: Run vendor script
        run: PIIGHOST_BUNDLE_SRC=piighost-src/bundles/full bash scripts/vendor-piighost.sh
      - name: Open PR
        uses: peter-evans/create-pull-request@v6
        with:
          commit-message: "chore: vendor piighost @ ${{ inputs.piighost_ref }}"
          title: "Vendor piighost @ ${{ inputs.piighost_ref }}"
          body: "Automated vendor sync from piighost ref `${{ inputs.piighost_ref }}`."
          branch: vendor-sync/${{ inputs.piighost_ref }}
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/vendor-sync.yml
git commit -m "ci: workflow_dispatch vendor sync from piighost"
```

---

## Task 24: End-to-end smoke test (manual)

**Files:** none — this is an operator task documented for reproducibility.

- [ ] **Step 1: Create a throwaway client folder**

```bash
mkdir -p /tmp/Dossiers/ACME
cp ~/some-sample-pdfs/*.pdf /tmp/Dossiers/ACME/
```

- [ ] **Step 2: Install the plugin locally**

In Claude Desktop's plugin manager, add the local path:
```
/plugin install file://C:/Users/NMarchitecte/Documents/hacienda
```

- [ ] **Step 3: Verify bootstrap ran**

```bash
ls ~/.hacienda/sessions ~/.hacienda/projects ~/.hacienda/logs
```
Expected: all three dirs exist.

- [ ] **Step 4: Open `/tmp/Dossiers/ACME` in Cowork**

Expect the status chip: *"hacienda: indexing 3/N files"* → *"hacienda KB ready"*.

- [ ] **Step 5: Ask a content question**

*"Quels sont les livrables en retard sur ce dossier?"*

Verify in the response:
- At least one citation of the form `[file.pdf p.N]`.
- No raw client name appears in the model's response; only placeholders like `«PER_001»`.

- [ ] **Step 6: Run `/hacienda:audit`**

Verify the audit surfaces:
- The `redact` events for the question (if the user typed any PII in chat).
- The `rehydrate` sidecar events for each `hybrid_search` call.

- [ ] **Step 7: Switch folders mid-session**

Open `/tmp/Dossiers/BETA` (create one with unrelated content). Ask an ACME question. Verify the model refuses and suggests switching back to ACME.

- [ ] **Step 8: Document results**

Append to `docs/smoke-test-log.md`:
```markdown
## 2026-MM-DD smoke test
- Plugin version: 0.1.0
- piighost vendored: <version from vendor/piighost/.version>
- OS: Windows 11 / macOS 14.x / Ubuntu 24.04
- Result: PASS | FAIL (notes: …)
```

- [ ] **Step 9: Commit the smoke log**

```bash
git add docs/smoke-test-log.md
git commit -m "docs: v0.1.0 end-to-end smoke test log"
```

---

## Task 25: Release v0.1.0

**Files:** none — git tagging.

- [ ] **Step 1: Run full CI locally**

```bash
uv run ruff check .
uv run pytest -v
```
Expected: 0 failures.

- [ ] **Step 2: Bump version in `.claude-plugin/plugin.json`** (already `0.1.0`; verify)

- [ ] **Step 3: Tag and push**

```bash
git tag -a v0.1.0 -m "v0.1.0 — first marketplace-ready build"
git push origin v0.1.0
```

- [ ] **Step 4: Build the mcpb bundle**

```bash
PIIGHOST_BUNDLE_SRC="../piighost/bundles/full" bash scripts/vendor-piighost.sh
bash scripts/package-mcpb.sh
```

Expected: `dist/hacienda-0.1.0.mcpb` produced.

- [ ] **Step 5: Draft a GitHub release**

```bash
gh release create v0.1.0 dist/hacienda-0.1.0.mcpb \
  --title "v0.1.0 — first marketplace-ready build" \
  --notes "First public release. See README.md for install + usage."
```

- [ ] **Step 6: Submit to Anthropic marketplace**

Follow the Cowork marketplace submission portal. Attach:
- `dist/hacienda-0.1.0.mcpb`
- `README.md` and `README.fr.md`
- `icon.png` (final, commissioned)
- Screenshots of the status chip, a cited answer, `/hacienda:audit` output.

---

## Self-Review

**Spec coverage:** Walked § 4 (Scope in/out) against the plan:
- Manifest + marketplace metadata → Task 1, Task 20.
- Bundled piighost MCP server → Task 2, vendor sync in Task 23.
- `knowledge-base` skill → Task 9.
- `redact-outbound` skill → Task 10.
- Redaction seatbelt hooks (Pre/PostToolUse) → Tasks 6, 7, 8.
- `/hacienda:index`, `/hacienda:kb-status`, `/hacienda:audit` → Task 11.
- `/hacienda:brief`, `/hacienda:draft-reply` (stretch) → Task 12.
- Status surface `hacienda://kb/status` → Task 2 (.mcp.json alias) + Task 11 consumption.
- Monitors → Task 17.
- Indexing lifecycle (lazy+watcher+poll) → Task 11 (command) + Task 17 (monitor) + Task 18 (`network_poll_seconds` setting).
- Redacted-transit confidentiality → Tasks 3-8.
- FR + EN localization → Task 19.
- MIT license → Task 0.
- Bootstrap (datadir, keychain, daemon) → Tasks 14, 15, 16.
- Settings → Task 18.
- Audit trail → Task 5 (log) + Task 11 (command) + Task 13 (subagent).
- CI → Task 21.
- mcpb packaging → Task 22.
- Vendor-sync automation → Task 23.
- E2E smoke + release → Tasks 24, 25.

No gaps. Every spec requirement maps to at least one task.

**Placeholder scan:** No "TBD", "implement later", or "handle edge cases" prose. Every code block is complete.

**Type consistency:**
- `PiighostCLI.anonymize(text: str, *, project: str) -> AnonymizeResult` consistent between Task 4 and Task 6 usage.
- `AuditLog.record(event, tool, project, placeholders)` consistent between Task 5 and Task 6.
- `resolve_project_name(folder: Path) -> str` consistent across Tasks 3, 6, 7.
- `ensure_vault_key(backend, *, service, account) -> str` consistent across Tasks 15, 16.
- Env vars consistent: `CLAUDE_PLUGIN_ROOT`, `HACIENDA_ACTIVE_FOLDER`, `HACIENDA_DATA_DIR` used identically everywhere.
- MCP tool names: `mcp__hacienda__hybrid_search`, `mcp__hacienda__index_path`, `mcp__hacienda__vault_get` — same spellings in hooks.json matcher, SKILL.md prose guidance, and command `allowed-tools`.
- Cowork skill contract respected: SKILL.md frontmatter carries only `name` and `description`; tool invocation happens through `.mcp.json` session-level tools (used by commands with `allowed-tools` and by the redaction-agent with `tools`).
- `hacienda://kb/status` resource URI used consistently.

All checks pass. No fixes needed.
