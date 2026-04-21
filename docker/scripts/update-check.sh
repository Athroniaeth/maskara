#!/usr/bin/env bash
# piighost update notifier — compare installed digest to latest on GHCR,
# emit a notice if newer. Never mutates the stack.

set -euo pipefail

INTERVAL="${PIIGHOST_UPDATE_CHECK_INTERVAL:-86400}"
IMAGE="${PIIGHOST_IMAGE:-ghcr.io/jamon8888/hacienda-ghost}"
TAG="${PIIGHOST_TAG:-slim}"
DATA_DIR="${PIIGHOST_DATA_DIR:-/var/lib/piighost}"
OUT_FILE="$DATA_DIR/update-available.json"

mkdir -p "$DATA_DIR"

check_once() {
    latest_digest="$(
        IMAGE="$IMAGE" TAG="$TAG" python - <<'PY'
import os, sys
import httpx

image = os.environ["IMAGE"]
tag = os.environ["TAG"]
host, name = image.split("/", 1)
token = httpx.get(
    f"https://{host}/token",
    params={"service": host, "scope": f"repository:{name}:pull"},
    timeout=10,
).json().get("token", "")
headers = {
    "Accept": "application/vnd.oci.image.index.v1+json",
    "Authorization": f"Bearer {token}" if token else "",
}
r = httpx.get(
    f"https://{host}/v2/{name}/manifests/{tag}",
    headers=headers,
    timeout=10,
)
r.raise_for_status()
print(r.headers.get("Docker-Content-Digest", ""))
PY
    )"
    current_digest_file="$DATA_DIR/installed-digest"
    if [[ ! -f "$current_digest_file" ]]; then
        echo "$latest_digest" > "$current_digest_file"
        return 0
    fi
    installed="$(<"$current_digest_file")"
    if [[ "$latest_digest" != "$installed" ]]; then
        cat > "$OUT_FILE" <<EOF
{
  "image": "$IMAGE",
  "tag": "$TAG",
  "installed": "$installed",
  "latest": "$latest_digest",
  "checked_at": "$(date -u +%FT%TZ)"
}
EOF
        echo "[piighost] update available: $TAG $installed -> $latest_digest" >&2
    fi
}

while true; do
    check_once || echo "[piighost] update check failed (will retry)" >&2
    sleep "$INTERVAL"
done
