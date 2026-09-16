#!/usr/bin/env python3
"""Boot a Fedora CoreOS test VM that rebases itself to SecureBlue.

Renders config.bu from the template, converts it to Ignition, and starts QEMU.
Stdlib only.
"""

import argparse
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
TEMPLATE = os.path.join(TEST_DIR, "config.bu.template")
BUTANE_CONFIG = os.path.join(TEST_DIR, "config.bu")
IGNITION = os.path.join(TEST_DIR, "config.ign")
# One key for everything: Ignition bakes in the pubkey, deploy/test scripts use
# the private half. deployment-private/ssh/coreos_key must be the same key.
SSH_KEY = os.path.join(TEST_DIR, "coreos_key")
URL = (f"https://builds.coreos.fedoraproject.org/prod/streams/stable/builds/"
       f"{FCOS_VERSION}/x86_64/fedora-coreos-{FCOS_VERSION}-qemu.x86_64.qcow2.xz")

BASE_SNAPSHOT = "base"
BUTANE_RELEASE = "v0.28.0"

GREEN, RED, YELLOW, NC = "\033[0;32m", "\033[0;31m", "\033[1;33m", "\033[0m"


def ok(msg):
    print(f"{GREEN}[+] {msg}{NC}")


def warn(msg):
    print(f"{YELLOW}[!] {msg}{NC}")


def fail(msg):
    print(f"{RED}[-] {msg}{NC}")
    sys.exit(1)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Getting to a usable VM costs a download, an rpm-ostree rebase "
               "and two reboots. Take a --save-base snapshot once that is done "
               "and every later reset is a --restore.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--fresh", action="store_true",
                      help="rebuild the disk, re-running Ignition and the rebase")
    mode.add_argument("--restore", action="store_true",
                      help=f'roll back to the "{BASE_SNAPSHOT}" snapshot and boot')
    mode.add_argument("--save-base", action="store_true",
                      help=f'tag the current disk state "{BASE_SNAPSHOT}" '
                           "(the VM must be shut down) and exit")
    # The target is an 8 GB thin client. Matching it here means a from-scratch
    # start, which pulls every image while starting every container, is not
    # tested under memory pressure the real box would never see.
    parser.add_argument("--memory", default="8192", metavar="MB",
                        help="guest RAM in MB (default: %(default)s)")
    parser.add_argument("--cpus", default="2", metavar="N",
                        help="guest vCPUs (default: %(default)s)")
    parser.add_argument("--disk-size", default="20G", metavar="SIZE",
                        help="grow the disk image to this size (default: %(default)s)")
    parser.add_argument("--ssh-port", default=2222, type=int, metavar="PORT",
                        help="host port forwarded to the guest's SSH (default: %(default)s)")
    return parser.parse_args(argv)


def save_base_snapshot():
    """Tag the current disk state so a reset is a rollback, not a rebuild."""
    if not os.path.exists(DISK):
        fail(f"No disk at {DISK}")
    # Replace any existing snapshot so re-running is idempotent.
    subprocess.run(["qemu-img", "snapshot", "-d", BASE_SNAPSHOT, DISK],
                   capture_output=True)
    result = subprocess.run(["qemu-img", "snapshot", "-c", BASE_SNAPSHOT, DISK],
                            capture_output=True, text=True)
    if result.returncode != 0:
        fail(f"Could not snapshot (is the VM still running?):\n{result.stderr}")
    ok(f'Saved snapshot "{BASE_SNAPSHOT}". Roll back with --restore.')


def restore_base_snapshot():
    result = subprocess.run(["qemu-img", "snapshot", "-a", BASE_SNAPSHOT, DISK],
                            capture_output=True, text=True)
    if result.returncode != 0:
        fail(f'No "{BASE_SNAPSHOT}" snapshot to restore '
             f"(take one with --save-base):\n{result.stderr}")
    ok(f'Rolled back to "{BASE_SNAPSHOT}"')


def ensure_ssh_key():
    if not os.path.exists(SSH_KEY):
        ok(f"Creating SSH key: {SSH_KEY}")
        subprocess.run(["ssh-keygen", "-t", "ed25519", "-f", SSH_KEY, "-N", "",
                        "-C", "coreos"], check=True, capture_output=True)


