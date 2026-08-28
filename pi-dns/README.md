# pi-dns — DNS

**IP:** `192.168.1.170`  
**Hardware:** Raspberry Pi 5 (4 GB o 8 GB RAM)

> ⚠️ **`nginx` y la copia local de `apikey-service` se decomisionaron al cerrar la mejora 41**
> (2026-08-28, `docs/22-mejoras-futuras.md`) — Traefik, en el Swarm, es el proxy inverso del
> clúster ahora (`docker-swarm/stacks/traefik/`); `apikey-service` tiene su propia instancia
> canónica en el Swarm (`docker-swarm/stacks/apikey-service/`). Este nodo queda deliberadamente
> **fuera** del Swarm — solo DNS + Tailscale. La config de `nginx` se conserva bajo `config/nginx/`
> como referencia histórica, marcada como retirada, nunca desplegada.

## Servicios

| Servicio | Puerto (host) | Descripción |
|---|---|---|
| unbound | interno (172.20.0.2:5335) | Resolvedor DNS recursivo |
| pihole | 53/tcp, 53/udp, `8053` (LAN, sin proxy desde el cierre de la mejora 41) | DNS autoritativo + ad-block — panel en `http://192.168.1.170:8053` |
| tailscale | `network_mode: host` | Subnet router — acceso remoto autenticado a toda la LAN + Split DNS de `*.404labo.net` — ver `docs/18-tailscale.md` |

## Arranque rápido

```bash
# 1. Deshabilitar systemd-resolved (obligatorio)
sudo systemctl stop systemd-resolved
sudo systemctl disable systemd-resolved
sudo rm /etc/resolv.conf
echo "nameserver 1.1.1.1" | sudo tee /etc/resolv.conf

# 2. Preparar directorios
sudo bash /srv/homelab/shared/scripts/prepare-host.sh pi-dns

# 3. Copiar configuración estática
cp config/unbound/unbound.conf /srv/homelab/pi-dns/unbound/config/

# 4. Arrancar stack
cp .env.example .env
nano .env    # Ajustar PIHOLE_PASSWORD
docker compose up -d
docker compose ps
```

## Post-arranque

Añadir los registros DNS en Pi-hole: `http://192.168.1.170:8053/admin` → **Settings → DNS Records**
(Pi-hole v6).

Más rápido que añadirlos uno a uno: cargar la tabla completa por API con
`shared/scripts/load-dns-records.sh` (`PIHOLE_URL` por defecto ya apunta a
`http://192.168.1.170:8053`).

Ver la tabla completa en: `shared/dns/dns-records.md`

## Estructura de archivos

```
pi-dns/
├── docker-compose.yml
├── .env.example
├── README.md
└── config/
    ├── unbound/
    │   └── unbound.conf       ← configuración del resolvedor recursivo
    └── nginx/                  ← RETIRADO (mejora 41) -- referencia histórica, nunca desplegado
        ├── nginx.conf          ← marcado retirado en cabecera
        ├── proxy-common.conf
        ├── apikey-auth.conf
        ├── authentik-auth.conf
        ├── generate-ca.sh      ← SIGUE ACTIVO -- Valkey (docker-swarm/stacks/valkey/) sigue
        │                          firmando su cert TLS con esta CA, único consumidor que queda
        ├── generate-cert.sh    ← retirado (cert de *.home.arpa, ya nadie lo usa)
        ├── generate-valkey-cert.sh ← SIGUE ACTIVO -- regenera el cert de Valkey (CN=valkey.404labo.net)
        └── html/               ← panel estático original, retirado (superseded por Capataz, mejora 15)
```

`apikey-service` ya no tiene código bajo `pi-dns/` ni un contenedor propio aquí — vive en `services/apikey-service/` (raíz del repo), se publica en `registry.404labo.net` mediante `make build` (multi-arch amd64+arm64), y su instancia canónica corre en el Swarm (`docker-swarm/stacks/apikey-service/`), alcanzable por routing mesh en `http://<nodo-swarm>:8091` para gestión administrativa directa.

## Notas

- `generate-ca.sh`/`generate-valkey-cert.sh` son los dos únicos scripts de `config/nginx/` que
  siguen activos — todo lo demás ahí (nginx en sí, `generate-cert.sh`, el panel estático) quedó
  retirado al cerrar la mejora 41, conservado solo como referencia histórica. Ver
  `docs/15-ca-interna.md` para el estado actual de la CA interna (vigencia reducida a Valkey).
- Pi-hole publica su panel directo en `192.168.1.170:8053`, sin proxy delante, desde el mismo
  cierre.
