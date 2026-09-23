# home-server-core

Ansible roles that prepare a Fedora CoreOS host for rootless containers.

The roles make one unprivileged user and one Btrfs subvolume for each service.
They also set up snapshots, off-box backup, the firewall and the Ignition
config that installs the host.

These roles name no service. The deployment sets `base_setup_services` and says
what the host is for. To run this project, read `home-server-deploy`.

## Architecture

```
site.yml
  base_setup role                   Btrfs subvolumes, users, subuid,
          │                         snapshots, off-box backup, zram, firewall,
          │                         auto-update / auto-reboot timers
          └── one service role per entry in base_setup_services
                └── quadlet_service role   deploys quadlets/, quadlets/container.d/
                                           and quadlets/configs/, reloads, restarts
                                           the pod on change
```

One Linux user per service, each with its own systemd user manager and Podman
network. Cross-service traffic goes through host-published ports, never
container names.

### What `base_setup` does

| Area | How |
|---|---|
| Storage | Btrfs subvolume per service under `/var/services`, `snapshots` subvolume on the same disk: a rollback mechanism, not a backup |
| Users | System users, linger, optional extra `groups`; the subuid/subgid range starts at `uid * base_setup_subuid_range_size + 100000`, so it is stable and collision-free |
| Snapshots | `btrfs-snapshot@<svc>.timer`, on `base_setup_btrfs_snapshot_schedule`; read-only, retention by the date in the name |
| Backup | `btrfs-backup@<target>.service`, started by a finished snapshot: incremental `btrfs send` to each target |
| Memory | Swap on zram, sized `min(ram / 2, 4096)` |
| Power | `sleep`, `suspend`, `hibernate` and `hybrid-sleep` targets masked: a server that suspends is down |
| Updates | `podman-auto-update.timer` per user for the containers. `auto-reboot-staged.timer` reboots into an OS image that is staged, after the night's backup. The platform stages the image with `rpm-ostreed-automatic.timer`. Stock Fedora CoreOS runs Zincati instead, which stages and reboots on its own schedule |
| Firewall | firewalld: ssh, http and https are opened, permanent and immediate, with no `firewall-cmd --reload`, which would drop the SSH connection the deploy runs over. `ip_unprivileged_port_start=80`, so any service user can bind 80 and 443 while the proxy is down |
| Metrics | `/var/lib/node-textfile`, see "Metrics" |

## Usage

This project needs Ansible Core 2.21 or newer with the collections in
`requirements.yml`. The host needs Fedora CoreOS 44 or newer. Ansible's Python
needs `passlib` and `bcrypt` (ntfy hashes its users):
`uv tool install --reinstall ansible --with passlib --with bcrypt`.

Service repos are siblings: `site.yml` includes the role of each entry from
`../home-server-<repo>/ansible-role/<repo>_service`. The inventory and the
scripts that drive this playbook live in `home-server-deploy`, the secrets in
`home-server-secrets`.

### Adding a service

Copy `home-server-template`. Follow its README.

Add an entry to `base_setup_services` in the deploy repository, at
`inventory/group_vars/homeserver.yml`:

```yaml
base_setup_services:
  - name: immich
    uid: 1003
    repo: immich
```

A service's `uid` never changes after its first deploy. It sets the subuid
range, and every image layer and data file of the service is owned inside that
range.

An image that this project's cosign key does not sign needs nothing further.
`base_setup` reads every `*_image` default of every service role, and every
`<repo>_service_*_image` variable the deployment sets for this host, and writes
each repository into the signature policy.

Each service gets a subvolume, user, subuid range, linger, snapshot timer and
auto-update timer. A repository may ship alert rules and dashboards in
`monitoring/`; `home-server-monitoring/README.md` has the format. This
repository's own `monitoring/` covers snapshots, backups, reboots, SSH and
SELinux.

## Host-specific tasks

A step that one host needs and no other host needs does not belong in these
roles. The deployment names a task file, and `site.yml` includes it before
`base_setup`, so a later task can depend on it (a device, a policy exception):

```yaml
host_tasks_pre: "{{ secrets_dir }}/tasks/<host>-pre.yml"
```

It is optional. `deploy.sh` sets `secrets_dir`.

Use this for the genuinely singular. A mechanism that two hosts can share
belongs in the role, with its value in the deployment. A platform step is the
exception. These roles target stock Fedora CoreOS, so a step that only a
derivative image needs lives in the deployment too, even when every host runs
one. The same holds for the Ignition config: `ignition/build.sh` merges the
Butane fragment that `PLATFORM_BU` names, such as a rebase to a derivative
image, into the config.

## Privilege escalation

Ansible becomes root and the service users with `run0`, through
`community.general.run0`. The plugin needs a terminal, and Ansible sees one only
in its own SSH arguments: `ssh_extra_args` in `ansible.cfg` carries
`-o RequestTTY=force`, which reaches `ssh` alone: `sftp` with a terminal hangs.
With a terminal each `run0` session closes when the call ends. A session that
stays in `closing` counts against logind's session limit, and a few hundred of
them stop logind from opening new ones; `functional_test.sh` checks for them.
Pipelining is off, because it cannot work with a terminal. `become_exe` sets
`TERM=dumb`, so `run0` writes no terminal escape codes into the module output.

The polkit rule `/etc/polkit-1/rules.d/60-run0-fast-user-auth.rules`, installed
by Ignition, grants `org.freedesktop.systemd1.manage-units` to `core` without
authentication. `manage-units` starts transient units, so `core` has
unauthenticated root on this host. The SSH key is the whole perimeter.

## Metrics

`/var/lib/node-textfile` holds Prometheus text files that root writes when a
job succeeds. node-exporter's textfile collector reads them. The directory is
`container_ro_file_t`, so a rootless container mounts it read-only without a
relabel. A service role may add its own files there.

| File | Metric | Written by |
|---|---|---|
| `snapshot-<service>.prom` | `snapshot_last_success_timestamp_seconds{service}` | `btrfs-snapshot@<service>` |
| `backup-<target>.prom` | `backup_last_success_timestamp_seconds{target}`, `backup_target_size_bytes`, `backup_target_avail_bytes` | `btrfs-backup@<target>` |

The first deploy writes each file with the deploy time, so a job that never
succeeds reads as stale 30 hours later.

## Variables

Every variable and its default is in `roles/base_setup/defaults/main.yml`.
The ones whose default is not the whole story:

| Var | Note |
|---|---|
| `base_setup_backup_targets` | `[]` means no off-box backup |
| `base_setup_iscsi_portal` | Set: the deploy logs in to the iSCSI target, with or without a backup target |
| `base_setup_luks_passphrase` | Required as soon as a backup target is set; keep a copy off the box |

## Design

`docs/DESIGN.md` says why these roles are shaped as they are.

## License

MIT
