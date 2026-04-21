#!/usr/bin/env bash
# piighost container entrypoint — dispatches to the requested role.
#
# Usage:  entrypoint.sh <role> [args...]
#
# Roles:
#   mcp       Run the MCP server (FastMCP, streamable HTTP)
#   daemon    Run the long-running anonymization daemon
#   backup    Run a one-shot backup (invoked by the backup sidecar cron)
#   notify    Run the update-availability check (one-shot)
#   cli       Drop into the piighost CLI with remaining args
#
# Env:
#   PIIGHOST_DRY_RUN=1   Echo the command that would run, exit 0 without exec
#   PIIGHOST_DATA_DIR    Data directory (default: /var/lib/piighost)
#   PIIGHOST_VAULT_KEY_FILE  Path to vault-key secret file (default: /run/secrets/piighost_vault_key)

set -euo pipefail

role="${1:-mcp}"
shift || true

case "$role" in
    mcp)
        cmd=(python -m piighost.mcp.server --transport http --host 0.0.0.0 --port 8765 "$@")
        ;;
    daemon)
        cmd=(python -m piighost.daemon "$@")
        ;;
    backup)
        cmd=(/docker/scripts/backup.sh "$@")
        ;;
    notify)
        cmd=(/docker/scripts/update-check.sh "$@")
        ;;
    cli)
        cmd=(python -m piighost.cli.main "$@")
        ;;
    *)
        echo "entrypoint.sh: unknown role '$role'" >&2
        echo "valid roles: mcp | daemon | backup | notify | cli" >&2
        exit 64
        ;;
esac

# Load vault key from secret file if present (never via env var)
if [[ -f "${PIIGHOST_VAULT_KEY_FILE:-/run/secrets/piighost_vault_key}" ]]; then
    PIIGHOST_VAULT_KEY="$(<"${PIIGHOST_VAULT_KEY_FILE:-/run/secrets/piighost_vault_key}")"
    export PIIGHOST_VAULT_KEY
fi

if [[ "${PIIGHOST_DRY_RUN:-0}" == "1" ]]; then
    printf 'dry-run: role=%s cmd=%s\n' "$role" "${cmd[*]}"
    exit 0
fi

exec "${cmd[@]}"
