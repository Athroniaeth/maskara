# piighost Sprint 4c — MCPB Bundles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `piighost-core.mcpb` and `piighost-full.mcpb` bundles so Claude Desktop users can install piighost MCP with one click via the [MCPB format](https://github.com/modelcontextprotocol/mcpb).

**Architecture:** Two UV-based bundles (no vendored deps) that differ only in their `pyproject.toml` extras. The shared MCP server gates `index_path` / `query` tool registration on `importlib.util.find_spec("sentence_transformers")`, so the core bundle naturally exposes 8 tools and full exposes 10. A build script reads the root version and templates it into each bundle's `manifest.json` + `pyproject.toml`, zips the result. CI runs on tag push.

**Tech Stack:** Python 3.10+, FastMCP, UV, zipfile (stdlib), MCPB spec 0.4, GitHub Actions, `@anthropic-ai/mcpb` CLI (node).

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `src/piighost/mcp/server.py` | Gate `index_path` + `query` tool registration on `sentence_transformers` availability |
| Create | `bundles/core/manifest.json` | Core bundle manifest |
| Create | `bundles/core/pyproject.toml` | Core bundle deps (`piighost[mcp]`) |
| Create | `bundles/core/icon.png` | Placeholder icon (256x256 PNG) |
| Create | `bundles/core/src/server.py` | MCPB entry point |
| Create | `bundles/full/manifest.json` | Full bundle manifest with extra user_config |
| Create | `bundles/full/pyproject.toml` | Full bundle deps (`piighost[mcp,index,gliner2]`) |
| Create | `bundles/full/icon.png` | Placeholder icon |
| Create | `bundles/full/src/server.py` | Identical to core's |
| Create | `scripts/build_mcpb.py` | Version-template + zip into `dist/mcpb/piighost-{core,full}.mcpb` |
| Create | `.github/workflows/mcpb.yml` | CI: validate + build + upload assets on tag push |
| Create | `tests/unit/test_mcp_indexing_gate.py` | Tool gating behavior |
| Create | `tests/unit/test_build_mcpb.py` | Build script produces valid zip with templated version |
| Modify | `README.md` | Append MCPB install section |
| Create | `docs/mcpb-install.md` | Detailed install walkthrough |

---

### Task 1: Tool gating in `piighost.mcp.server`

**Files:**
- Modify: `src/piighost/mcp/server.py`
- Create: `tests/unit/test_mcp_indexing_gate.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_mcp_indexing_gate.py`:

```python
import asyncio
import importlib.util
import pytest


@pytest.fixture()
def built_mcp(tmp_path, monkeypatch):
    monkeypatch.setenv("PIIGHOST_EMBEDDER", "stub")
    monkeypatch.setenv("PIIGHOST_DETECTOR", "stub")
    from piighost.mcp.server import build_mcp

    vault_dir = tmp_path / "vault"
    mcp, svc = asyncio.run(build_mcp(vault_dir))
    yield mcp, svc
    asyncio.run(svc.close())


def test_indexing_tools_registered_when_available(built_mcp):
    mcp, _ = built_mcp
    tools = asyncio.run(mcp.get_tools())
    assert "index_path" in tools
    assert "query" in tools


def test_indexing_tools_not_registered_when_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("PIIGHOST_EMBEDDER", "stub")
    monkeypatch.setenv("PIIGHOST_DETECTOR", "stub")

    real_find_spec = importlib.util.find_spec

    def fake_find_spec(name, *args, **kwargs):
        if name == "sentence_transformers":
            return None
        return real_find_spec(name, *args, **kwargs)

    monkeypatch.setattr("importlib.util.find_spec", fake_find_spec)

    from piighost.mcp.server import build_mcp

    vault_dir = tmp_path / "vault"
    mcp, svc = asyncio.run(build_mcp(vault_dir))
    try:
        tools = asyncio.run(mcp.get_tools())
        assert "index_path" not in tools
        assert "query" not in tools
        assert "anonymize_text" in tools
        assert "rehydrate_text" in tools
        assert "vault_list" in tools
    finally:
        asyncio.run(svc.close())
```

