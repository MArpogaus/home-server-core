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

```bash
pre-commit install --install-hooks -t pre-commit -t commit-msg -t pre-push
```

Plain `pre-commit install` wires up only the pre-commit stage, so the
commitizen message and branch checks stay dormant. Hooks: shellcheck,
ansible-lint (which owns YAML style here), commitizen for conventional commits.
CI runs the same set on push and pull request. Actions are pinned to SHAs, and
dependabot updates actions and hook revisions weekly against `dev`.

## License

MIT
