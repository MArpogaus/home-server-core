# ansible-base

Ansible playbook for base provisioning of a SecureBlue (FCOS) home server.
Target: a thin client with 8 GB RAM, one Btrfs SSD, rootless Podman Quadlets.

## Prerequisites

- Ansible Core 2.21+, `community.general` (for the `run0` become method)
- Fedora CoreOS 44+ rebased to SecureBlue `securecore-main-hardened`
- Passwordless `run0` for `wheel` via polkit (set up in `test/config.bu.template`)

## Architecture

```
site.yml (1 play)
  ├── base_setup role (this repo)   Btrfs subvolumes, users, subuid, SELinux,
  │                                 snapshots, off-box backup, zram, firewall,
  │                                 auto-update / auto-reboot timers
  ├── nextcloud_service role        service-nextcloud
  ├── bunker_service role           service-bunker
  └── monitoring_service role       service-monitoring
```

One Linux user per service, each with its own systemd user manager and Podman
network. Cross-service traffic goes through host-published ports
(the host address plus the published port), never container names. The service list
lives in `roles/base_setup/defaults/main.yml`; override entries in
`secrets/vars.yml`.

## What `base_setup` does

| Area | How |
|---|---|
| Storage | Btrfs subvolume per service under `/var/services`, `snapshots` subvolume |
| Users | System users, linger, optional extra `groups`; subuid/subgid range starts at `uid * 65536 + 100000`, so it is stable and collision-free |
| SELinux | `container_file_t` on `/var/services` |
| Snapshots | `btrfs-snapshot@<svc>.timer` (daily RO snapshot, retention by date in the name) |
| Backup | `btrfs-backup@<target>.timer` (01:00): incremental `btrfs send` to each configured target that is present |
| Memory | Swap on zram, sized `min(ram / 2, 4096)` |
| Updates | `podman-auto-update.timer` per user, `auto-reboot-staged.timer` for rpm-ostree |
| Firewall | firewalld: ssh, http, https only; `ip_unprivileged_port_start=80` |

## Usage

Service repos are siblings: `../service-nextcloud`, `../service-bunker`,
`../service-monitoring`. Inventory and secrets live in `deployment-private`.

```bash
../deployment-private/deploy.sh
```

## Adding a service

1. Copy `service-template`, replace `__NAME__`.
2. Add it to `base_setup_extra_services` in `secrets/vars.yml` (no need to
   restate the built-in three):

   ```yaml
   base_setup_extra_services:
     - name: immich
       uid: 1003
       role: immich_service
       repo: immich
   ```
3. Add its `ansible-role` to `roles_path` in `ansible.cfg`.

Each service gets a subvolume, user, subuid range, SELinux label, linger,
snapshot timer and auto-update timer automatically.

## Backup targets

Every target is a LUKS container holding Btrfs, whether it is a USB disk or an
iSCSI LUN on the NAS. One mechanism therefore covers all of them, and
`btrfs send` stays unchanged.

```yaml
base_setup_luks_passphrase: "<one passphrase for every target>"
base_setup_backup_targets:
  - uuid: 7f3c8e2a-...      # UUID of the LUKS container
    name: usb
    retention_days: 30
  - uuid: a91b4d17-...
    name: nas
    retention_days: 180
```

Targets are matched by the UUID of the LUKS container, so a disk keeps working
after it moves to another port. `name` is used for the mount point, the unit
instance and the alert.

Each target gets:

- a `crypttab` entry, opened by systemd when the disk appears, `nofail` so a
  missing one never holds up the boot
- `/var/backup/<name>` as an automount, unmounted again after five idle minutes
- `btrfs-backup@<name>.service`, with its own retention

There is no timer on the sync. A finished snapshot triggers it, through
`OnSuccess=` on `btrfs-snapshot@<service>.service`, so the copy is always of
the snapshot that was just taken. systemd merges the identical start jobs from
each service, so each target syncs once.

The sync requires its mount. An absent target therefore fails the unit and
appears in the journal, and `ScheduledJobFailed` reports it. A disk you unplug
on purpose will alert every night, which is the deliberate trade for never
missing one that should have been there.

