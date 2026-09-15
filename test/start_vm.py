#!/usr/bin/env python3
"""Boot a Fedora CoreOS test VM that rebases itself to SecureBlue.

Renders config.bu from the template, converts it to Ignition, and starts QEMU.
Stdlib only.

    python3 start_vm.py              # boot (reuses an existing disk)
    python3 start_vm.py --fresh      # rebuild the disk, re-run Ignition + rebase
    python3 start_vm.py --save-base  # VM off: tag the current disk state "base"
    python3 start_vm.py --restore    # roll back to "base" and boot
"""

import json
import os
import shutil
import subprocess
import sys
import urllib.request

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
FCOS_VERSION = "44.20260510.3.1"
DISK = os.path.join(TEST_DIR, "fcos.qcow2")
DISK_XZ = DISK + ".xz"
DISK_SIZE = "20G"
TEMPLATE = os.path.join(TEST_DIR, "config.bu.template")
BUTANE_CONFIG = os.path.join(TEST_DIR, "config.bu")
IGNITION = os.path.join(TEST_DIR, "config.ign")
# One key for everything: Ignition bakes in the pubkey, deploy/test scripts use
# the private half. deployment-private/ssh/coreos_key must be the same key.
SSH_KEY = os.path.join(TEST_DIR, "coreos_key")
SSH_PORT = 2222
URL = (f"https://builds.coreos.fedoraproject.org/prod/streams/stable/builds/"
       f"{FCOS_VERSION}/x86_64/fedora-coreos-{FCOS_VERSION}-qemu.x86_64.qcow2.xz")

BASE_SNAPSHOT = "base"

GREEN, RED, YELLOW, NC = "\033[0;32m", "\033[0;31m", "\033[1;33m", "\033[0m"
def ok(m): print(f"{GREEN}[+] {m}{NC}")
def warn(m): print(f"{YELLOW}[!] {m}{NC}")
def fail(m): print(f"{RED}[-] {m}{NC}"); sys.exit(1)

fresh = "--fresh" in sys.argv
restore = "--restore" in sys.argv

# --- Snapshot the provisioned base state -------------------------------------
# Getting to a usable VM costs a download, an rpm-ostree rebase and two reboots.
# A qcow2 internal snapshot taken once the rebase is done turns a reset into a
# second-long rollback. The VM must be shut down: qemu-img will not touch a disk
# QEMU still has open.
if "--save-base" in sys.argv:
    if not os.path.exists(DISK):
        fail(f"No disk at {DISK}")
    subprocess.run(["qemu-img", "snapshot", "-d", BASE_SNAPSHOT, DISK],
                   capture_output=True)
    r = subprocess.run(["qemu-img", "snapshot", "-c", BASE_SNAPSHOT, DISK],
                       capture_output=True, text=True)
    if r.returncode != 0:
        fail(f"Could not snapshot (is the VM still running?):\n{r.stderr}")
    ok(f'Saved snapshot "{BASE_SNAPSHOT}". Roll back with --restore.')
    sys.exit(0)

if fresh and restore:
    fail("--fresh rebuilds the disk and --restore rolls it back; pick one")

if not os.path.exists("/dev/kvm"):
    fail("/dev/kvm not available")

if restore:
    r = subprocess.run(["qemu-img", "snapshot", "-a", BASE_SNAPSHOT, DISK],
                       capture_output=True, text=True)
    if r.returncode != 0:
        fail(f"No \"{BASE_SNAPSHOT}\" snapshot to restore "
             f"(take one with --save-base):\n{r.stderr}")
    ok(f'Rolled back to "{BASE_SNAPSHOT}"')

# --- SSH key -----------------------------------------------------------------
if not os.path.exists(SSH_KEY):
    ok(f"Creating SSH key: {SSH_KEY}")
    subprocess.run(["ssh-keygen", "-t", "ed25519", "-f", SSH_KEY, "-N", "",
                    "-C", "coreos"], check=True, capture_output=True)

# --- Disk image --------------------------------------------------------------
# Ignition only runs on first boot, so a re-test needs a fresh disk. The .xz
# download is kept as a cache so --fresh costs seconds, not a re-download.
if fresh and os.path.exists(DISK):
    ok("--fresh: removing existing disk")
    os.remove(DISK)

