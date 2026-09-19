# Test VM

A Fedora CoreOS guest that rebases itself to SecureBlue, so the playbook can be
tested against the real target platform.

## Use

```bash
python3 start_vm.py             # boot (reuses the existing disk)
python3 start_vm.py --fresh     # rebuild the disk, re-run Ignition and the rebase
python3 start_vm.py --save-base # VM shut down: tag this disk state "base"
python3 start_vm.py --restore   # roll back to "base" and boot
python3 start_vm.py --help      # all options
```

The guest gets 8 GB and 2 vCPUs by default, matching the target thin client.
Override with `--memory` and `--cpus`. Sizing it below the real hardware makes
a from-scratch start, which pulls every image while starting every container,
fail under memory pressure that the real box never sees.

Then, from `deployment-private/`:

```bash
./deploy.sh
./functional_test.sh
```

## Resetting between test runs

Three levels, cheapest first.

| Want | Do | Cost |
|---|---|---|
| Undo what Ansible created | `deployment-private/reset.sh` | seconds, VM keeps running |
| Back to a clean provisioned host | `--restore` | seconds, VM restarts |
| Back to bare Fedora CoreOS | `--fresh` | download plus rebase plus two reboots |

`--restore` is the one you want most of the time. Getting a usable VM costs an
image download, an rpm-ostree rebase and two reboots, and none of that is worth
repeating to test a playbook change.

### Taking the base snapshot

Do this once, after the rebase has finished:

```bash
ssh -p 2222 -i coreos_key core@localhost rpm-ostree status   # expect securecore
ssh -p 2222 -i coreos_key core@localhost run0 systemctl poweroff
python3 start_vm.py --save-base
```

The VM must be shut down. `qemu-img` refuses to write a snapshot into a disk
QEMU still has open, and a snapshot taken mid-rebase captures a broken
state. Re-running `--save-base` replaces the existing snapshot.

This is a qcow2 internal snapshot: it lives inside `fcos.qcow2`, costs only the
blocks that change afterwards, and needs no second image or backing-file chain.
On `--restore` the Ignition config is not regenerated, because Ignition runs
on a first boot only.

## What start_vm.py does

1. Creates `coreos_key` if missing.
2. Downloads and extracts the FCOS image, grows it to 20 GB. The `.xz` stays as
   a cache, so `--fresh` skips the download.
3. Renders `config.bu` from `config.bu.template` with the public key and, if
   `mkpasswd` is available, a console password (`VM_PASSWORD`, default `test`).
   FCOS gives the `wheel` group passwordless sudo, so the password is optional.
4. Converts it to `config.ign` with `butane`, falling back to the Butane
   container image if the binary is not installed.
5. Boots QEMU with the requested RAM and vCPUs (8 GB, 2 by default),
   SSH forwarded to port 2222.

## Boot sequence

```
FCOS first boot → Ignition applies config.ign
  → install-secureblue.service runs /opt/install_secureblue.sh
  → rpm-ostree rebase to securecore → reboot
  → SSH available, ready for Ansible
```

The rebase takes a few minutes and SSH only answers after the second boot.
Nothing waits for a login: the first boot does the work on its own. Until the
reboot the host is stock FCOS, which has no python3, so a deploy started too
early fails with `The module interpreter '/usr/bin/python3' was not found`.

## Reaching the VM from a rootless container

From the host, `localhost` works. From inside a rootless Podman container it
does not. Two paths reach the forwarded ports, and both break and recover on
their own, so test both before you debug anything else:

```bash
timeout 3 bash -c 'echo > /dev/tcp/169.254.1.2/2222'      # host.containers.internal
ip -4 addr show scope global | grep inet                   # on the host: its LAN address
TARGET_HOST=<the one that answers> ./functional_test.sh
```

A dead path answers `Connection refused` on every port, including ports where
nothing listens, so refusal says nothing about the VM.

`deploy.sh`, `functional_test.sh` and `reset.sh` all honour `TARGET_HOST` and
`TARGET_PORT`.

## One key everywhere

`coreos_key` is the single SSH identity: its public half is baked into the
Ignition config, and `deployment-private/ssh/coreos_key` must be the same key.
If you regenerate it, copy both halves over and re-run with `--fresh`.

## Requirements

`qemu-system-x86_64` with `/dev/kvm`, `qemu-img`, `python3`, `unxz`, and either
`butane` or `podman`. Optional: `mkpasswd` for the console password.
