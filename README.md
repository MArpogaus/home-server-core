# SecureBlue Ansible Deployment

Ansible Playbooks for automating SecureBlue deployments with Fedora CoreOS.

## Architecture

```
+-------------------------------------------------------------+
|                    SecureBlue VM (KVM/QEMU)                  |
|  +-------------------------------------------------------+  |
|  |  Fedora CoreOS 44 -> rpm-ostree rebase -> SecureBlue |  |
|  |  +-------------------------------------------------+ |  |
|  |  |  Btrfs Rootfs                                   | |  |
|  |  |  +- /var/services/nextcloud (subvolume)        | |  |
|  |  |  +- /var/services/proxy (subvolume)            | |  |
|  |  |  +-- /var/services/snapshots (subvolume)       | |  |
|  |  |                                                  | |  |
|  |  |  Service Accounts:                               | |  |
|  |  |  +- nextcloud (UID 82)                          | |  |
|  |  |  +-- proxy (UID 1001)                           | |  |
|  |  |                                                  | |  |
|  |  |  Quadlet Services (user-level systemd):         | |  |
|  |  |  +- nextcloud-{app,cron,db,redis,web,...}       | |  |
|  |  |  +-- bunker-{nginx,scheduler}                   | |  |
|  |  |                                                  | |  |
|  |  |  Privilege Escalation:                          | |  |
|  |  |  +-- run0 + Polkit (no sudo)                    | |  |
|  |  +-------------------------------------------------+ |  |
|  +-------------------------------------------------------+  |
+-------------------------------------------------------------+
```

## Repository Structure

```
ansible-base/
├── .github/workflows/
│   └── test-secureblue-deploy.yaml  # GitHub Actions CI
├── inventory/
│   └── hosts.ini.example            # Host configuration (template)
├── roles/
│   └── base_setup/                  # Btrfs, users, SELinux, snapshots
│       ├── defaults/
│       ├── files/
│       ├── handlers/
│       ├── tasks/
│       └── templates/
├── secrets/
│   └── vars.yml.example             # Private secrets (template)
├── test/
│   ├── config.bu                    # Butane ignition config
│   ├── start_vm.py                  # VM launcher (Python stdlib)
│   └── deploy.sh                    # Quick deploy script
├── ansible.cfg                      # Ansible configuration
├── site.yml                         # Main playbook
└── README.md

External roles (in separate repos):
├── service-nextcloud/ansible-role/nextcloud_service/
└── service-bunker/ansible-role/bunker_service/
```

## Quick Start

### 1. Start VM (test environment)

```bash
cd test
./deploy.sh
```

Or manually:

```bash
# Generate SSH key
ssh-keygen -t ed25519 -f coreos_key -N ""

# Generate Butane config
podman run --rm -i quay.io/coreos/butane:release < config.bu > config.ign

# Start VM
python3 start_vm.py
```

### 2. Run Ansible playbook

```bash
# Configure private secrets
cp secrets/vars.yml.example secrets/vars.yml
# Edit secrets/vars.yml with your values

# Configure inventory
cp inventory/hosts.ini.example inventory/hosts.ini
# Edit inventory/hosts.ini

# Run playbook
ansible-playbook -i inventory/hosts.ini site.yml \
  --extra-vars "@secrets/vars.yml"
```

## Secrets Management

**IMPORTANT:** Private secrets must NOT be committed to the repository!

### Required secrets:

```yaml
# secrets/vars.yml
ssh_key_path: "../test/coreos_key"
ghcr_username: "your-username"
ghcr_token: "your-token"
domain: "cloud.your-domain.de"
```

### .gitignore protects against accidental commits:

```
secrets/vars.yml
inventory/hosts.ini
*.key
*.pub
```

## Service Roles

Service-specific Ansible roles are in separate repositories:

- **service-nextcloud** - Nextcloud Quadlet deployment
- **service-bunker** - Bunkerweb Quadlet deployment

Roles are automatically included via `ansible.cfg` roles_path.

### Usage

```yaml
# site.yml
- hosts: all
  roles:
    - base_setup
    - nextcloud_service
    - bunker_service
```

See respective repositories for role documentation:
- `../service-nextcloud/ansible-role/README.md`
- `../service-bunker/ansible-role/README.md`

## CI/CD

GitHub Actions workflow tests:
- VM boot with QEMU
- Ansible playbook execution
- Btrfs subvolume creation
- Service account setup
- SELinux contexts
- Snapshot timers
- Quadlet file deployment

Workflow runs automatically on `push` to `dev` or `PR`.

## Requirements

### Local (for development)

- Podman (for Butane)
- Python 3.10+
- Ansible Core 2.21+
- community.general 13.0.1+

### Target system

- Fedora CoreOS 44.20260510.3.1 or newer
- SecureBlue `securecore-main-hardened`
- KVM/QEMU virtualization
- 4GB+ RAM, 20GB+ storage

## Configuration

### Butane Ignition (`test/config.bu`)

- SSH key injection
- Polkit rule for `run0`
- Network configuration (NAT + port forwarding)
- Btrfs rootfs

### Ansible variables

All variables are defined in role defaults or passed via playbook.

## Validation

```bash
# Btrfs subvolumes
systemd-run --wait --unit=tmp-check /usr/bin/btrfs subvolume list /var/services

# Service accounts
getent passwd nextcloud proxy

# SELinux contexts
ls -Zd /var/services/nextcloud /var/services/proxy

# Snapshot timers
systemctl list-timers --all | grep btrfs-snapshot

# Quadlet files
ls /var/services/nextcloud/.config/systemd/user/*.container
```

## Troubleshooting

See [Agent.md](../Agent.md) for detailed troubleshooting.

## References

- [REQUIREMENTS.md](../REQUIREMENTS.md) - Project requirements
- [service-nextcloud](../service-nextcloud/) - Nextcloud container
- [service-bunker](../service-bunker/) - Bunkerweb container
- [deployment-private](../deployment-private/) - Private deployment config

## License

MIT - See LICENSE file
