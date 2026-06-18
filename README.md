# ansible-base

Ansible playbook for base provisioning of a SecureBlue (FCOS) home server.

## Prerequisites

- Ansible Core 2.21+
- `community.general` collection (for `run0` become method)
- Fedora CoreOS 44+ (SecureBlue `securecore-main-hardened`)
- `run0` via polkit (default on SecureBlue — no sudo required)

## Architecture

Single playbook (`site.yml`) with 4 plays:

| Play | Role | Purpose |
|---|---|---|
| 1 | `base_setup` (this repo) | Btrfs subvolumes, service users, SELinux, Quadlet dirs, shared Podman network |
| 2 | `nextcloud_service` | Nextcloud Quadlet deployment *(external: service-nextcloud)* |
| 3 | `bunker_service` | Bunkerweb reverse proxy *(external: service-bunker)* |
| 4 | `monitoring_service` | Loki/Prometheus/Grafana stack *(external: service-monitoring)* |

Service roles live in separate repos and are referenced via `ansible.cfg` `roles_path`.

## Usage

```bash
# 1. Clone service repos alongside ansible-base:
#    ../service-nextcloud
#    ../service-bunker
#    ../service-monitoring

# 2. Configure inventory
cp inventory/hosts.ini.example inventory/hosts.ini
# edit inventory/hosts.ini with your target host details

# 3. Set secrets
cp secrets/vars.yml.example secrets/vars.yml
# edit secrets/vars.yml with passwords, tokens, etc.

# 4. Run
ansible-playbook -i inventory/hosts.ini site.yml --extra-vars "@secrets/vars.yml"
```

Variables are inherited from role defaults (`roles/base_setup/defaults/main.yml`)
and overridden via `vars.yml` in `deployment-private/secrets/vars.yml` (not public).

## File structure

```
ansible-base/
  ansible.cfg                 # Ansible config (run0, roles_path, SSH)
  site.yml                    # Main playbook
  .pre-commit-config.yaml     # Pre-commit hooks (yaml, lint, whitespace)
  scripts/
    ansible-syntax-check.sh  # Runs ansible-lint on playbook
  roles/
    base_setup/
      defaults/main.yml       # Variable defaults
      tasks/main.yml          # Subvolumes, users, SELinux, snapshots, network
      handlers/main.yml       # Snapshot service restart
      templates/
        btrfs-snapshot@.service.j2
        btrfs-snapshot@.timer.j2
      files/
        btrfs-snapshot-cleanup.sh
  inventory/
    hosts.ini.example         # Inventory template
  secrets/
    vars.yml.example          # Secrets template
  test/
    generate.sh               # SSH key + Butane config generation
    config.bu.template        # Butane ignition template
    start_vm.py               # QEMU VM launcher (stdlib only)
    deploy.sh                 # Quick deploy to test VM
```

## Security

- Privilege escalation via `community.general.run0` (no sudo binary needed)
- Rootless Podman with subuid/subgid ranges
- Port binding restricted to >= 80 via sysctl
- SELinux `container_file_t` contexts on service directories
- All secrets and inventory are `.gitignore`-protected

## License

MIT
