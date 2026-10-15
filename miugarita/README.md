# miugarita

**IP:** `192.168.10.9` (reserva DHCP) · **Usuario SSH:** `admin` (`docs/38-acceso-ssh-nodos.md`) · **Rol:** nodo del Swarm (`retaco` + `pinchi` + `miugarita`)

Mini PC, mismo hardware que `pinchi` (8 CPU, 12 GB RAM, 468 GB NVMe). Alta en `docs/39-instalacion-miugarita.md`.

## Qué corre aquí

| Qué | Cómo |
|---|---|
| Observabilidad (Loki, Tempo, Prometheus, Grafana, otel-collector, exporters) | Stack Swarm `pi-obs` (`docker-swarm/stacks/pi-obs/`), fijado a este nodo. Datos en `/srv/homelab/observability/` |
| SonarQube | Stack Swarm `sonarqube`, fijado a este nodo. Índice en `/srv/homelab/sonarqube/data` |
| node-exporter / cadvisor | Stack Swarm `common` (global) |
| Cualquier servicio sin nodo fijo | Swarm lo coloca donde toque |
| `nut-upsmon` | Compose clásico (`docker-compose.yml` de este directorio) -- cliente del SAI |

## Prerrequisitos que no vienen del Swarm (se olvidan fácil)

- Plugin de logging `loki` instalado (`docker plugin install grafana/loki-docker-driver:latest --alias loki --grant-all-permissions`): sin él, ningún servicio con `logging: driver: loki` arranca aquí ("missing plugin").
- `/srv/homelab/infisical/infisical-cli/` (binario compartido de Infisical, `deploy-infisical-cli.sh shared`) y `/srv/homelab/valkey/{users.acl,tls}` (por si Valkey cae aquí).
- `/srv/homelab/node-exporter-textfile` propiedad de `admin` (si no, `check-*-updates.sh` no puede escribir).
- NFS montado en `/mnt/nfs-data` (`/etc/fstab`).
- Login a `registry.404labo.net` para `admin` (lo usa `check-image-updates.sh`).

## Despliegue del cliente del SAI

```bash
ssh admin@192.168.10.9
cd /srv/homelab/miugarita && cp .env.example .env   # poner NUT_MONUSER_PASSWORD real
docker compose up -d --build nut-upsmon
```