- [ ] **Step 2: Run test to verify failure**

```bash
cd C:/Users/NMarchitecte/Documents/piighost
python -m pytest tests/unit/test_mcp_indexing_gate.py -v -p no:randomly
```

Expected: `test_indexing_tools_not_registered_when_unavailable` FAILS — tools are currently registered unconditionally.

- [ ] **Step 3: Add `_indexing_available` helper and gate registrations**

Edit `src/piighost/mcp/server.py`. After the existing imports (around line 11), add:

```python
def _indexing_available() -> bool:
    import importlib.util
    return importlib.util.find_spec("sentence_transformers") is not None
```

Then find the two tool registrations (`index_path` and `query`, currently at lines 28-36 after Sprint 4a). Wrap them in a single conditional:

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

**Note**: Keep indentation correct — the `if` block lives inside `build_mcp`, so the tool decorators sit at the same indentation level as the other tools. The existing `index_path` tool signature may not already include `force: bool = False` — check Sprint 4a's commit. If the existing signature is `async def index_path(path: str, recursive: bool = True) -> dict:` without `force`, add it now since Sprint 3 wired `force` into the service layer.

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/unit/test_mcp_indexing_gate.py -v -p no:randomly
```

Expected: 2 PASSED.

- [ ] **Step 5: Run full suite (no regressions)**

```bash
python -m pytest tests/unit/ tests/e2e/ -q -p no:randomly 2>&1 | tail -5
```

Expected: all passing (153+ tests).

- [ ] **Step 6: Commit**

```bash
git add src/piighost/mcp/server.py tests/unit/test_mcp_indexing_gate.py
git commit -m "feat(mcp): gate index_path/query tools on sentence_transformers availability"
```

---

### Task 2: Core bundle skeleton

**Files:**
- Create: `bundles/core/manifest.json`
- Create: `bundles/core/pyproject.toml`
- Create: `bundles/core/src/server.py`
- Create: `bundles/core/icon.png` (placeholder — solid-color PNG)

- [ ] **Step 1: Create `bundles/core/manifest.json`**

```json
{
  "manifest_version": "0.4",
  "name": "piighost-core",
  "display_name": "piighost (Core)",
  "version": "0.8.0",
  "description": "GDPR PII anonymization and vault — core tools (no indexing)",
  "long_description": "piighost provides GDPR-compliant PII anonymization, rehydration, and vault operations as MCP tools. This core bundle includes the anonymization pipeline and vault management without the heavier document indexing and retrieval tools.",
  "author": {
    "name": "Athroniaeth"
  },
  "homepage": "https://github.com/Athroniaeth/piighost",
  "repository": {
    "type": "git",
    "url": "https://github.com/Athroniaeth/piighost.git"
  },
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
    "runtimes": {
      "python": ">=3.10"
    }
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

- [ ] **Step 2: Create `bundles/core/pyproject.toml`**

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

- [ ] **Step 3: Create `bundles/core/src/server.py`**

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

- [ ] **Step 4: Create placeholder `bundles/core/icon.png`**

Generate a 256x256 solid-color PNG with a simple "P" letter. Use Python:

```bash
cd C:/Users/NMarchitecte/Documents/piighost
python -c "
from pathlib import Path
import struct, zlib

# Minimal 256x256 solid-color PNG (dark teal #14524d)
def make_png(width, height, rgb, out_path):
    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xFFFFFFFF)
    ihdr = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    row = bytes([0]) + bytes(rgb * width)
    raw = row * height
    idat = zlib.compress(raw, 9)
    png = b'\\x89PNG\\r\\n\\x1a\\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', idat) + chunk(b'IEND', b'')
    Path(out_path).write_bytes(png)

make_png(256, 256, [0x14, 0x52, 0x4d], 'bundles/core/icon.png')
print('core icon written')
"
```

The icon can be replaced later with proper branding. For now, we need a valid PNG for the bundle to pass `mcpb validate`.

- [ ] **Step 5: Validate manifest**

If `mcpb` CLI is available (install via `npm install -g @anthropic-ai/mcpb`), run:

```bash
mcpb validate bundles/core
```

Expected: no errors. If `mcpb` CLI is NOT available locally, skip this step — CI will enforce validation.

- [ ] **Step 6: Commit**

```bash
git add bundles/core/
git commit -m "feat(mcpb): piighost-core bundle skeleton (manifest + entrypoint)"
```

---

### Task 3: Full bundle skeleton

**Files:**
- Create: `bundles/full/manifest.json`
- Create: `bundles/full/pyproject.toml`
- Create: `bundles/full/src/server.py`
- Create: `bundles/full/icon.png`

- [ ] **Step 1: Create `bundles/full/manifest.json`**

```json
{
  "manifest_version": "0.4",
  "name": "piighost-full",
  "display_name": "piighost (Full)",
  "version": "0.8.0",
  "description": "GDPR PII anonymization, vault, and document indexing + retrieval",
  "long_description": "piighost provides GDPR-compliant PII anonymization, rehydration, vault operations, plus full document indexing with hybrid BM25+vector retrieval as MCP tools. First-run installation downloads ~1.5 GB of Python packages (torch, sentence-transformers, lancedb).",
  "author": {
    "name": "Athroniaeth"
  },
  "homepage": "https://github.com/Athroniaeth/piighost",
  "repository": {
    "type": "git",
    "url": "https://github.com/Athroniaeth/piighost.git"
  },
  "support": "https://github.com/Athroniaeth/piighost/issues",
  "icon": "icon.png",
  "server": {
    "type": "uv",
    "entry_point": "src/server.py",
    "mcp_config": {
      "command": "uv",
      "args": ["run", "--directory", "${__dirname}", "src/server.py"],
      "env": {
        "PIIGHOST_VAULT_DIR": "${user_config.vault_dir}",
        "MISTRAL_API_KEY": "${user_config.mistral_api_key}"
      }
    }
  },
  "compatibility": {
    "platforms": ["darwin", "linux", "win32"],
    "runtimes": {
      "python": ">=3.10"
    }
  },
  "user_config": {
    "vault_dir": {
      "type": "directory",
      "title": "Vault Directory",
      "description": "Location of your PII vault (persisted across sessions)",
      "required": true,
      "default": "${HOME}/.piighost/vault"
    },
    "mistral_api_key": {
      "type": "string",
      "title": "Mistral API Key (optional)",
      "description": "Required only if embedder backend is 'mistral'. Leave blank to use local embeddings.",
      "sensitive": true,
      "required": false
    }
  },
  "keywords": ["pii", "anonymization", "gdpr", "privacy", "vault", "rag", "retrieval", "indexing"],
  "license": "MIT"
}
```

- [ ] **Step 2: Create `bundles/full/pyproject.toml`**

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

- [ ] **Step 3: Create `bundles/full/src/server.py` (identical to core's)**

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

- [ ] **Step 4: Create placeholder `bundles/full/icon.png`**

```bash
cd C:/Users/NMarchitecte/Documents/piighost
python -c "
from pathlib import Path
import struct, zlib

def make_png(width, height, rgb, out_path):
    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xFFFFFFFF)
    ihdr = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    row = bytes([0]) + bytes(rgb * width)
    raw = row * height
    idat = zlib.compress(raw, 9)
    png = b'\\x89PNG\\r\\n\\x1a\\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', idat) + chunk(b'IEND', b'')
    Path(out_path).write_bytes(png)

# Use a slightly different color for 'full' to distinguish visually
make_png(256, 256, [0x1f, 0x6f, 0x5c], 'bundles/full/icon.png')
print('full icon written')
"
```

- [ ] **Step 5: Commit**

```bash
git add bundles/full/
git commit -m "feat(mcpb): piighost-full bundle skeleton (indexing + query tools)"
```

---

### Task 4: Build script with version templating

**Files:**
- Create: `scripts/build_mcpb.py`
- Create: `tests/unit/test_build_mcpb.py`

- [ ] **Step 1: Write failing test**

Create `tests/unit/test_build_mcpb.py`:

```python
import json
import zipfile
from pathlib import Path
import tomllib
import sys


ROOT = Path(__file__).resolve().parents[2]


def _root_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
    return data["project"]["version"]


def test_build_script_importable():
    sys.path.insert(0, str(ROOT / "scripts"))
    import build_mcpb  # noqa: F401


def test_build_core_produces_valid_zip(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / "scripts"))
    import build_mcpb

    # Redirect DIST to tmp_path so we don't pollute dist/
    monkeypatch.setattr(build_mcpb, "DIST", tmp_path)

    version = _root_version()
    out = build_mcpb.build("core", version)
    assert out.exists()

    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
        assert "manifest.json" in names
        assert "pyproject.toml" in names
        assert "src/server.py" in names
        assert "icon.png" in names

        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["name"] == "piighost-core"
        assert manifest["version"] == version

        pyproject_text = zf.read("pyproject.toml").decode("utf-8")
        assert f'piighost[mcp]=={version}' in pyproject_text


def test_build_full_produces_valid_zip(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / "scripts"))
    import build_mcpb

    monkeypatch.setattr(build_mcpb, "DIST", tmp_path)

    version = _root_version()
    out = build_mcpb.build("full", version)
    assert out.exists()

    with zipfile.ZipFile(out) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["name"] == "piighost-full"
        assert manifest["version"] == version

        pyproject_text = zf.read("pyproject.toml").decode("utf-8")
        assert f'piighost[mcp,index,gliner2]=={version}' in pyproject_text


def test_build_both_variants(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / "scripts"))
    import build_mcpb

    monkeypatch.setattr(build_mcpb, "DIST", tmp_path)
    version = _root_version()

    core_out = build_mcpb.build("core", version)
    full_out = build_mcpb.build("full", version)

    assert core_out.exists()
    assert full_out.exists()
    assert core_out != full_out
```

- [ ] **Step 2: Run test to verify failure**

```bash
cd C:/Users/NMarchitecte/Documents/piighost
python -m pytest tests/unit/test_build_mcpb.py -v -p no:randomly
```

Expected: `ModuleNotFoundError: No module named 'build_mcpb'`.

- [ ] **Step 3: Create `scripts/build_mcpb.py`**

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

- [ ] **Step 4: Run test to verify pass**

```bash
python -m pytest tests/unit/test_build_mcpb.py -v -p no:randomly
```

Expected: 4 PASSED.

- [ ] **Step 5: Run script manually**

```bash
cd C:/Users/NMarchitecte/Documents/piighost
python scripts/build_mcpb.py
ls dist/mcpb/
```

Expected output:
```
Built: .../dist/mcpb/piighost-core.mcpb
Built: .../dist/mcpb/piighost-full.mcpb
piighost-core.mcpb  piighost-full.mcpb
```

- [ ] **Step 6: Add `dist/mcpb/` to `.gitignore` if not already**

```bash
grep -q '^dist/' .gitignore || echo 'dist/' >> .gitignore
```

- [ ] **Step 7: Run full suite (no regressions)**

```bash
python -m pytest tests/unit/ tests/e2e/ -q -p no:randomly 2>&1 | tail -5
```

Expected: all passing.

- [ ] **Step 8: Commit**

```bash
git add scripts/build_mcpb.py tests/unit/test_build_mcpb.py .gitignore
git commit -m "feat(mcpb): build script with version templating + zip creation"
```

---

### Task 5: CI workflow — validate + build + upload on tag push

**Files:**
- Create: `.github/workflows/mcpb.yml`

- [ ] **Step 1: Create the workflow**

Create `.github/workflows/mcpb.yml`:

```yaml
name: Build MCPB bundles

on:
  push:
    tags: ["[0-9]+.[0-9]+.[0-9]+"]
  pull_request:
    paths:
      - "bundles/**"
      - "scripts/build_mcpb.py"
      - ".github/workflows/mcpb.yml"
  workflow_dispatch:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Set up Node (for mcpb CLI)
        uses: actions/setup-node@v4
        with:
          node-version: "20"

      - name: Install mcpb CLI
        run: npm install -g @anthropic-ai/mcpb

      - name: Validate core manifest
        run: mcpb validate bundles/core

      - name: Validate full manifest
        run: mcpb validate bundles/full

      - uses: astral-sh/setup-uv@v5

      - name: Build bundles
        run: uv run python scripts/build_mcpb.py

      - name: List build outputs
        run: ls -la dist/mcpb/

      - name: Upload bundles as workflow artifacts
        uses: actions/upload-artifact@v4
        with:
          name: mcpb-bundles
          path: dist/mcpb/*.mcpb

      - name: Upload to GitHub Release
        if: startsWith(github.ref, 'refs/tags/')
        uses: softprops/action-gh-release@v2
        with:
          files: |
            dist/mcpb/piighost-core.mcpb
            dist/mcpb/piighost-full.mcpb
```

- [ ] **Step 2: Verify the YAML is valid**

```bash
cd C:/Users/NMarchitecte/Documents/piighost
python -c "import yaml; yaml.safe_load(open('.github/workflows/mcpb.yml'))"
```

Expected: no errors. If PyYAML is not installed:

```bash
pip install pyyaml
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/mcpb.yml
git commit -m "ci(mcpb): validate + build + upload bundles on tag push"
```

---

### Task 6: README + install docs

**Files:**
- Modify: `README.md`
- Create: `docs/mcpb-install.md`

- [ ] **Step 1: Read current README to find the "Installation" section**

```bash
cd C:/Users/NMarchitecte/Documents/piighost
grep -n "Installation" README.md | head -5
```

- [ ] **Step 2: Append MCPB install subsection to README.md**

Find the existing "Installation" section in `README.md`. Append this subsection immediately after the existing installation instructions (after the last line of the current "Installation" section):

```markdown
### Claude Desktop (MCPB bundle)

One-click install for Claude Desktop users:

1. Download the latest bundle from the [GitHub Releases page](https://github.com/Athroniaeth/piighost/releases/latest):
   - **`piighost-core.mcpb`** — anonymization + vault tools only (~50 MB first-run install).
   - **`piighost-full.mcpb`** — includes document indexing and hybrid retrieval (~1.5 GB first-run install, heavy deps: torch, sentence-transformers).
2. Double-click the file — Claude Desktop will prompt for install confirmation and ask you to choose a vault directory.
3. On first tool call, UV installs the required Python packages. Subsequent launches are instant (packages are cached).
4. See [docs/mcpb-install.md](docs/mcpb-install.md) for troubleshooting.
```

- [ ] **Step 3: Create `docs/mcpb-install.md`**

```markdown
# Installing piighost in Claude Desktop (MCPB)

piighost ships two MCPB bundles. Both install the MCP server into Claude Desktop with a single click and use UV to manage Python dependencies on first run.

## Which bundle do I want?

| Use case | Bundle | First-run size |
|----------|--------|----------------|
| Anonymize / rehydrate text, manage the PII vault | `piighost-core.mcpb` | ~50 MB |
| All of the above PLUS index documents and run hybrid retrieval queries | `piighost-full.mcpb` | ~1.5 GB |

The two bundles can coexist — but if you install both, Claude Desktop will show the tools from whichever bundle you enable.

## Installing

1. Download the `.mcpb` file from the [latest release](https://github.com/Athroniaeth/piighost/releases/latest).
2. Double-click the file. Claude Desktop opens a confirmation dialog showing the tools, required configuration, and permissions.
3. Configure the **Vault Directory** (required). Default: `~/.piighost/vault`. Changing it later is done via Claude Desktop → Settings → Extensions → piighost → Configure.
4. For the full bundle only: optionally set your Mistral API key if you plan to use the Mistral embedder.
5. Click **Install**. Claude Desktop unpacks the bundle. At this point nothing is downloaded yet — UV runs lazily on first tool call.
6. Open a new conversation. The first time you invoke a piighost tool, Claude Desktop starts the MCP server, which triggers `uv run src/server.py`. UV creates a venv and installs the pinned `piighost[...]` extras.
   - Core: ~30 seconds.
   - Full: 3–10 minutes depending on your connection (downloads torch, transformers, lancedb, sentence-transformers).
7. Subsequent conversations reuse the cached environment — tool calls start in under a second.

## Troubleshooting

### UV not found

MCPB requires UV to be installed on the user's machine. Install via:

- **macOS/Linux**: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Windows**: `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`
- Or `pip install uv`.

Restart Claude Desktop after installing UV.

### Python version too old

piighost requires Python ≥ 3.10. UV picks the first Python on the user's `PATH` matching `requires-python`. If you see errors about Python version, install Python 3.10+ via `uv python install 3.12`.

### First-run install hangs

The full bundle's first-run install downloads large wheels. If your connection is slow, give it time. To monitor progress, open Claude Desktop's extension log (macOS: `~/Library/Logs/Claude/mcp-server-piighost.log`).

### Behind a corporate proxy

Set the `HTTPS_PROXY` environment variable in Claude Desktop's extension configuration — MCPB passes it through to UV.

### Manual install fallback

If one-click install fails:

1. Unzip the `.mcpb` file into `~/.config/Claude/extensions/piighost/` (Linux/macOS) or `%APPDATA%\Claude\extensions\piighost\` (Windows).
2. Restart Claude Desktop.

## Uninstalling

Claude Desktop → Settings → Extensions → piighost → Remove. The UV cache persists at `~/.local/share/uv/` — clear it manually if you want to reclaim disk space.
```

- [ ] **Step 4: Verify markdown renders**

```bash
cd C:/Users/NMarchitecte/Documents/piighost
# Just confirm the files exist and have the right headers
head -5 README.md
head -5 docs/mcpb-install.md
```

- [ ] **Step 5: Commit**

```bash
git add README.md docs/mcpb-install.md
git commit -m "docs(mcpb): README install section + detailed walkthrough"
```

---

## Self-Review

### Spec coverage

| Spec requirement | Task |
|------------------|------|
| Two `.mcpb` artifacts (core + full) via UV-based bundles | Tasks 2 + 3 |
| Core exposes 8 tools, full exposes 10 | Task 1 (gating) |
| One code change in `piighost.mcp.server` for tool gating | Task 1 |
| Manifests per MCPB 0.4 spec | Tasks 2 + 3 |
| User config: `vault_dir` (both), `mistral_api_key` (full only) | Tasks 2 + 3 |
| Shared entry point (`src/server.py` identical) | Tasks 2 + 3 |
| Build script with version templating | Task 4 |
| CI workflow on tag push | Task 5 |
| GitHub Release asset upload | Task 5 |
| README + install docs | Task 6 |
| Unit tests: gating + build script | Tasks 1 + 4 |
| `mcpb validate` in CI | Task 5 |

### Placeholder scan

- No "TBD" / "TODO" markers.
- All code blocks complete with exact content.
- Commands have expected output noted.
- The PNG generation uses a Python one-liner — real bytes, not a placeholder.

### Type consistency

- `build(variant: str, version: str) -> Path` signature consistent between Task 4's definition and Task 5's usage (CI calls via `python scripts/build_mcpb.py` not the function directly — no mismatch).
- Manifest field names (`version`, `name`, `user_config`, etc.) consistent across Tasks 2, 3, 4.
- Tool names (`index_path`, `query`) consistent across Task 1 (gating) and test assertions.
- File paths (`bundles/core/...`, `bundles/full/...`, `scripts/build_mcpb.py`, `dist/mcpb/...`) match across all tasks.

All consistency checks pass.
