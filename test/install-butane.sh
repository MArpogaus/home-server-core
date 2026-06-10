#!/usr/bin/env bash
set -euo pipefail
# Install Butane for Ignition config generation (FCOS/SecureBlue)
# Usage: ./install-butane.sh

BUTANE_URL="https://github.com/coreos/butane/releases/download/v0.28.0/butane-x86_64-unknown-linux-gnu"
LOCAL_BIN="${HOME}/.local/bin"

mkdir -p "${LOCAL_BIN}"

echo "Downloading Butane..."
curl -fsSL "${BUTANE_URL}" -o "${LOCAL_BIN}/butane"
chmod +x "${LOCAL_BIN}/butane"

echo "Installed: ${LOCAL_BIN}/butane"
"${LOCAL_BIN}/butane" --version
