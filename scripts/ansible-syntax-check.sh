#!/usr/bin/env bash
set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"

cd "$(dirname "$0")/.."

echo "▶ ansible-playbook --syntax-check -i inventory/hosts.ini site.yml"
ansible-playbook --syntax-check -i inventory/hosts.ini site.yml
