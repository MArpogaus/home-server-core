#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KEY_NAME="${1:-test_key}"
KEY_DIR="${SCRIPT_DIR}"
KEY_PATH="${KEY_DIR}/${KEY_NAME}"
KEY_PUB_PATH="${KEY_PATH}.pub"
TEMPLATE="${SCRIPT_DIR}/config.bu.template"
OUTPUT="${SCRIPT_DIR}/config.bu"
IGNITION="${SCRIPT_DIR}/config.ign"

if [ ! -f "${TEMPLATE}" ]; then
    echo "Error: ${TEMPLATE} not found"
    exit 1
fi

# Generate SSH key pair if not exists
if [ ! -f "${KEY_PATH}" ]; then
    ssh-keygen -t ed25519 -f "${KEY_PATH}" -N "" -C "ansible-test" >/dev/null 2>&1
    echo "Generated SSH key: ${KEY_PATH}"
else
    echo "Using existing SSH key: ${KEY_PATH}"
fi

SSH_PUBLIC_KEY=$(cat "${KEY_PUB_PATH}")

# Generate password hash (interactive prompt or default)
if [ -t 0 ]; then
    # Running interactively
    PASSWORD="${PASSWORD:-}"
    if [ -z "${PASSWORD}" ]; then
        read -rsp "Enter password for core user (default: test): " PASSWORD_INPUT
        echo
        PASSWORD="${PASSWORD_INPUT:-test}"
    fi
else
    PASSWORD="${PASSWORD:-test}"
fi

PASSWORD_HASH=$(mkpasswd --method=yescrypt "${PASSWORD}" 2>/dev/null || \
                python3 -c "import crypt; print(crypt.crypt('${PASSWORD}', crypt.gensalt(crypt.meth_yescrypt)))" 2>/dev/null || \
                echo "\$y\$j9T\$\$placeholder")

# Fill template
sed -e "s|\${SSH_PUBLIC_KEY}|${SSH_PUBLIC_KEY}|g" \
    -e "s|\${PASSWORD_HASH}|${PASSWORD_HASH}|g" \
    "${TEMPLATE}" > "${OUTPUT}"

echo "Generated config.bu"

# Convert to Ignition if butane is available
if command -v butane &>/dev/null; then
    butane "${OUTPUT}" -o "${IGNITION}"
    echo "Generated config.ign"
else
    echo "butane not found - skipping Ignition generation"
fi
