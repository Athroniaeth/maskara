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

piighost requires Python >= 3.10. UV picks the first Python on the user's `PATH` matching `requires-python`. If you see errors about Python version, install Python 3.10+ via `uv python install 3.12`.

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
