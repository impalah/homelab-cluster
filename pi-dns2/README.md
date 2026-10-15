# pi-dns2 — DNS de respaldo del clúster

**IP:** `192.168.10.3` (reserva DHCP en el R700, no se configura IP local)
**Hardware:** Raspberry Pi 5 (arm64), Ubuntu 26.04
**Antes:** `pi-utils` (hasta 2026-10-15; el nombre antiguo sigue resolviendo como alias transitorio)

Segundo Pi-hole + Unbound, equivalente al de `pi-dns` (`192.168.10.2`): si uno cae, el otro mantiene la resolución de `*.404labo.net` y de Internet. Es el **secundario** que el servidor DHCP del R700 entrega a los clientes (mejora 55 de `docs/22-mejoras-futuras.md`). Arquitectura, incidente que lo motivó y checklist: `docs/41-dns-pihole-unbound.md`.

Está **fuera del Swarm**, igual que `pi-dns`.

## Servicios (`docker-compose.yml`, red `pi-dns-net` 172.20.0.0/24, IP fijas)

| Servicio | IP | Puerto (host) | Notas |
|---|---|---|---|
| unbound | 172.20.0.2 | — (5335 interno) | Resolvedor recursivo, upstream de Pi-hole. Misma `unbound.conf` que `pi-dns` |
| pihole | 172.20.0.3 | 53/tcp+udp, 8053 (panel/API) | Upstream `172.20.0.2#5335`, DNSSEC según `PIHOLE_DNSSEC` |
| nut-upsmon | 172.20.0.4 | — | Cliente NUT: apaga el host si el SAI lo ordena (`docs/33-nut-sai.md`) |
| node-exporter | 172.20.0.5 | 9100 | Métricas del host + `dns-guard.prom` |
| watchtower | 172.20.0.8 | — | Solo contenedores con la etiqueta de auto-actualización (ninguno hoy) |

Panel de Pi-hole directamente en la LAN: `http://192.168.10.3:8053/admin` (sin proxy ni hostname).

## Diferencias con `pi-dns`

- Sin servidor NUT (el SAI y su cable USB están en `pi-dns`) ni subnet router de Tailscale.
- Sin cadvisor ni portainer-agent.
- **Registros locales**: no se editan a mano. `shared/scripts/load-dns-records.sh` aplica la misma lista del repo a los dos Pi-hole:

```bash
PIHOLE_PASSWORD=... PIHOLE_URLS="http://192.168.10.2:8053 http://192.168.10.3:8053" \
  bash shared/scripts/load-dns-records.sh
```

La contraseña de la API es la misma en ambos (`PIHOLE_PASSWORD` de cada `.env`).

## Despliegue

El directorio real del nodo es `/srv/homelab/pi-dns2/` (`docker-compose.yml`, `.env` modo 600 propiedad de `admin`, `unbound/config/unbound.conf`, `pihole/`). Se actualiza con `/tmp` + `sudo cp` (docs/38). Si se cambia `unbound.conf`, cambiarlo también en `pi-dns/config/unbound/` (son copias).

```bash
cd /srv/homelab/pi-dns2
docker compose up -d
docker compose ps
```

## Resolución del propio nodo

`systemd-resolved` está deshabilitado (Pi-hole ocupa el 53). `/etc/resolv.conf` apunta a `127.0.0.1` (su Pi-hole) y, como respaldo para el arranque, a `192.168.10.2`.

## Guardián de Unbound

`shared/scripts/dns-guard.sh` en el cron de `admin` (cada minuto, log en `/var/log/homelab-dns-guard.log`): Docker no reintenta `unbound` si falla su red en el arranque. Escribe `/srv/homelab/node-exporter-textfile/dns-guard.prom`; las alertas de `pi-obs/config/grafana/alerting/dns.yml` vigilan esas métricas en los dos nodos.

## Comprobación

```bash
bash shared/scripts/check-health.sh pi-dns2          # ejecutar EN el nodo
bash shared/scripts/fix-dns-resolver.sh pi-dns2      # prueba funcional de resolución
dig +short registry.404labo.net @192.168.10.3
```

## Datos heredados de `pi-utils`

`/srv/homelab/pi-dns2/` conserva carpetas de cuando era `pi-utils` (`capataz`, `rsshub`, `n8n-aux`, `portainer`, `vaultwarden`, `infisical-cli`, ~150 MB): esos servicios ya viven en el Swarm, pero **no se han borrado** por si alguna fuese la única copia. Revisar y limpiar a mano.

## Estructura del repo

```
pi-dns2/
├── docker-compose.yml
├── .env.example
├── config/unbound/unbound.conf
└── README.md
```
