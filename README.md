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
| Backup | `btrfs-backup.timer` (01:00): incremental `btrfs send` to `base_setup_backup_dir` when it is mounted |
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

## Backup target (iSCSI + LUKS)

`base_setup_backup_dir` can be an encrypted iSCSI LUN instead of a USB disk.
The role logs in to the target, opens the LUKS device and mounts it. The backup
script itself is unchanged: it still does incremental `btrfs send`.

```yaml
base_setup_iscsi_portal: "192.168.0.50"
base_setup_iscsi_target: "iqn.2015-04.com.wdc:ex2ultra.backup"
base_setup_iscsi_chap_user: "t630"
base_setup_iscsi_chap_password: "<chap secret>"
base_setup_luks_passphrase: "<passphrase>"
base_setup_backup_dir: /var/backup
```

Set `base_setup_backup_device` instead of the portal to encrypt a local disk.

CAUTION: Keep `base_setup_luks_passphrase` somewhere other than this machine.
Without it the backup cannot be read, which matters most when this machine is
the thing that failed.

### SELinux blocks iSCSI on SecureBlue

iscsid does not start under the stock policy:

```
iscsid: can not create NETLINK_ISCSI socket [Permission denied]
avc: denied { create } for comm="iscsid"
  scontext=...:iscsid_t:s0 tclass=netlink_iscsi_socket
```

The class and both permissions exist in the policy, and `deny_unknown` is 0,
but a local allow rule for exactly `iscsid_t self:netlink_iscsi_socket
{ create bind }` installs and has no effect. That was tested and repeated.
Only a permissive domain works:

```yaml
base_setup_iscsi_selinux_permissive: true
```

This stops SELinux enforcing iscsid alone. Every other domain stays enforcing,
and denials for iscsid are still logged. It is weaker than the stock policy,
so it is off by default and the role fails with an explanation instead of
turning it on by itself.

A backup over NFS or SMB needs no policy change. That is the alternative if
you would rather not relax the policy for iscsid.

### First use

The role never erases a device that carries a signature. To format a new and
empty LUN, run one deploy with `base_setup_iscsi_format=true`. The run stops
with an error if the device holds anything.

```bash
ansible-playbook ... -e base_setup_iscsi_format=true
```

Then remove the flag. The device is found by path, so it survives a reboot
through `/etc/crypttab` and `/etc/fstab`, both with `_netdev,nofail`.

### Staleness

The backup treats an absent target as a skip and exits 0, so a failure alert
never fires for a disk that is not there. `BackupStale` in `service-monitoring`
covers that: it alerts when the job has not logged a completed run for 48
hours, and stays quiet on a host that runs no backup.

## Variables

| Var | Default |
|---|---|
| `base_setup_services` | nextcloud / proxy / monitoring |
| `base_setup_extra_services` | `[]` (appended to the above) |
| `base_setup_services_dir` | `/var/services` |
| `base_setup_btrfs_snapshot_retention_days` | 30 |
| `base_setup_btrfs_snapshot_schedule` | `daily` |
| `base_setup_backup_dir` | `""` (disabled) |
| `base_setup_backup_retention_days` | 90 |
| `base_setup_iscsi_portal` / `_target` | `""` (no iSCSI) |
| `base_setup_backup_device` | `""` (local disk instead of iSCSI) |
| `base_setup_iscsi_format` | `false` (never erases by default) |
| `base_setup_luks_passphrase` | required when a backup device is set |
| `base_setup_firewall_services` | ssh, http, https |

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
