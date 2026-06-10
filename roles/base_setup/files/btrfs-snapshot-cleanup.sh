#!/bin/bash
set -euo pipefail

VOLUME_NAME="$1"
SOURCE="/var/services/${VOLUME_NAME}"
SNAPSHOT_DIR="/var/services/snapshots/${VOLUME_NAME}"
RETENTION_DAYS="${BTRFS_SNAPSHOT_RETENTION_DAYS:-30}"

# Create snapshot directory if it doesn't exist
mkdir -p "${SNAPSHOT_DIR}"

# Create timestamped read-only snapshot
SNAPSHOT_NAME="$(date +%Y-%m-%d)"
SNAPSHOT_PATH="${SNAPSHOT_DIR}/${SNAPSHOT_NAME}"

if [ -d "${SNAPSHOT_PATH}" ]; then
    echo "Snapshot ${SNAPSHOT_PATH} already exists today, skipping."
    exit 0
fi

btrfs subvolume snapshot -r "${SOURCE}" "${SNAPSHOT_PATH}"
echo "Created snapshot: ${SNAPSHOT_PATH}"

# Delete old snapshots
find "${SNAPSHOT_DIR}" -maxdepth 1 -type d -mtime +"${RETENTION_DAYS}" -exec rm -rf {} \;
echo "Cleaned snapshots older than ${RETENTION_DAYS} days"
