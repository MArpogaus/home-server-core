#!/bin/bash
# Renders the Ignition config for the real hardware and writes it to a disk or
# an ISO. It needs podman, which runs butane and the installer.
#
#   ./build.sh ign                      only render config.ign
#   ./build.sh install /dev/sdX         install Fedora CoreOS onto that disk
#   ./build.sh iso <live.iso> /dev/sdX  write an unattended installer ISO
#
# <live.iso> is the stock Fedora CoreOS live image. /dev/sdX is the disk of the
# machine that will boot the ISO, not a disk of this one.
#
# PLATFORM_BU names an optional Butane fragment that the deployment provides,
# such as a rebase to a derivative image. It is merged into the config.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE="${HERE}/config.bu.template"
BUTANE_CONFIG="${HERE}/config.bu"
IGNITION="${HERE}/config.ign"
INSTALLER_IMAGE="quay.io/coreos/coreos-installer:release"

usage() { echo "usage: $0 [ign | install /dev/sdX | iso <live.iso> /dev/sdX]"; exit 1; }

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

BUTANE=(podman run --rm -i --security-opt label=disable
	-v "${HERE}":/pwd -w /pwd quay.io/coreos/butane:release)

SSH_PUBLIC_KEY="${SSH_PUBLIC_KEY:-}"
if [ -z "${SSH_PUBLIC_KEY}" ]; then
	SSH_PUBLIC_KEY="$(ssh-add -L 2>/dev/null | grep -m1 'cardno:' || true)"
	[ -n "${SSH_PUBLIC_KEY}" ] || {
		echo "ERROR: no smartcard key in the agent. Plug in the YubiKey, or"
		echo "       set SSH_PUBLIC_KEY to the key you want to authorise."
		exit 1
	}
fi
echo "Authorising: ${SSH_PUBLIC_KEY%% *} ...${SSH_PUBLIC_KEY##* }"

# Console password, for physical recovery only. PASSWORD_HASH=none sets none.
if [ -z "${PASSWORD_HASH:-}" ]; then
	command -v mkpasswd >/dev/null || { echo "ERROR: mkpasswd not found; set PASSWORD_HASH"; exit 1; }
	echo "Console password for the 'core' user (physical recovery):"
	PASSWORD_HASH="$(mkpasswd --method=yescrypt)"
fi

config="$(<"${TEMPLATE}")"
# shellcheck disable=SC2016  # the patterns are the literal placeholders
{
	config="${config//'${SSH_PUBLIC_KEY}'/"${SSH_PUBLIC_KEY}"}"
	config="${config//'${PASSWORD_HASH}'/"${PASSWORD_HASH}"}"
}
printf '%s\n' "${config}" > "${BUTANE_CONFIG}"
if [ "${PASSWORD_HASH}" = "none" ]; then
	sed -i '/password_hash:/d' "${BUTANE_CONFIG}"
fi
rm -f "${HERE}/platform.ign"
if [ -n "${PLATFORM_BU:-}" ]; then
	"${BUTANE[@]}" --strict < "${PLATFORM_BU}" > "${HERE}/platform.ign"
	printf 'ignition:\n  config:\n    merge:\n      - local: platform.ign\n' >> "${BUTANE_CONFIG}"
fi
(cd "${HERE}" && "${BUTANE[@]}" --pretty --strict --files-dir . config.bu) > "${IGNITION}"
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
	podman run --pull=always --rm \
		-v "${HERE}":/data:z -v "${SRC_DIR}":/iso:z -w /data \
		"${INSTALLER_IMAGE}" \
		iso customize --force --dest-ignition config.ign \
		--dest-device "${DEVICE}" \
		-o install.iso "/iso/$(basename "${SRC_ISO}")"
	echo "Wrote ${HERE}/install.iso"
	echo "Booting it installs onto ${DEVICE} and reboots, with no prompt."
	;;
esac
