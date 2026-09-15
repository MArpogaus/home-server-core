#!/bin/bash
# Check if rpm-ostree has a staged deployment and reboot if so.
set -euo pipefail

if rpm-ostree status --json | grep -q '"staged":true'; then
  echo "Staged deployment detected. Rebooting in 60 seconds..."
  /usr/sbin/shutdown -r +1 "Auto-reboot: staged rpm-ostree deployment"
else
  echo "No staged deployment. Skipping reboot."
fi
