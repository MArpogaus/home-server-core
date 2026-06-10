# ansible-base

System configuration for a Podman Quadlet server: Btrfs subvolumes, automated snapshots, SELinux policies, and user management.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  ansible-base (System Configuration)                │
│                                                     │
│  base_setup          Btrfs users, snapshots, SELinux│
│  service_deploy      Deploy Quadlet files to users  │
│                                                     │
│  Services deployed:                                 │
│    - nextcloud (service-nextcloud)                  │
│    - proxy / bunker  (service-bunker)               │
└─────────────────────────────────────────────────────┘
```

## Quick Start

1. Configure inventory:
   ```bash
   cp inventory/hosts.ini.example inventory/hosts.ini
   # Edit with your server IP and user
   ```

2. Install Galaxy dependencies:
   ```bash
   ansible-galaxy install -r requirements.yml
   ```

3. Run the playbook:
   ```bash
   ansible-playbook -i inventory/hosts.ini site.yml
   ```

4. Verify:
   ```bash
   # Check Btrfs snapshots
   btrfs subvolume list /snapshots

   # Check SELinux labels
   ls -Z /home/nextcloud
   ls -Z /home/proxy

   # Check container services
   systemctl --user list-units --type=service | grep -E '(nextcloud|bunker)'
   podman ps
   ```

## Roles

### base_setup
- Installs podman, btrfs-progs, SELinux tools
- Creates users (nextcloud, proxy)
- Creates Btrfs subvolumes with SELinux labels
- Deploys daily snapshot timers
- Runs snapshot cleanup script (30-day retention)

### service_deploy
- Deploys Quadlet `.container`, `.volume`, `.network` files
- Deploys config files (nginx, php configs for Nextcloud)
- Reloads systemd user daemon
- Enables and starts services

## Variables

See `defaults/main.yml` and `group_vars/all.yml` for configurable variables.

## Snapshot Configuration

- **Schedule:** Daily (via systemd timer)
- **Retention:** 30 days (configurable via `btrfs_snapshot_retention_days`)
- **Location:** `/snapshots/<volume>/<YYYY-MM-DD>/`
- **Type:** Read-only snapshots