def ensure_disk(fresh, disk_size):
    """Download and extract the image if needed.

    Ignition only runs on first boot, so re-testing it needs a fresh disk. The
    .xz download is kept as a cache, which makes --fresh cost seconds.
    """
    if fresh and os.path.exists(DISK):
        ok("--fresh: removing existing disk")
        os.remove(DISK)

    if not os.path.exists(DISK):
        if not os.path.exists(DISK_XZ):
            ok(f"Downloading Fedora CoreOS {FCOS_VERSION}")
            urllib.request.urlretrieve(URL, DISK_XZ)
        ok("Extracting disk image")
        subprocess.run(["unxz", "-k", DISK_XZ], check=True)
        subprocess.run(["qemu-img", "resize", DISK, disk_size], check=True)
    ok(f"Disk: {os.path.getsize(DISK) // 1024 // 1024} MB")


def render_butane_config():
    """Fill the template with the public key and an optional console password."""
    with open(SSH_KEY + ".pub") as handle:
        pubkey = handle.read().strip()

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

    with open(TEMPLATE) as handle:
        config = handle.read().replace("${SSH_PUBLIC_KEY}", pubkey)
    config = "".join(pw_line if "${PASSWORD_HASH}" in line else line
                     for line in config.splitlines(keepends=True))
    with open(BUTANE_CONFIG, "w") as handle:
        handle.write(config)
    ok("Rendered config.bu")


def butane_command():
    if shutil.which("butane"):
        return ["butane", "--pretty", "--strict", "config.bu"]
    if shutil.which("podman"):
        ok("butane binary not found, using container")
        return ["podman", "run", "--rm", "-i", "--security-opt", "label=disable",
                "-v", f"{TEST_DIR}:/pwd", "-w", "/pwd",
                "quay.io/coreos/butane:release",
                "--pretty", "--strict", "config.bu"]
    fail("Neither butane nor podman found. Install butane:\n"
         f"  curl -fsSL -o ~/.local/bin/butane https://github.com/coreos/butane"
         f"/releases/download/{BUTANE_RELEASE}/butane-x86_64-unknown-linux-gnu"
         " && chmod +x ~/.local/bin/butane")
    return []  # unreachable; fail() exits


def build_ignition():
    """Render config.bu and convert it to config.ign."""
    render_butane_config()
    result = subprocess.run(butane_command(), cwd=TEST_DIR,
                            capture_output=True, text=True)
    if result.returncode != 0:
        fail(f"Butane failed:\n{result.stderr}")
    with open(IGNITION, "w") as handle:
        handle.write(result.stdout)
    with open(IGNITION) as handle:
        json.load(handle)  # refuse to boot a truncated config
    ok("Generated config.ign")


def print_banner(args):
    if args.restore:
        hint = f'  Restored from the "{BASE_SNAPSHOT}" snapshot: ready to use.'
    else:
        hint = ("  Boots FCOS (~2 min), rebases to SecureBlue, reboots.\n"
                "  SSH answers only after that second boot. Once `rpm-ostree status`\n"
                "  shows securecore, shut the VM down and run --save-base so later\n"
                "  resets take seconds instead of a full rebuild.")
    print(f"""
{'=' * 50}
  Fedora CoreOS test VM  ({args.memory} MB, {args.cpus} vCPU)
{'=' * 50}

  SSH:   ssh -p {args.ssh_port} -i {SSH_KEY} core@localhost
  Stop:  Ctrl+C

{hint}
""")


def boot(args, ignition_args):
    subprocess.run([
        "qemu-system-x86_64",
        "-machine", "q35,accel=kvm",
        "-cpu", "host",
        "-m", args.memory,
        "-smp", args.cpus,
        "-drive", f"file={DISK},format=qcow2,if=virtio",
        *ignition_args,
        "-netdev", f"user,id=net0,hostfwd=tcp::{args.ssh_port}-:22",
        "-device", "virtio-net-pci,netdev=net0",
        "-display", "none",
        "-serial", "mon:stdio",
    ], check=True)


def main(argv=None):
    args = parse_args(argv)

    if args.save_base:
        save_base_snapshot()
        return 0

    if not os.path.exists("/dev/kvm"):
        fail("/dev/kvm not available")

    if args.restore:
        restore_base_snapshot()

    ensure_ssh_key()
    ensure_disk(args.fresh, args.disk_size)

    if args.restore:
        # The disk is already provisioned and Ignition, which only runs on first
        # boot, would ignore the config anyway.
        ignition_args = []
    else:
        build_ignition()
        ignition_args = ["-fw_cfg", f"name=opt/com.coreos/config,file={IGNITION}"]

    print_banner(args)
    boot(args, ignition_args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
