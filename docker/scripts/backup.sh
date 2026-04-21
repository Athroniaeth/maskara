#!/usr/bin/env bash
# piighost vault backup — age-encrypted tar of $PIIGHOST_DATA_DIR to
# $PIIGHOST_BACKUP_DIR. Called by the backup sidecar on the configured
# cron schedule.

set -euo pipefail

DATA_DIR="${PIIGHOST_DATA_DIR:-/var/lib/piighost}"
BACKUP_DIR="${PIIGHOST_BACKUP_DIR:-/backups}"
RECIPIENT_FILE="${PIIGHOST_AGE_RECIPIENT_FILE:-/run/secrets/piighost_age_recipient}"
TIMESTAMP="${PIIGHOST_BACKUP_TIMESTAMP:-$(date -u +%Y-%m-%d)}"
RETENTION_DAILY="${PIIGHOST_BACKUP_RETENTION_DAILY:-7}"
RETENTION_WEEKLY="${PIIGHOST_BACKUP_RETENTION_WEEKLY:-4}"

if [[ ! -r "$RECIPIENT_FILE" ]]; then
    echo "backup.sh: cannot read age recipient file: $RECIPIENT_FILE" >&2
    exit 1
fi

recipient="$(tr -d '[:space:]' < "$RECIPIENT_FILE")"
if [[ -z "$recipient" ]]; then
    echo "backup.sh: recipient file is empty" >&2
    exit 1
fi

mkdir -p "$BACKUP_DIR"
archive="$BACKUP_DIR/piighost-$TIMESTAMP.tar.age"

# Stream: tar → age → file. No plaintext on disk.
tar -C "$DATA_DIR" -cf - . | age -r "$recipient" -o "$archive"

# Retention: keep N most-recent dailies + M most-recent weeklies (date-named)
cd "$BACKUP_DIR"
ls -1t piighost-*.tar.age 2>/dev/null | tail -n +$((RETENTION_DAILY + 1)) | \
    while read -r old; do
        if [[ "$(date -d "${old#piighost-}" +%u 2>/dev/null || echo 0)" != "7" ]]; then
            rm -f "$old"
        fi
    done

ls -1t piighost-*.tar.age 2>/dev/null | \
    awk 'NR > '"$((RETENTION_DAILY + RETENTION_WEEKLY))"'' | \
    xargs -r rm -f

echo "backup.sh: wrote $archive"
