# ansible-base

Ansible playbook for base provisioning of a SecureBlue (FCOS) home server.

## Prerequisites

- Ansible Core 2.21+
- `community.general` collection (for `run0` become method)
- Fedora CoreOS 44+ (SecureBlue `securecore-main-hardened`)
- `run0` via polkit (default on SecureBlue — no sudo required)

## Architecture

Single playbook (`site.yml`) with one play that loops over `base_setup_services`:

```
site.yml (1 play)
  ├── base_setup role (this repo)          — Btrfs, users, SELinux, snapshots, network, firewall
  ├── nextcloud_service role               — Nextcloud Quadlets (service-nextcloud)
  ├── bunker_service role                  — Bunkerweb proxy (service-bunker)
  └── monitoring_service role              — Loki/Prometheus/Grafana (service-monitoring)
```

Service roles live in separate repos referenced via `ansible.cfg` `roles_path`.

## Task Reference

### `base_setup` role — 27 tasks

| # | Task | Module | Rationale |
|---|------|--------|-----------|
| 1 | Ensure `/var/services` exists | `file` | Root parent dir for all service subvolumes |
| 2 | Create Btrfs subvolumes per service | `command` | Separate CoW subvolumes for snapshot isolation |
| 3 | Create snapshots subvolume | `command` | Store read-only snapshots outside service subvols |
| 4 | Create system users | `user` | Dedicated non-login UIDs for rootless Podman |
| 5-6 | Add subuid/subgid ranges | `lineinfile` | Rootless Podman needs UID/GID mapping ranges |
| 7 | Set subvolume ownership | `file` | Service user must own its subvolume root |
| 8 | Create Quadlet systemd dir | `file` | Rootless Quadlet reads `.container` from `~/.config/containers/systemd` |
| 9 | Build SELinux target list | `set_fact` | Compute paths for `container_file_t` labeling |
| 10 | Install SELinux contexts | `sefcontext` | Allow Podman containers to access service dirs |
| 11 | Apply SELinux labels | `command` | `restorecon` to activate the new contexts |
| 12 | Create containers config dir | `file` | Podman auth/config stored here |
| 13-14 | Deploy snapshot service+timer | `template` | Systemd oneshot + `OnCalendar` timer for Btrfs snapshots |
| 15 | Deploy snapshot cleanup script | `copy` | Shell script: creates RO snapshots, prunes old ones |
| 16 | Enable snapshot timers | `systemd` | Activate per-service snapshot schedule |
| 17 | Enable linger | `command` | `loginctl enable-linger` keeps user systemd alive after logout |
| 18 | Start systemd user managers | `systemd` | Activates `user@.service` for Quadlet to run |
| 19-20 | Deploy auto-reboot script+timer | `copy`+`template` | Automated reboot after `rpm-ostree update` staged |
| 21 | Enable auto-reboot timer | `systemd` | `OnCalendar=daily` at 03:00 + 30min random delay |
| 22 | Enable podman auto-update timers | `command` | `podman-auto-update.timer` checks registry for new images |
| 23 | Ensure firewalld running | `systemd` | `firewalld` must be active before rules |

... via `machinectl shell` | | 24-26 | Open firewall (SSH, HTTP, HTTPS) | `command` | Minimal surface: only 22/80/443 | | 27 | Reload firewalld | `command` | Apply permanent rules | | 28 | Allow unprivileged ports >=80 | `copy` | `sysctl` so rootless Podman can bind 80/443 | | 29 | Reload systemd daemon | `systemd` | Pick up new unit files |

## Usage

```bash
# Clone service repos alongside ansible-base:
#   ../service-nextcloud
#   ../service-bunker
#   ../service-monitoring

# Deploy via deployment-private (recommended):
../deployment-private/deploy.sh

# Or directly:
ansible-playbook -i inventory/hosts.ini site.yml --extra-vars "@secrets/vars.yml"
```

## Custom Deployment

Files requiring changes:

| File | What to change |
|---|---|
| `inventory/hosts.ini` | Hostname/IP, SSH port, SSH key path, user |
| `secrets/vars.yml` (in `deployment-private`) | All passwords, domain, tokens, image tags |
| `roles/base_setup/defaults/main.yml` | `base_setup_services` list, snapshot schedule, subuid range size |
| `ansible.cfg` | `roles_path` if service repos are elsewhere |
| `test/config.bu.template` | SSH public key, password hash, GHCR key material |

### Adding a new service

1. Add entry to `base_setup_services` in `defaults/main.yml`
2. Create `service-<name>/` with `ansible-role/<name>_service/` (Quadlet files, templates, tasks)
3. Add `roles_path` entry in `ansible.cfg`

## Generalization Status

| Aspect | Status |
|---|---|
| Service users/UIDs | Configurable via `secrets/vars.yml` |
| Subuid ranges | Computed from index (name-based would be better) |
| Snapshot schedule | Configurable via `base_setup_btrfs_snapshot_schedule` |
| Snapshot retention | Configurable via `base_setup_btrfs_snapshot_retention_days` (now wired through systemd unit env) |
| Snapshot dir | Configurable via `base_setup_btrfs_snapshot_dir` (now wired through systemd unit env) |
| Firewall services | Hardcoded to ssh/http/https |
| Port start floor | Hardcoded to 80 |
| Reboot schedule | Hardcoded to 03:00+30m |

## Files

```
ansible-base/
  ansible.cfg                 # Ansible config (run0, roles_path, SSH)
  site.yml                    # Main playbook (1 play, loop over services)
  .pre-commit-config.yaml     # Pre-commit hooks
  roles/base_setup/
    defaults/main.yml         # Variable defaults
    tasks/main.yml            # 27 tasks
    handlers/main.yml         # Restart snapshot services
    templates/                # *.j2 for systemd units
    files/                    # Static scripts
  inventory/                  # hosts.ini (gitignored)
  test/                       # Butane, VM launcher, CI helpers
  .github/workflows/          # CI/CD
```

## License

MIT
