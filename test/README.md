# Fedora CoreOS Test-VM

## Schnellstart

```bash
# 1. VM starten (KVM, headless, Port-Forwarding SSH auf 2222)
python3 start_vm.py

# 2. Deployment spielen (in neuem Terminal)
./deploy.sh

# 3. Auf der VM prüfen
ssh core@localhost -p 2222
podman info
systemctl --user list-unit-files | grep nextcloud
```

## Dateien

| File | Zweck |
|---|---|
| `start_vm.py` | Lädt FCOS-Image, kompiliert Butane→Ignition, startet VM mit KVM |
| `config.bu` | Butane-Konfiguration (YAML) für Fedora CoreOS |
| `config.ign` | Generierte Ignition-Konfiguration (JSON) — wird automatisch aus `config.bu` |
| `deploy.sh` | Spielt ansible-base `site.yml` gegen die VM |
| `marpogaus.pub` | GHCR-Signing-Key (cosign.pub) |

## Butane-Konfiguration

Die Ignition-Konfiguration wird mit **Butane** generiert (offizielles FCOS-Tool):

```bash
# Butane als Container
podman run --rm -i -v "${PWD}:/pwd" -w /pwd quay.io/coreos/butane:release --pretty --strict config.bu > config.ign

# Oder Butane-Binary (falls installiert)
butane --pretty --strict config.bu > config.ign
```

`start_vm.py` führt diesen Schritt automatisch aus.

## Architektur

```
Container → localhost:2222 → QEMU Port-Forward → VM:22 (SSH)
```

QEMU nutzt `user` network mode (NAT) — keine Bridge-Interfaces nötig.

## VM stoppen

Im QEMU-Terminal: **Ctrl+C**

## Voraussetzungen

- `qemu-system-x86_64` (KVM)
- `/dev/kvm` existiert
- `python3` (stdlib only, keine externen Dependencies)
- `podman` oder `butane` Binary (für Ignition-Konfig-Generierung)
- `unxz` (für FCOS-Image-Entpacken)
