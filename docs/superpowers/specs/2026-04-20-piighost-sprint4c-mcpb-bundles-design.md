# piighost Sprint 4c — MCPB Bundles Design

**Date:** 2026-04-20
**Scope:** Ship `piighost-core.mcpb` and `piighost-full.mcpb` so Claude Desktop users can install the piighost MCP server with one click via the [MCP Bundles](https://github.com/modelcontextprotocol/mcpb) format.

---

## Goals

1. Two `.mcpb` artifacts, both using MCPB `server.type: "uv"` so dependencies resolve at install time via UV's venv + cache (no vendored `lib/`).
2. `piighost-core.mcpb` — 8 tools (anonymize, rehydrate, detect, vault_*, daemon_*). Install footprint ~50 MB after UV cache populates. Deps: `piighost[mcp]`.
3. `piighost-full.mcpb` — all 10 tools including `index_path` and `query`. Install footprint ~1.5 GB on first install (cached thereafter). Deps: `piighost[mcp,index,gliner2]`.
4. One-change MCP server: `piighost.mcp.server.build_mcp` conditionally registers the two indexing tools based on whether `sentence_transformers` can be imported.
5. CI builds both bundles on tag push and attaches them to the GitHub Release.

## Non-goals

- Vendoring Python dependencies inside the `.mcpb` zip (`"type": "uv"` handles this).
- Shipping a pre-populated LanceDB or BM25 index inside the bundle.
- Claude Desktop version-specific binaries (`_meta.com.microsoft.windows.static_responses` etc.).
- Submission to any MCPB "curated directory" — that process is not public at spec version 0.4.

---

## 1. Architecture

```
bundles/
├── core/
│   ├── manifest.json       # piighost-core bundle manifest
│   ├── pyproject.toml      # declares piighost[mcp]==<version>
│   ├── icon.png
│   └── src/server.py       # MCPB entry point
└── full/
    ├── manifest.json       # piighost-full bundle manifest
    ├── pyproject.toml      # declares piighost[mcp,index,gliner2]==<version>
    ├── icon.png
    └── src/server.py       # identical file content to core's

scripts/
└── build_mcpb.py           # zips each bundle into dist/mcpb/piighost-<variant>.mcpb

.github/workflows/
└── mcpb.yml                # on tag push: build + upload to GitHub Release

src/piighost/mcp/
└── server.py               # MODIFY: gate index_path + query on importlib find_spec
```

The two `src/server.py` files are byte-identical. What differs between bundles is `pyproject.toml` (which extras) and `manifest.json` (name, description, optional user_config fields). The server discovers which tools to expose at runtime by probing for `sentence_transformers`.

## 2. manifest.json

### Core bundle (`bundles/core/manifest.json`)

```json
{
  "manifest_version": "0.4",
  "name": "piighost-core",
  "display_name": "piighost (Core)",
  "version": "0.8.0",
  "description": "GDPR PII anonymization and vault — core tools (no indexing)",
  "long_description": "piighost provides GDPR-compliant PII anonymization, rehydration, and vault operations as MCP tools. This core bundle includes the anonymization pipeline and vault management without the heavier document indexing and retrieval tools.",
  "author": { "name": "Athroniaeth" },
  "homepage": "https://github.com/Athroniaeth/piighost",
  "repository": { "type": "git", "url": "https://github.com/Athroniaeth/piighost.git" },
  "support": "https://github.com/Athroniaeth/piighost/issues",
  "icon": "icon.png",
  "server": {
    "type": "uv",
    "entry_point": "src/server.py",
    "mcp_config": {
      "command": "uv",
      "args": ["run", "--directory", "${__dirname}", "src/server.py"],
      "env": {
        "PIIGHOST_VAULT_DIR": "${user_config.vault_dir}"
      }
    }
  },
  "compatibility": {
    "platforms": ["darwin", "linux", "win32"],
    "runtimes": { "python": ">=3.10" }
  },
  "user_config": {
    "vault_dir": {
      "type": "directory",
      "title": "Vault Directory",
      "description": "Location of your PII vault (persisted across sessions)",
      "required": true,
      "default": "${HOME}/.piighost/vault"
    }
  },
  "keywords": ["pii", "anonymization", "gdpr", "privacy", "vault"],
  "license": "MIT"
}
```

### Full bundle (`bundles/full/manifest.json`)

Same base, with these deltas:

- `name`: `"piighost-full"`
- `display_name`: `"piighost (Full)"`
- `description`: `"GDPR PII anonymization, vault, and document indexing + retrieval"`
- Additional `keywords`: `["rag", "retrieval", "indexing"]`
- Additional `user_config.mistral_api_key`:
  ```json
  "mistral_api_key": {
    "type": "string",
    "title": "Mistral API Key (optional)",
    "description": "Required only if embedder backend is 'mistral'. Leave blank to use local embeddings.",
    "sensitive": true,
    "required": false
  }
  ```
- Additional `env` entry in `mcp_config`: `"MISTRAL_API_KEY": "${user_config.mistral_api_key}"`

## 3. Bundle `pyproject.toml`

### Core (`bundles/core/pyproject.toml`)

```toml
[project]
name = "piighost-core-bundle"
version = "0.8.0"
description = "Embedded dependencies for piighost-core MCPB"
requires-python = ">=3.10"
dependencies = [
    "piighost[mcp]==0.8.0",
]
```

### Full (`bundles/full/pyproject.toml`)

```toml
[project]
name = "piighost-full-bundle"
version = "0.8.0"
description = "Embedded dependencies for piighost-full MCPB"
requires-python = ">=3.10"
dependencies = [
    "piighost[mcp,index,gliner2]==0.8.0",
]
```

Versions are pinned exactly so a given `.mcpb` always installs the same piighost release. When a new piighost version ships, the bundle versions bump in lockstep via `scripts/build_mcpb.py` reading the root `pyproject.toml` version.

## 4. Server entry point (`bundles/{core,full}/src/server.py`)

Identical file, 15 lines:

```python
"""MCPB entry point — invoked by `uv run src/server.py`."""
from __future__ import annotations

import os
from pathlib import Path

from piighost.mcp.server import run_mcp


def main() -> None:
    vault_dir = Path(os.environ["PIIGHOST_VAULT_DIR"]).expanduser()
    vault_dir.mkdir(parents=True, exist_ok=True)
    run_mcp(vault_dir, transport="stdio")


if __name__ == "__main__":
    main()
```

## 5. Tool gating in `src/piighost/mcp/server.py`

Add this helper at the top of the module:

```python
def _indexing_available() -> bool:
    import importlib.util
    return importlib.util.find_spec("sentence_transformers") is not None
```

Wrap the `index_path` and `query` tool registrations in a single conditional:

```python
if _indexing_available():
    @mcp.tool(description="Index a file or directory into the retrieval store")
    async def index_path(path: str, recursive: bool = True, force: bool = False) -> dict:
        report = await svc.index_path(Path(path), recursive=recursive, force=force)
        return report.model_dump()

    @mcp.tool(description="Hybrid BM25+vector search over indexed documents")
    async def query(text: str, k: int = 5) -> dict:
        result = await svc.query(text, k=k)
        return result.model_dump()
```

No other tool registration logic changes. The core bundle ends up exposing 8 tools; the full bundle exposes 10.

## 6. Build script (`scripts/build_mcpb.py`)

The script reads the root `pyproject.toml` version, templates it into each bundle's `manifest.json` and `pyproject.toml`, then zips:

```python
"""Build piighost-core.mcpb and piighost-full.mcpb from bundles/{core,full}/."""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


ROOT = Path(__file__).resolve().parent.parent
BUNDLES = ROOT / "bundles"
DIST = ROOT / "dist" / "mcpb"

_EXTRAS = {"core": "mcp", "full": "mcp,index,gliner2"}


def _read_root_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
    return data["project"]["version"]


def _render_manifest(variant: str, version: str) -> str:
    manifest_path = BUNDLES / variant / "manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    manifest["version"] = version
    return json.dumps(manifest, indent=2) + "\n"


def _render_pyproject(variant: str, version: str) -> str:
    extras = _EXTRAS[variant]
    return (
        f'[project]\n'
        f'name = "piighost-{variant}-bundle"\n'
        f'version = "{version}"\n'
        f'description = "Embedded dependencies for piighost-{variant} MCPB"\n'
        f'requires-python = ">=3.10"\n'
        f'dependencies = [\n'
        f'    "piighost[{extras}]=={version}",\n'
        f']\n'
    )


def build(variant: str, version: str) -> Path:
    src = BUNDLES / variant
    out = DIST / f"piighost-{variant}.mcpb"
    out.parent.mkdir(parents=True, exist_ok=True)

    rendered = {
        "manifest.json": _render_manifest(variant, version),
        "pyproject.toml": _render_pyproject(variant, version),
    }

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(src.rglob("*")):
            if not path.is_file():
                continue
            arcname = str(path.relative_to(src)).replace("\\", "/")
            if arcname in rendered:
                zf.writestr(arcname, rendered[arcname])
            else:
                zf.write(path, arcname)
    return out


if __name__ == "__main__":
    version = _read_root_version()
    for variant in ("core", "full"):
        print(f"Built: {build(variant, version)}")
```

Deterministic output: `sorted(src.rglob("*"))` ensures zip ordering is stable. The on-disk `manifest.json` and `pyproject.toml` in `bundles/{core,full}/` hold canonical content; the script overwrites only the `version` field at build time. This lets developers edit manifests in the repo without re-running the script to see their changes, while guaranteeing the packaged version always matches the root project.

## 7. CI workflow (`.github/workflows/mcpb.yml`)

```yaml
name: Build MCPB bundles

on:
  push:
    tags: ["[0-9]+.[0-9]+.[0-9]+"]
  workflow_dispatch:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v5

      - name: Install mcpb CLI
        run: npm install -g @anthropic-ai/mcpb

      - name: Validate manifests
        run: |
          mcpb validate bundles/core
          mcpb validate bundles/full

      - name: Build bundles
        run: uv run python scripts/build_mcpb.py

      - name: Upload to GitHub Release
        if: startsWith(github.ref, 'refs/tags/')
        uses: softprops/action-gh-release@v2
        with:
          files: |
            dist/mcpb/piighost-core.mcpb
            dist/mcpb/piighost-full.mcpb
```

Runs in parallel with `release.yml`. Assets are appended to the same Release created by `release.yml` (via `softprops/action-gh-release`, which merges assets into an existing Release for the same tag).

## 8. Testing

| Test | Type | File |
|------|------|------|
| `_indexing_available()` returns correct value | Unit | `tests/unit/test_mcp_indexing_gate.py` |
| When indexing deps are absent, `mcp.get_tools()` lacks `index_path` and `query` | Unit (monkeypatch `find_spec`) | same file |
| Core `manifest.json` validates against MCPB schema | CI step (`mcpb validate`) | `.github/workflows/mcpb.yml` |
| Full `manifest.json` validates | CI step | same |
| `scripts/build_mcpb.py` produces valid zip | Unit | `tests/unit/test_build_mcpb.py` — opens the produced zip and asserts `manifest.json` + `src/server.py` are present, `manifest.json.version` matches root `pyproject.toml.version`, and `pyproject.toml` contains `piighost[<extras>]==<version>` |
| End-to-end install in Claude Desktop | Manual | `docs/mcpb-install.md` walkthrough |

Skip: actually launching `uv run` to install `piighost[index]` in a CI job. Too slow (adds ~5 minutes per CI run). Covered by the existing unit test suite on master.

## 9. README + docs updates

Append to `README.md` under "## Installation":

```markdown
### Claude Desktop (MCPB)

One-click install for Claude Desktop users:

1. Download the latest `piighost-core.mcpb` (anonymization only) or `piighost-full.mcpb` (with document indexing) from the [GitHub Releases page](https://github.com/Athroniaeth/piighost/releases/latest).
2. Double-click the file — Claude Desktop will prompt for install confirmation.
3. On first run, UV installs the required Python packages. Core finishes in ~30 seconds, full takes 3-10 minutes depending on connection speed (heavy deps: torch, sentence-transformers).
4. Open a new conversation — piighost tools appear in the tool picker.
```

New file `docs/mcpb-install.md`:
- Screenshots of the install dialog
- Manual workaround if one-click install fails (unzip into `~/.config/Claude/extensions/piighost/` and restart Claude Desktop)
- How to edit the vault directory after install (Claude Desktop Settings → Extensions → piighost → Configure)
- Troubleshooting: UV not found, Python version mismatch, proxy/offline envs

## 10. Error handling

- Manifest validation is a hard CI gate. `mcpb validate` exit non-zero blocks the release asset upload.
- If a user installs the core bundle but then calls `index_path` via MCP, Claude Desktop never shows the tool (because `_indexing_available()` returns false → not registered). No error path required.
- If `PIIGHOST_VAULT_DIR` is unset (user skipped the required `user_config.vault_dir`), `Path(os.environ["PIIGHOST_VAULT_DIR"])` raises `KeyError` at startup. Claude Desktop surfaces the error. This is the right behavior: a vault path is required.
- `MISTRAL_API_KEY` absent in the full bundle with `mistral` embedder selected — already handled by Sprint 4a's `build_embedder` fast-fail (`RuntimeError("MISTRAL_API_KEY not set for mistral embedder")`).

## 11. PII safety invariants (preserved)

- MCPB bundles don't introduce new PII paths. The server still uses `piighost.mcp.server:build_mcp`, which already passes Sprint 4a's MCP `reveal` audit and fixture tests.
- The bundle manifest declares `MISTRAL_API_KEY` as `sensitive: true`, so Claude Desktop UI masks it in the config editor.
- `user_config.vault_dir` is a filesystem path — not PII. Safe to persist in Claude Desktop's extension config.

## 12. Acceptance criteria

- `bundles/core/manifest.json` and `bundles/full/manifest.json` pass `mcpb validate` with zero warnings.
- `scripts/build_mcpb.py` produces two `.mcpb` files under `dist/mcpb/`, each under 10 MB (they're just source + manifest).
- On tag push, the CI job publishes both bundles as release assets alongside the wheel.
- Unit tests verify `index_path` / `query` are NOT registered when `sentence_transformers` is not importable, and ARE registered otherwise.
- Manual smoke: opening `piighost-core.mcpb` in Claude Desktop on macOS/Windows results in one-click install → tools appear in a new conversation.
- README documents the install flow with links to the release assets.

## 13. Assets to source before implementation

- `bundles/core/icon.png` and `bundles/full/icon.png` — 256×256 PNG, transparent background, piighost branding. Can be identical across variants or differ slightly (e.g., "core" vs "full" badge). If no brand-approved icon exists yet, use a simple typographic glyph (letter "P" on a colored square) for the first release and replace in Sprint 5.

## 14. Out of scope

- Auto-updating bundles via Claude Desktop's background update mechanism (MCPB spec supports it but we defer to Sprint 4d).
- Signing the `.mcpb` file (MCPB spec 0.4 does not require signatures; Claude Desktop shows an "unverified publisher" warning either way).
- Icons for light/dark themes — single `icon.png` for now.
- Localization (`localization.resources`) — English-only for the first release.
- Any MCPB "directory"/registry submission. That ecosystem does not exist yet at spec 0.4.
