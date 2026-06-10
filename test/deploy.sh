#!/usr/bin/env bash
#
# Deploy ansible-base gegen Fedora CoreOS VM
#
# usage: ./test/deploy.sh
#

set -euo pipefail

TEST_DIR="$(cd "$(dirname "$0")" && pwd)"
ANSIBLE_DIR="$TEST_DIR/../ansible-base"
SSH_KEY="$TEST_DIR/coreos_key"

# ==========================
RED='\033[0;31m'; GREEN='\033[0;32m'; BLUE='\033[0;34m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[+]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[-]${NC} $*"; exit 1; }

# ==========================
# Voraussetzungen
# ==========================
[ ! -d "$ANSIBLE_DIR" ] && err "ansible-base nicht gefunden: $ANSIBLE_DIR"
[ ! -f "$SSH_KEY" ] && err "SSH-Key nicht gefunden: $SSH_KEY"

export PATH="$HOME/.local/bin:$PATH"
command -v ansible-playbook &>/dev/null || err "ansible-playbook nicht gefunden"

# ==========================
# SSH-Host konfigurieren
# ==========================
SSH_CONFIG="${HOME}/.ssh/config"
if ! grep -q "Host coreos" "$SSH_CONFIG" 2>/dev/null; then
  cat >> "$SSH_CONFIG" << EOF

Host coreos
  HostName 127.0.0.1
  Port 2222
  User core
  IdentityFile $SSH_KEY
  StrictHostKeyChecking no
  UserKnownHostsFile /dev/null
  LogLevel ERROR
EOF
  chmod 600 "$SSH_CONFIG"
fi

# ==========================
# VM erreichbar?
# ==========================
log "Prüfe SSH-Verbindung zur VM..."
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -p 2222 core@localhost "echo ok" || \
  err "VM nicht erreichbar. Starte zuerst: ./test/start_vm.sh"

# ==========================
# Deployment
# ==========================
echo ""
echo "=========================================="
echo "  Deploy ansible-base → Fedora CoreOS"
echo "=========================================="
echo ""

cd "$ANSIBLE_DIR"

ansible-playbook \
  -i "coreos," \
  -e "ansible_ssh_private_key_file=$SSH_KEY" \
  -e "ansible_user=core" \
  --private-key "$SSH_KEY" \
  site.yml

echo ""
echo "=========================================="
echo "  Deployment abgeschlossen"
echo "=========================================="
echo ""
echo "  Nächstes auf der VM:"
echo "    ssh coreos"
echo "    podman info"
echo "    systemctl --user list-unit-files | grep nextcloud"
echo ""
