#!/usr/bin/env bash
# piighost vault restore — decrypt an age-encrypted tar archive into
# $PIIGHOST_DATA_DIR. Destructive: wipes the target directory first.

set -euo pipefail

archive="${1:?usage: restore.sh <archive.tar.age>}"
DATA_DIR="${PIIGHOST_DATA_DIR:-/var/lib/piighost}"
KEY_FILE="${PIIGHOST_AGE_KEY_FILE:-/run/secrets/piighost_age_key}"

if [[ ! -r "$archive" ]]; then
    echo "restore.sh: cannot read archive: $archive" >&2
    exit 1
fi
if [[ ! -r "$KEY_FILE" ]]; then
    echo "restore.sh: cannot read age key file: $KEY_FILE" >&2
    exit 1
fi

echo "restore.sh: wiping $DATA_DIR and restoring from $archive"
mkdir -p "$DATA_DIR"
find "$DATA_DIR" -mindepth 1 -delete

age -d -i "$KEY_FILE" "$archive" | tar -C "$DATA_DIR" -xf -

echo "restore.sh: restored to $DATA_DIR"
