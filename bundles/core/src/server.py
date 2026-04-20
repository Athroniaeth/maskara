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
