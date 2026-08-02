# pi-dns — DNS + Proxy Inverso

**IP:** `192.168.1.170`  
**Hardware:** Raspberry Pi 5 (4 GB o 8 GB RAM)

## Servicios

| Servicio | Puerto (host) | Descripción |
|---|---|---|
| unbound | interno (172.20.0.2:5335) | Resolvedor DNS recursivo |
| pihole | 53/tcp, 53/udp, 127.0.0.1:8053 | DNS autoritativo + ad-block |
| nginx | 80, 443 | Proxy inverso HTTPS para el clúster + panel estático `index.home.arpa` |
| apikey-service | interno (172.20.0.9:8090) | Emisión/validación de API keys propias, usado por nginx mediante `auth_request` — ver `docs/06-instalacion-pi1-dns.md` |
| tailscale | `network_mode: host` | Subnet router — acceso remoto autenticado a toda la LAN + Split DNS de `*.home.arpa` — ver `docs/18-tailscale.md` |

## Arranque rápido

```bash
# 1. Deshabilitar systemd-resolved (obligatorio)
sudo systemctl stop systemd-resolved
sudo systemctl disable systemd-resolved
sudo rm /etc/resolv.conf
echo "nameserver 1.1.1.1" | sudo tee /etc/resolv.conf

# 2. Preparar directorios
sudo bash /srv/homelab/shared/scripts/prepare-host.sh pi-dns

# 3. Copiar configuraciones estáticas
cp config/unbound/unbound.conf /srv/homelab/pi-dns/unbound/config/
cp config/nginx/nginx.conf /srv/homelab/pi-dns/nginx/conf/
cp config/nginx/proxy-common.conf /srv/homelab/pi-dns/nginx/conf/
cp config/nginx/apikey-auth.conf /srv/homelab/pi-dns/nginx/conf/

# 4. Generar el certificado TLS (necesario antes del primer arranque)
bash config/nginx/generate-cert.sh

# 5. Arrancar stack
cp .env.example .env
nano .env    # Ajustar PIHOLE_PASSWORD, APIKEY_DATABASE_URL, APIKEY_ADMIN_TOKEN
docker login registry.home.arpa   # una sola vez — apikey-service se publica en el registry, no se construye aquí
docker compose pull apikey-service
docker compose up -d
docker compose ps
```

> `apikey-service` necesita su base de datos creada de antemano en `postgres-main` (retaco) — ver `docs/06-instalacion-pi1-dns.md` sección "Despliegue" antes del primer arranque.

## Post-arranque

Añadir los registros DNS en Pi-hole (primer acceso vía túnel SSH, ver `docs/06-instalacion-pi1-dns.md` sección 7.1):
→ `http://localhost:8053/admin` (con `ssh -L 8053:127.0.0.1:8053 u-dns@192.168.1.170`) → **Settings → DNS Records** (Pi-hole v6)

Más rápido que añadirlos uno a uno: cargar la tabla completa por API con `shared/scripts/load-dns-records.sh` (detalle en `docs/06-instalacion-pi1-dns.md` sección 7.1).

Ver la tabla completa en: `shared/dns/dns-records.md`

Para acceder por nombre de host (`https://grafana.home.arpa`, etc.) desde tu PC de gestión **sin** cambiar aún el DNS del router: `docs/06-instalacion-pi1-dns.md` sección 8.1 (configuración temporal reversible, solo afecta a tu equipo). El cambio definitivo a nivel de router (afecta a toda la red) es el paso 8 del mismo documento.

## Estructura de archivos

```
pi-dns/
├── docker-compose.yml
├── .env.example
├── README.md
└── config/
    ├── unbound/
    │   └── unbound.conf       ← configuración del resolvedor recursivo
    └── nginx/
        ├── nginx.conf          ← proxy inverso para todos los servicios
        ├── proxy-common.conf   ← cabeceras comunes (incl. soporte WebSocket)
        ├── apikey-auth.conf    ← snippet auth_request para proteger un servicio con API key
        ├── generate-ca.sh      ← genera la CA raíz interna (una sola vez)
        ├── generate-cert.sh    ← genera/regenera el certificado TLS, firmado por la CA
        └── html/
            ├── index.html      ← panel de acceso a los servicios (index.home.arpa)
            └── icons/          ← logos de cada servicio (SVG/PNG, servidos localmente)

```

`apikey-service` ya no tiene código bajo `pi-dns/` — vive en `services/apikey-service/` (raíz del repo) y se publica en `registry.home.arpa` mediante `make build` (multi-arch amd64+arm64, esta Pi lo necesita); este nodo solo hace `image:` + `pull` (`docs/06-instalacion-pi1-dns.md`, `docs/05-instalacion-retaco.md` sección 5.3):

```
services/apikey-service/
├── Dockerfile
├── pyproject.toml
└── src/apikey_service/
    ├── controllers/    ← routers FastAPI (HTTP in/out)
    ├── services/       ← reglas de negocio (hash/validación/revocado de keys)
    └── repositories/   ← acceso a datos (SQLAlchemy + asyncpg)
```

## Panel de servicios (`index.home.arpa`)

Página estática (HTML + CSS puro, sin JS ni frameworks) servida directamente por nginx — no es un proxy, `nginx` sirve los ficheros de `config/nginx/html/` con `root`/`try_files`. Una tarjeta por servicio con interfaz web real (no incluye APIs sin interfaz como Ollama o Whisper-service), cada una enlaza a su `https://*.home.arpa` en una pestaña nueva. No se limita a servicios del propio clúster: el NAS UGREEN (`ketekasko`, fuera del clúster Docker) también tiene su tarjeta aquí, enlazando directamente a `https://ketekasko.home.arpa:9443` — ver `docs/21-configuracion-nas-ugreen.md`.

**Añadir un servicio nuevo a la lista:**
1. Copiar un icono a `config/nginx/html/icons/` (buscar el SVG oficial en [simple-icons](https://simpleicons.org) o el logo del propio proyecto en su repositorio de GitHub).
2. Añadir una tarjeta `<a class="card">` nueva en `config/nginx/html/index.html`, copiando la estructura de una existente.
3. Desplegar: `rsync -av config/nginx/html/ u-dns@192.168.1.170:/srv/homelab/pi-dns/nginx/html/` — no hace falta reiniciar nginx (son ficheros estáticos, se sirven directo del disco).

## Notas

- nginx usa un certificado firmado por una **CA interna propia** (`config/nginx/generate-ca.sh` + `generate-cert.sh`), válido 10 años por defecto — no es Let's Encrypt, ya que `*.home.arpa` no es un dominio público. Instalando el certificado de la CA en cada dispositivo (una vez, ver `docs/15-ca-interna.md`) desaparecen los avisos del navegador para siempre, incluso al regenerar el certificado de servicio. Sin instalarla, sigue funcionando con `-k`/`--insecure` en `curl` o aceptando la excepción manualmente.
- Pi-hole expone su web en `127.0.0.1:8053` (no directamente en 80) para evitar conflicto con nginx.
- El orden de arranque está gestionado por `depends_on`: unbound → pihole → nginx; `apikey-service` arranca en paralelo a pihole (sin depender de él) pero nginx espera a que ambos estén `healthy` antes de arrancar, porque su `auth_request` los necesita.
- Regenerar el certificado de servicio (nuevo nombre de host, rotación, etc.): ver `docs/06-instalacion-pi1-dns.md` sección 11. La CA en sí casi nunca hace falta regenerarla — ver aviso en `docs/15-ca-interna.md`.
