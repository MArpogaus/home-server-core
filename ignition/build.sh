#!/bin/bash
# Renders the Ignition config for the real hardware and writes it to a disk or
# an ISO. Run it on a machine that has butane in PATH and podman for the
# installer image.
#
#   ./build.sh ign                      only render config.ign
#   ./build.sh install /dev/sdX         install Fedora CoreOS onto that disk
#   ./build.sh iso <live.iso> /dev/sdX  write an unattended installer ISO
#
# <live.iso> is the stock Fedora CoreOS live image. /dev/sdX is the disk of the
# machine that will boot the ISO, not a disk of this one.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE="${HERE}/config.bu.template"
BUTANE_CONFIG="${HERE}/config.bu"
IGNITION="${HERE}/config.ign"
INSTALLER_IMAGE="quay.io/coreos/coreos-installer:release"

usage() { echo "usage: $0 [ign | install /dev/sdX | iso <live.iso> /dev/sdX]"; exit 1; }

# The arguments are read first. Rendering costs a password prompt, and a
# missing ISO must not be found out by the installer container.
MODE="${1:-ign}"
case "${MODE}" in
ign) ;;
install)
	DEVICE="${2:-}"; [ -n "${DEVICE}" ] || usage
	[ -b "${DEVICE}" ] || { echo "ERROR: ${DEVICE} is not a block device"; exit 1; }
	;;
iso)
	SRC_ISO="${2:-}"; DEVICE="${3:-}"
	[ -n "${SRC_ISO}" ] && [ -n "${DEVICE}" ] || usage
	[ -f "${SRC_ISO}" ] || {
		echo "ERROR: no such file: ${SRC_ISO}"
		echo "       Fetch the live ISO into this directory first:"
		echo "       podman run --rm -v \"${HERE}\":/data:z -w /data \\"
		echo "           ${INSTALLER_IMAGE} download -s stable -p metal -f iso"
		exit 1
	}
	;;
*) usage ;;
esac

command -v butane >/dev/null || { echo "ERROR: butane not in PATH"; exit 1; }

# The YubiKey is the only key that may log in. Override to use another.
SSH_PUBLIC_KEY="${SSH_PUBLIC_KEY:-}"
if [ -z "${SSH_PUBLIC_KEY}" ]; then
	# Take the smartcard key from the agent: it is the one with a cardno.
	SSH_PUBLIC_KEY="$(ssh-add -L 2>/dev/null | grep -m1 'cardno:' || true)"
	[ -n "${SSH_PUBLIC_KEY}" ] || {
		echo "ERROR: no smartcard key in the agent. Plug in the YubiKey, or"
		echo "       set SSH_PUBLIC_KEY to the key you want to authorise."
		exit 1
	}
fi
echo "Authorising: ${SSH_PUBLIC_KEY%% *} ...${SSH_PUBLIC_KEY##* }"

# Console password, for physical recovery only. SSH refuses passwords either
# way, through /etc/ssh/sshd_config.d/10-no-passwords.conf.
if [ -z "${PASSWORD_HASH:-}" ]; then
	command -v mkpasswd >/dev/null || { echo "ERROR: mkpasswd not found; set PASSWORD_HASH"; exit 1; }
	echo "Console password for the 'core' user (physical recovery):"
	PASSWORD_HASH="$(mkpasswd --method=yescrypt)"
fi

export SSH_PUBLIC_KEY PASSWORD_HASH
# SC2016: envsubst wants the literal names, so the quotes must stay single.
# shellcheck disable=SC2016
envsubst '${SSH_PUBLIC_KEY} ${PASSWORD_HASH}' < "${TEMPLATE}" > "${BUTANE_CONFIG}"
butane --pretty --strict "${BUTANE_CONFIG}" > "${IGNITION}"
echo "Wrote ${IGNITION}"

case "${MODE}" in
install)
	echo "CAUTION: this erases ${DEVICE}."
	read -rp "Type the device again to confirm: " confirm
	[ "${confirm}" = "${DEVICE}" ] || { echo "Aborted."; exit 1; }
	sudo podman run --pull=always --privileged --rm \
		-v /dev:/dev -v /run/udev:/run/udev -v "${HERE}":/data -w /data \
		"${INSTALLER_IMAGE}" \
		install "${DEVICE}" -i config.ign
	;;
iso)
	SRC_DIR="$(cd "$(dirname "${SRC_ISO}")" && pwd)"
	# No privileges and no /dev here: this only rewrites a file.
	podman run --pull=always --rm \
		-v "${HERE}":/data:z -v "${SRC_DIR}":/iso:z -w /data \
		"${INSTALLER_IMAGE}" \
		iso customize --force --dest-ignition config.ign \
		--dest-device "${DEVICE}" \
		-o t630.iso "/iso/$(basename "${SRC_ISO}")"
	echo "Wrote ${HERE}/t630.iso"
	echo "Booting it installs onto ${DEVICE} and reboots, with no prompt."
	;;
esac
