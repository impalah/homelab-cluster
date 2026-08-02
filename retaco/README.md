# retaco — Nodo de datos y automatización (PostgreSQL + Qdrant + n8n-main + registry)

**IP:** `192.168.1.174`
**Hardware:** MiniPC Ryzen 5, 16 GB RAM, 512 GB disco

## Rol del nodo

`retaco` aloja los servicios de datos y automatización del clúster: **postgres-main** (multi-tenant — bases `n8n` y `sonarqube`, migradas desde `ryzen` y `pi-sonar` respectivamente), **qdrant** (migrado desde `ryzen`), **n8n-main** (migrado desde `ryzen`, co-localizado con `postgres-main`) y **registry** (registro Docker privado del clúster — imágenes de `apikey-service`/`markitdown-service`/`whisper-service`, publicadas desde `services/` en la raíz del repo mediante `make build`, nunca construidas por ningún nodo). Centraliza esto para dejar a `ryzen` dedicado solo a cómputo con GPU y a las Raspberry Pi dedicadas solo a ejecución — y para que las automatizaciones de n8n (cron, webhooks) sigan funcionando aunque `ryzen` esté parado, ya que `retaco` está siempre encendido. Ver `docs/05-instalacion-retaco.md` para el procedimiento completo de todas las migraciones y la instalación del registry (sección 5.3).

## Servicios

| Servicio | Puerto (host) | URL pública |
|---|---|---|
| postgres-main | 5432 | `postgresql.home.arpa:5432` (alias DNS directo, sin proxy — no es HTTP) |
| n8n-main | 5678 | https://n8n.home.arpa (proxy nginx en pi-dns) |
| qdrant | 6333 (127.0.0.1:6334 gRPC) | https://qdrant.home.arpa (proxy nginx en pi-dns) |
| registry | 5000 | https://registry.home.arpa (proxy nginx en pi-dns) — auth htpasswd propia, credenciales en Vaultwarden |
| node-exporter | 9100 | — (consultado por Prometheus en pi-obs) |
| cadvisor | 8081→8080 | — (consultado por Prometheus en pi-obs) |
| portainer-agent | 9001 | — (conectado al servidor Portainer en pi-utils) |

> `postgres-main` se publica en la LAN (5432) a propósito: `postgres-exporter` (en `pi-obs`) y `sonarqube` (en `pi-sonar`) necesitan alcanzarlo entre nodos. Protegido por contraseña fuerte, no por aislamiento de red — ver `docs/13-troubleshooting.md`. `n8n-main`, en cambio, está en este mismo nodo y conecta por nombre de contenedor (red `retaco-net`), sin pasar por la LAN.

## Arranque rápido

```bash
sudo bash /srv/homelab/shared/scripts/prepare-host.sh retaco
cp .env.example .env
nano .env    # Ajustar todos los CHANGE_ME

# Copiar el script de inicialización de PostgreSQL ANTES del primer arranque
# (el entrypoint oficial de la imagen postgres solo lo ejecuta la primera
# vez, con el volumen de datos vacío)
cp /srv/homelab/retaco/config/postgres/init/01-init-n8n.sh /srv/homelab/retaco/postgres/init/

docker compose up -d
docker compose ps
```

## Prerrequisitos

- Ubuntu Server 24.04 LTS (o Desktop, según prefieras) instalado en el MiniPC
- Docker Engine instalado (`shared/scripts/install-docker-ubuntu.sh`) — no hace falta NVIDIA Container Toolkit, este nodo no usa GPU
- IP estática asignada: `192.168.1.174`

## Estructura

```
retaco/
├── docker-compose.yml
├── .env.example
├── README.md
└── config/
    └── postgres/
        └── init/
            └── 01-init-n8n.sh   ← crea la BD/usuario de n8n en el primer arranque
```

## Notas

- `postgres-main` no es exclusivo de n8n — servidor compartido para varios proyectos, cada uno con su propia base de datos y usuario aislados (ver `shared/scripts/create-postgres-db.sh`). Actualmente aloja `n8n` (usada por `n8n-main`, en este mismo nodo) y `sonarqube` (usada por `sonarqube` en `pi-sonar`, cross-host).
- Este nodo no tiene GPU ni la necesita — postgres, qdrant y n8n-main son todos servicios de CPU/disco.
- `N8N_ENCRYPTION_KEY` **debe ser idéntica** a la que tenía `ryzen` antes de la migración — cambiarla deja ilegibles las credenciales ya guardadas en los workflows (irreversible).
- Copias de seguridad: `bash /srv/homelab/shared/scripts/backup-postgres.sh retaco postgres-main <n8n|sonarqube>` — una base a la vez, ver `docs/12-backups-y-restore.md`.
- Ver `docs/05-instalacion-retaco.md` para las migraciones completas desde `ryzen` y `pi-sonar`, incluyendo el traspaso de los datos existentes (no solo el despliegue en vacío).
