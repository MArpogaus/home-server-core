#!/usr/bin/env python3
"""
Start Fedora CoreOS VM (KVM, headless, Port-Forwarding SSH)
Rebase to SecureBlue, inject GHCR signing keys, SSH-Key.

Usage: python3 start_vm.py

No dependencies — stdlib only.
"""

import json
import os
import shutil
import subprocess
import sys
import urllib.request

# ==========================
# Config
# ==========================
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
FCOS_VERSION = "44.20260510.3.1"
DISK_FILE = os.path.join(TEST_DIR, "fcos.qcow2")
DISK_SIZE = "20G"  # grown after initial download
IGNITION_FILE = os.path.join(TEST_DIR, "config.ign")
BUTANE_CONFIG = os.path.join(TEST_DIR, "config.bu")
SSH_KEY = os.path.join(TEST_DIR, "coreos_key")
SSH_PORT = 2222

# ==========================
# Color helpers
# ==========================
GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[1;33m"
NC = "\033[0m"

def ok(msg):  print(f"{GREEN}[+] {msg}{NC}")
def warn(msg): print(f"{YELLOW}[!] {msg}{NC}")
def fail(msg):
    print(f"{RED}[-] {msg}{NC}")
    sys.exit(1)

# ==========================
# Prerequisites
# ==========================
ok("Prüfe Voraussetzungen...")

if not os.path.exists("/dev/kvm"):
    fail("/dev/kvm nicht verfügbar")

if not os.path.exists(SSH_KEY):
    ok(f"Erstelle SSH-Key: {SSH_KEY}")
    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-f", SSH_KEY, "-N", "", "-C", "coreos"],
        check=True, capture_output=True
    )

# ==========================
# Download FCOS image
# ==========================
if not os.path.exists(DISK_FILE):
    xz_file = DISK_FILE + ".xz"
    if not os.path.exists(xz_file):
        url = f"https://builds.coreos.fedoraproject.org/prod/streams/stable/builds/{FCOS_VERSION}/x86_64/fedora-coreos-{FCOS_VERSION}-qemu.x86_64.qcow2.xz"
        ok(f"Lade Fedora CoreOS {FCOS_VERSION}...")
        ok(f"  {url}")
        urllib.request.urlretrieve(url, xz_file)
        ok(f"Download: {os.path.getsize(xz_file)//1024//1024} MB")
    else:
        ok(f"Cache: {os.path.basename(xz_file)}")
    ok("Entpacke Disk-Image...")
    subprocess.run(["unxz", "-k", xz_file], check=True)  # -k = keep original
    ok(f"Disk: {os.path.basename(DISK_FILE)} ({os.path.getsize(DISK_FILE)//1024//1024} MB)")
else:
    ok(f"Disk: {os.path.basename(DISK_FILE)} ({os.path.getsize(DISK_FILE)//1024//1024} MB)")

# Resize disk to DISK_SIZE if it hasn't been grown yet
current_size = os.path.getsize(DISK_FILE)
target_bytes = int(DISK_SIZE[:-1]) * 1024**3
if current_size < target_bytes:
    ok(f"Resize disk to {DISK_SIZE}...")
    subprocess.run(["qemu-img", "resize", DISK_FILE, DISK_SIZE], check=True)
    ok(f"Disk now: {os.path.getsize(DISK_FILE)//1024//1024} MB")
else:
    ok(f"Disk already {DISK_SIZE} (or larger)")

# ==========================
# Generate Ignition config via Butane
# ==========================
ok("Erstelle Ignition-Config via Butane...")

if not os.path.exists(BUTANE_CONFIG):
    fail(f"Butane config nicht gefunden: {BUTANE_CONFIG}")

# Run Butane to convert .bu -> .ign
butane_cmd = [
    "podman", "run", "--rm", "-i",
    "--security-opt", "label=disable",
    "-v", f"{TEST_DIR}:/pwd",
    "-w", "/pwd",
    "quay.io/coreos/butane:release",
    "--pretty", "--strict",
    "config.bu"
]

# Check if butane binary is available
butane_binary = shutil.which("butane")
if butane_binary:
    butane_cmd = ["butane", "--pretty", "--strict", "config.bu"]
    ok(f"Butane binary found: {butane_binary}")
else:
    ok("Butane binary nicht gefunden, verwende Podman-Container...")

result = subprocess.run(
    butane_cmd,
    cwd=TEST_DIR,
    capture_output=True,
    text=True
)

if result.returncode != 0:
    fail(f"Butane failed:\n{result.stderr}")

with open(IGNITION_FILE, "w") as f:
    f.write(result.stdout)

# Validate
with open(IGNITION_FILE) as f:
    json.load(f)

ok(f"Ignition: {os.path.basename(IGNITION_FILE)}")

# ==========================
# Start VM
# ==========================
print()
print("=" * 50)
print("  Starte Fedora CoreOS VM")
print("=" * 50)
print()
print(f"  Netzwerk:   QEMU user mode (NAT)")
print(f"  SSH-Zugriff: ssh -p {SSH_PORT} -i {SSH_KEY} core@localhost")
print(f"  Console:      (Terminal bleibt offen)")
print(f"  Stopp:        Ctrl+C")
print()
warn("CoreOS bootet ca. 2-3 Minuten, dann Reboot zu SecureBlue.")
warn("SSH erst nach Reboot (~1-2 Min) verfügbar.")
print()

cmd = [
    "qemu-system-x86_64",
    "-machine", "q35,accel=kvm",
    "-cpu", "host",
    "-m", "4096",
    "-smp", "2",
    "-drive", f"file={DISK_FILE},format=qcow2,if=virtio",
    # x86_64: pass Ignition via fw_cfg (firmware config interface)
    "-fw_cfg", f"name=opt/com.coreos/config,file={IGNITION_FILE}",
    "-netdev", f"user,id=net0,hostfwd=tcp::{SSH_PORT}-:22",
    "-device", "virtio-net-pci,netdev=net0",
    "-display", "none",
    "-serial", "mon:stdio",
]

subprocess.run(cmd, check=True)