CAUTION: Keep `base_setup_luks_passphrase` somewhere other than this machine.
One passphrase opens every target, and without it no backup can be read.

### First use

The role never erases a device that carries a signature. To prepare a new and
empty iSCSI LUN, run one deploy with `base_setup_iscsi_format=true`. It formats
the LUN and prints the UUID to put in `base_setup_backup_targets`. Then remove
the flag.

A local disk is prepared by hand once:

```bash
cryptsetup luksFormat --type luks2 /dev/sdX /etc/luks/backup.key
cryptsetup open --key-file /etc/luks/backup.key /dev/sdX tmp
mkfs.btrfs -L backup /dev/mapper/tmp && cryptsetup close tmp
blkid -s UUID -o value /dev/sdX      # the value for the target list
```

### SELinux blocks iSCSI on SecureBlue

iscsid does not start under the stock policy:

```
iscsid: can not create NETLINK_ISCSI socket [Permission denied]
avc: denied { create } for comm="iscsid"
  scontext=...:iscsid_t:s0 tclass=netlink_iscsi_socket
```

The class and both permissions exist in the policy, and `deny_unknown` is 0.
But a local allow rule for exactly `iscsid_t self:netlink_iscsi_socket
{ create bind }` installs and has no effect. That was tested and repeated.
Only a permissive domain works:

```yaml
base_setup_iscsi_selinux_permissive: true
```

This stops SELinux enforcing iscsid alone. Every other domain stays enforcing,
and denials for iscsid are still logged. It is weaker than the stock policy.
It is therefore off by default, and the role fails with an explanation rather
than turn it on by itself.

A USB target needs none of this, because it needs no iSCSI.

## Variables

| Var | Default |
|---|---|
| `base_setup_services` | nextcloud / proxy / monitoring |
| `base_setup_extra_services` | `[]` (appended to the above) |
| `base_setup_services_dir` | `/var/services` |
| `base_setup_btrfs_snapshot_retention_days` | 30 |
| `base_setup_btrfs_snapshot_schedule` | `daily` |
| `base_setup_backup_targets` | `[]` (no off-box backup) |
| `base_setup_backup_root` | `/var/backup` |
| `base_setup_backup_retention_days` | 90 (per-target fallback) |
| `base_setup_iscsi_portal` / `_target` | `""` (no iSCSI) |
| `base_setup_iscsi_format` | `false` (never erases by default) |
| `base_setup_luks_passphrase` | required when a backup device is set |
| `base_setup_firewall_services` | ssh, http, https |

## Installing the real host

`ignition/` holds one Butane template, used for the test VM and for the real
hardware alike, so the two cannot drift apart. `ignition/build.sh` renders it
and writes the result:

```bash
cd ansible-base/ignition
./build.sh ign                       # render config.ign only
./build.sh install /dev/sdX          # install Fedora CoreOS onto that disk
./build.sh iso fedora-coreos-live.iso /dev/sda
```

`install` writes to a disk attached to this machine. `iso` writes `t630.iso`,
which installs onto the named device of the *target* machine and reboots, with
no prompt. Name the disk as the t630 sees it.

It authorises the smartcard key from your SSH agent, the one whose comment
carries `cardno:`. Set `SSH_PUBLIC_KEY` to authorise a different key. It then
asks for a console password, which is for physical recovery: SSH refuses
passwords either way.

CAUTION: The installed host accepts that one key. Deploys therefore run with
`SSH_AUTH_KEY=agent` and the token plugged in. The test VM keeps using
`ssh/coreos_key`, which is the default.

## Test VM

```bash
python3 test/start_vm.py --fresh      # first time
python3 test/start_vm.py --save-base  # once the rebase is done, VM shut down
python3 test/start_vm.py --restore    # every reset after that
```

See `test/README.md`. The playbook is deployed against it from
`deployment-private/`.

## Development

Work on `dev`. Conventional commits.

```bash
pre-commit install --install-hooks -t pre-commit -t commit-msg -t pre-push
```

Plain `pre-commit install` wires up the pre-commit stage only, which leaves the
commit-message and branch hooks dormant.

## License

MIT
