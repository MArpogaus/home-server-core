#!/bin/bash
# Incremental `btrfs send` of the newest snapshot of every service to one
# backup target. The target is named by the instance: btrfs-backup@<name>.
# Its settings come from /etc/btrfs-backup/<name>.conf.
set -euo pipefail

TARGET="${1:?target name not given}"
# shellcheck source=/dev/null
. "/etc/btrfs-backup/${TARGET}.conf"

SNAP_DIR="${BTRFS_SNAPSHOT_DIR:-/var/services/snapshots}"
DEST="${BACKUP_ROOT:-/var/backup}/${TARGET}"
RETENTION_DAYS="${RETENTION_DAYS:-90}"
# The unit requires the mount, and crypttab opens the container when the disk
# appears, so by the time this runs the target is there. An absent target fails
# the unit instead, which is what puts it in the journal.

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
			btrfs send -q -p "${src}${parent}" "${src}${latest}" | btrfs receive "${DEST}/${svc}"
		else
			btrfs send -q "${src}${latest}" | btrfs receive "${DEST}/${svc}"
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

# The staleness alert keys on this line. It is only reached when the target
# was mounted and every service was processed.
echo "btrfs-backup: run complete"