if not os.path.exists(DISK):
    if not os.path.exists(DISK_XZ):
        ok(f"Downloading Fedora CoreOS {FCOS_VERSION}")
        urllib.request.urlretrieve(URL, DISK_XZ)
    ok("Extracting disk image")
    subprocess.run(["unxz", "-k", DISK_XZ], check=True)
    subprocess.run(["qemu-img", "resize", DISK, DISK_SIZE], check=True)
ok(f"Disk: {os.path.getsize(DISK) // 1024 // 1024} MB")

# --- Ignition ----------------------------------------------------------------
# Skipped on --restore: the disk is already provisioned and Ignition, which only
# runs on first boot, would ignore the config anyway.
def build_ignition():
    """Render config.bu from the template and convert it to config.ign."""
    pubkey = open(SSH_KEY + ".pub").read().strip()

    # The password is only for the serial console; FCOS gives wheel passwordless
    # sudo, so it is optional. Without mkpasswd, boot key-only rather than fail.
    if shutil.which("mkpasswd"):
        password = os.environ.get("VM_PASSWORD", "test")
        pw_hash = subprocess.run(["mkpasswd", "--method=yescrypt", password],
                                 check=True, capture_output=True,
                                 text=True).stdout.strip()
        pw_line = f'      password_hash: "{pw_hash}"\n'
    else:
        warn("mkpasswd not found — no console password, SSH key only")
        pw_line = ""

    config = open(TEMPLATE).read().replace("${SSH_PUBLIC_KEY}", pubkey)
    config = "".join(pw_line if "${PASSWORD_HASH}" in line else line
                     for line in config.splitlines(keepends=True))
    open(BUTANE_CONFIG, "w").write(config)
    ok("Rendered config.bu")

    if shutil.which("butane"):
        butane = ["butane", "--pretty", "--strict", "config.bu"]
    elif shutil.which("podman"):
        ok("butane binary not found, using container")
        butane = ["podman", "run", "--rm", "-i", "--security-opt", "label=disable",
                  "-v", f"{TEST_DIR}:/pwd", "-w", "/pwd",
                  "quay.io/coreos/butane:release",
                  "--pretty", "--strict", "config.bu"]
    else:
        fail("Neither butane nor podman found. Install butane:\n"
             "  curl -fsSL -o ~/.local/bin/butane https://github.com/coreos/butane"
             "/releases/download/v0.28.0/butane-x86_64-unknown-linux-gnu"
             " && chmod +x ~/.local/bin/butane")

    result = subprocess.run(butane, cwd=TEST_DIR, capture_output=True, text=True)
    if result.returncode != 0:
        fail(f"Butane failed:\n{result.stderr}")
    open(IGNITION, "w").write(result.stdout)
    json.load(open(IGNITION))
    ok("Generated config.ign")


if restore:
    ignition_args = []
else:
    build_ignition()
    ignition_args = ["-fw_cfg", f"name=opt/com.coreos/config,file={IGNITION}"]

# --- Boot --------------------------------------------------------------------
if restore:
    hint = f'  Restored from the "{BASE_SNAPSHOT}" snapshot: ready to use.'
else:
    hint = ("  Boots FCOS (~2 min), rebases to SecureBlue, reboots.\n"
            "  SSH answers only after that second boot. Once `rpm-ostree status`\n"
            "  shows securecore, shut the VM down and run --save-base so later\n"
            "  resets take seconds instead of a full rebuild.")

print(f"""
{'=' * 50}
  Fedora CoreOS test VM
{'=' * 50}

  SSH:   ssh -p {SSH_PORT} -i {SSH_KEY} core@localhost
  Stop:  Ctrl+C

{hint}
""")

subprocess.run([
    "qemu-system-x86_64",
    "-machine", "q35,accel=kvm",
    "-cpu", "host",
    # Matches the 8 GB target box minus host overhead
    "-m", "4096",
    "-smp", "2",
    "-drive", f"file={DISK},format=qcow2,if=virtio",
    *ignition_args,
    "-netdev", f"user,id=net0,hostfwd=tcp::{SSH_PORT}-:22",
    "-device", "virtio-net-pci,netdev=net0",
    "-display", "none",
    "-serial", "mon:stdio",
], check=True)
