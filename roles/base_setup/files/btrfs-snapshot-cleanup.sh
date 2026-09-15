#!/bin/bash
# Daily read-only Btrfs snapshot of one service subvolume, plus retention by snapshot date.
set -euo pipefail

VOLUME_NAME="$1"
BASE_DIR="${BTRFS_SNAPSHOT_DIR:-/var/services/snapshots}"
SERVICES_DIR="${BTRFS_SERVICES_DIR:-/var/services}"
RETENTION_DAYS="${BTRFS_SNAPSHOT_RETENTION_DAYS:-30}"
SOURCE="${SERVICES_DIR}/${VOLUME_NAME}"
SNAPSHOT_DIR="${BASE_DIR}/${VOLUME_NAME}"

mkdir -p "${SNAPSHOT_DIR}"

TODAY="$(date +%Y-%m-%d)"
if [ -d "${SNAPSHOT_DIR}/${TODAY}" ]; then
    echo "Snapshot ${SNAPSHOT_DIR}/${TODAY} already exists, skipping."
else
    btrfs subvolume snapshot -r "${SOURCE}" "${SNAPSHOT_DIR}/${TODAY}"
    echo "Created snapshot: ${SNAPSHOT_DIR}/${TODAY}"
fi

# Snapshots are read-only subvolumes: rm -rf fails on them, and mtime is the
# source's mtime, not the creation date. Compare the date in the name instead.
CUTOFF="$(date -d "-${RETENTION_DAYS} days" +%Y-%m-%d)"
for snap in "${SNAPSHOT_DIR}"/????-??-??; do
    [ -d "${snap}" ] || continue
    if [[ "$(basename "${snap}")" < "${CUTOFF}" ]]; then
        btrfs subvolume delete "${snap}"
        echo "Deleted snapshot: ${snap}"
    fi
done
