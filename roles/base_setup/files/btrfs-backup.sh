#!/bin/bash
# Incremental `btrfs send` of the newest snapshot of every service to a second
# Btrfs filesystem (USB disk). Skips silently when the target is not mounted.
set -euo pipefail

SNAP_DIR="${BTRFS_SNAPSHOT_DIR:-/var/services/snapshots}"
DEST="${BTRFS_BACKUP_DIR:?BTRFS_BACKUP_DIR not set}"
RETENTION_DAYS="${BTRFS_BACKUP_RETENTION_DAYS:-90}"

if ! mountpoint -q "${DEST}"; then
    echo "${DEST} is not mounted, skipping backup."
    exit 0
fi

CUTOFF="$(date -d "-${RETENTION_DAYS} days" +%Y-%m-%d)"

# Snapshot directory names only (YYYY-MM-DD), sorted oldest first.
snapshots() {
    find "$1" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' 2>/dev/null | sort
}

for src in "${SNAP_DIR}"/*/; do
    svc="$(basename "${src}")"
    mkdir -p "${DEST}/${svc}"

    latest="$(snapshots "${src}" | tail -n1)"
    [ -n "${latest}" ] || continue

    if [ -e "${DEST}/${svc}/${latest}" ]; then
        echo "${svc}/${latest} already backed up."
    else
        # Newest snapshot present on both sides is the incremental parent.
        parent="$(comm -12 <(snapshots "${src}") <(snapshots "${DEST}/${svc}") | tail -n1)"
        if [ -n "${parent}" ]; then
            btrfs send -q -p "${src}/${parent}" "${src}/${latest}" | btrfs receive "${DEST}/${svc}"
        else
            btrfs send -q "${src}/${latest}" | btrfs receive "${DEST}/${svc}"
        fi
        echo "Backed up ${svc}/${latest}"
    fi

    for snap in "${DEST}/${svc}"/????-??-??; do
        [ -d "${snap}" ] || continue
        if [[ "$(basename "${snap}")" < "${CUTOFF}" ]]; then
            btrfs subvolume delete "${snap}"
            echo "Deleted backup: ${snap}"
        fi
    done
done
