# pi-utils — Servicios de utilidades

**IP:** `192.168.1.173`  
**Hardware:** Raspberry Pi 5 (4 GB RAM)

## Servicios

| Servicio | Puerto (host) | URL pública |
|---|---|---|
| rsshub | 1200 | https://rsshub.home.arpa |
| markitdown-service | 8001 | https://markitdown.home.arpa (requiere API key — ver `docs/06-instalacion-pi1-dns.md`) |
| crawl4ai-scraper-service | 8002→8000 | https://crawl4ai.scraper.home.arpa (requiere API key — ver `docs/06-instalacion-pi1-dns.md`) |
| n8n-aux | 5679 | https://n8n-aux.home.arpa |
| portainer | 9000 | https://portainer.home.arpa (servidor Portainer del clúster, ver `docs/10-instalacion-pi4-utils.md`) |
| portainer-agent | 9001 | interno (usado por Portainer, no tiene URL propia) |
| node-exporter | 9100 | interno (consultado por Prometheus en pi-obs) |
| cadvisor | 8081 | interno (consultado por Prometheus en pi-obs) |
| vaultwarden | 8222 | https://vaultwarden.home.arpa (gestor de contraseñas del clúster, ver `docs/10-instalacion-pi4-utils.md`) |

> Los puertos publicados en `0.0.0.0` (no `127.0.0.1`) son a propósito: nginx (en pi-dns, un host distinto) necesita alcanzarlos por la LAN — ver `docs/13-troubleshooting.md`.

## Arranque rápido

```bash
sudo bash /srv/homelab/shared/scripts/prepare-host.sh pi-utils
cp .env.example .env
nano .env    # Ajustar N8N_AUX_ENCRYPTION_KEY y RSSHUB_ACCESS_KEY

# markitdown-service se publica en registry.home.arpa (services/markitdown-service/, make build) — aquí solo pull
docker login registry.home.arpa   # una sola vez
docker compose pull markitdown-service

# Arrancar todo
docker compose up -d
docker compose ps
```

## Estructura

```
pi-utils/
├── docker-compose.yml
├── .env.example
└── README.md
```

`markitdown-service` ya no tiene código bajo `pi-utils/` — vive en `services/markitdown-service/` (raíz del repo):

```
services/markitdown-service/
├── Dockerfile
├── Makefile
├── pyproject.toml
├── README.md
└── src/
    ├── __init__.py
    ├── config.py
    └── main.py
```

## Notas

- `n8n-aux` usa SQLite (no requiere PostgreSQL). Los flujos y credenciales se almacenan en `/srv/homelab/pi-utils/n8n-aux/data/`.
- `markitdown-service` se publica en `registry.home.arpa` desde `services/markitdown-service/` (`make build`, multi-arch amd64+arm64) — este nodo solo hace `docker compose pull markitdown-service && docker compose up -d markitdown-service` tras un cambio de código, nunca `build`.
- `crawl4ai-scraper-service` sigue el mismo patrón — publicado desde `services/crawl4ai-scraper-service/` (`make build`, multi-arch). Puerto host `8002` (no `8001`, ya usado por `markitdown-service`); el contenedor escucha siempre en `8000` internamente. Anti-bot (`CRAWL4AI_ENABLE_STEALTH_MODE`/`UNDETECTED_BROWSER`/`MAGIC_MODE`) activado en este nodo — ver `docs/10-instalacion-pi4-utils.md`.
- `rsshub` no requiere base de datos externa; usa caché en memoria.
- `vaultwarden` usa SQLite local, autocontenido (`/srv/homelab/pi-utils/vaultwarden/data/`) — es el servicio más sensible del clúster, tiene su propia copia de seguridad dedicada (`shared/scripts/backup-vaultwarden.sh`, no el de PostgreSQL). Ver `docs/10-instalacion-pi4-utils.md` para instalación, primer acceso y copia de seguridad.
- ⚠️ La imagen de `vaultwarden` necesita mantenerse al día con los clientes oficiales de Bitwarden (la extensión de navegador se actualiza sola, el servidor no) — si la extensión deja de mostrar las contraseñas tras sincronizar bien, es casi siempre un desajuste de versión. Ver `docs/13-troubleshooting.md`, sección Vaultwarden.
