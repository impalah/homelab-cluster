# homelab-cluster

Infraestructura doméstica distribuida en 7 nodos: tres PCs (Ryzen 9, MiniPC Ryzen 5 y GMKtec NucBox G10 Pro) y 4 Raspberry Pi 5. Orquestada con **Docker Swarm** (5 nodos manager: retaco/pi-obs/pi-sonar/pi-utils/pinchi) — sin Kubernetes. `pi-dns` queda deliberadamente fuera del Swarm (solo DNS + Tailscale); `ryzen` también queda fuera (Compose clásico, es el único nodo que se apaga habitualmente). Ver `docs/31-docker-swarm.md` y `docker-swarm/README.md` para el detalle. Todo el clúster resuelve bajo el dominio propio `404labo.net` (split-horizon, solo dentro de la LAN — ver "Dominio y DNS" más abajo). Además del clúster, la misma LAN aloja un NAS UGREEN (`ketekasko`) que no está gestionado por Docker — ver la sección "NAS UGREEN" más abajo.

---

## Nodos

| Nodo               | IP              | Swarm            | Función principal                                    |
|--------------------|-----------------|------------------|------------------------------------------------------|
| ryzen.404labo.net  | 192.168.1.150   | fuera (Compose)  | IA con GPU: Ollama, Whisper, Open WebUI               |
| retaco.404labo.net | 192.168.1.174   | manager          | Datos y automatización: Postgres main, Qdrant, n8n-main, Authentik, Valkey, Infisical |
| pi-dns.404labo.net | 192.168.1.170   | fuera            | DNS (Pi-hole + Unbound) + Tailscale subnet router — sin nginx, sin apikey-service |
| pi-obs.404labo.net | 192.168.1.171   | manager          | Observabilidad (OTel, Prometheus, Grafana, Loki, Tempo) |
| pi-sonar.404labo.net| 192.168.1.172  | manager          | SonarQube, Bifrost (base de datos en retaco)          |
| pi-utils.404labo.net| 192.168.1.173  | manager          | Utilidades: RSSHub, markitdown-service, crawl4ai-scraper-service, n8n-aux, Vaultwarden, Capataz |
| pinchi.404labo.net | 192.168.1.175   | manager          | Nodo Swarm de propósito general (añadido 2026-08-22, `docs/30-instalacion-pinchi.md`) — sin servicios pinnados propios, recibe carga vía routing mesh |

---

## Servicios expuestos por nombre de host

Todos servidos por Traefik (`docker-swarm/stacks/traefik/`), con un certificado wildcard real de
Let's Encrypt para `*.404labo.net` (renovado y rotado automáticamente — `shared/scripts/
renew-letsencrypt.sh` + `shared/scripts/deploy-traefik-cert.sh`). Split-horizon: estos hostnames
**resuelven solo en la LAN interna** (Pi-hole) — no hay ningún registro A público para
`404labo.net`, así que no hay superficie expuesta a internet. `<nodo swarm>` es cualquiera de los 5
managers (routing mesh, `mode: global`) — normalmente responde `pinchi` por convención, no porque
el servicio "viva" ahí.

| Hostname                    | Nodo real del backend | Puerto upstream |
|-----------------------------|------------------------|-----------------|
| home.404labo.net            | pi-utils.404labo.net   | 8090 (capataz-frontend) |
| capataz-api.404labo.net     | pi-utils.404labo.net   | 8000            |
| openwebui.404labo.net       | retaco.404labo.net     | 8080            |
| n8n.404labo.net             | retaco.404labo.net     | 5678            |
| ollama.404labo.net          | ryzen.404labo.net      | 11434           |
| vllm.404labo.net            | ryzen.404labo.net      | 8010            |
| comfyui.404labo.net         | ryzen.404labo.net      | 8188            |
| qdrant.404labo.net          | retaco.404labo.net     | 6333            |
| whisper.404labo.net         | ryzen.404labo.net      | 9800            |
| grafana.404labo.net         | pi-obs.404labo.net     | 3000            |
| prometheus.404labo.net      | pi-obs.404labo.net     | 9090            |
| sonarqube.404labo.net       | pi-sonar.404labo.net   | 9000            |
| bifrost.404labo.net         | pi-sonar.404labo.net   | 8080            |
| rsshub.404labo.net          | pi-utils.404labo.net   | 1200            |
| markitdown.404labo.net      | pi-utils.404labo.net   | 8001            |
| crawl4ai.scraper.404labo.net| pi-utils.404labo.net   | 8002            |
| n8n-aux.404labo.net         | pi-utils.404labo.net   | 5679            |
| portainer.404labo.net       | pi-utils.404labo.net   | 9000            |
| vaultwarden.404labo.net     | pi-utils.404labo.net   | 8222            |
| registry.404labo.net        | retaco.404labo.net     | 5000            |
| epub2pdf.404labo.net        | retaco.404labo.net     | 8003            |
| pdf2chunks.404labo.net      | retaco.404labo.net     | 8004            |
| open-terminal.404labo.net   | retaco.404labo.net     | 8005            |
| infisical.404labo.net       | retaco.404labo.net     | 8006            |
| authentik.404labo.net       | retaco.404labo.net     | 9000            |

`home.404labo.net` sirve el frontend de **Capataz** (consola de estado y automatización del
clúster) — contenedor propio (`capataz-frontend`) en `pi-utils`, junto a `capataz-api`/
`capataz-runner`. `capataz-api` tiene también su propio hostname en vez de exponerse solo por
IP:puerto — lo usa el propio `capataz-frontend` para reenviar `/api/`. Ver
`docs/28-capataz-consola-automatizacion.md`.

Tres hostnames que existían bajo `home.arpa` se retiraron sin sustituto al cerrar la mejora 41
(2026-08-28), por diseño: `pihole` (panel publicado directo en la LAN por IP:puerto,
`http://192.168.1.170:8053`, sin proxy), `apikey` (gestión de API keys por IP:puerto directo a
`http://192.168.1.175:8091`) y `old.index` (panel estático original, superseded por Capataz desde
la mejora 15). Ver `docs/22-mejoras-futuras.md` y `docs/31-docker-swarm.md` para el detalle
completo del cierre.

---

## Dominio y DNS

Todo el clúster resuelve bajo `404labo.net` (dominio real, delegado en Route53 solo para el reto
DNS-01 del certificado wildcard) — `home.arpa` se usó hasta el cierre de la mejora 41
(2026-08-28) y ya no queda ninguna referencia funcional a él. Split-horizon: Pi-hole resuelve
`*.404labo.net` solo dentro de la LAN, a IPs privadas; Route53 nunca recibe un registro para
ningún subdominio — solo el TXT temporal `_acme-challenge.404labo.net` durante la renovación del
certificado. TLS real de Let's Encrypt en todo el clúster, sin CA interna que instalar en los
dispositivos cliente salvo para el único servicio que todavía la usa (Valkey, ver
`docs/25-valkey-cache.md`). Ver `shared/dns/dns-records.md` para la tabla completa de registros y
`docs/22-mejoras-futuras.md` (mejora 41) para la historia de la migración.

---

## Acceso remoto (fuera de la LAN)

El acceso remoto se realiza mediante Tailscale, con un subnet router en `pi-dns` que da acceso autenticado a toda la LAN, incluida la resolución de `*.404labo.net` (Split DNS). Ver `docs/18-tailscale.md`.

---

## Wake-on-LAN

`ryzen` (alias `mole`) puede apagarse cuando no se usa y encenderse remotamente desde otro nodo del clúster — ver `docs/19-wake-on-lan.md`.

---

## NAS UGREEN (`ketekasko`)

Dispositivo LAN adicional (`192.168.1.180`, UGOS Pro) — no forma parte del clúster Docker, pero resuelve por DNS (`ketekasko.404labo.net`) y tiene tarjeta en `home.404labo.net`. SMB, NFSv3 y carpetas compartidas — ver `docs/21-configuracion-nas-ugreen.md`.

---

## Arranque rápido

**Servicios en el Swarm** (la mayoría — `docker-swarm/stacks/<name>/`), desde un nodo manager
(retaco/pi-obs/pi-sonar/pi-utils/pinchi):

```bash
docker stack deploy -c docker-swarm/stacks/<name>/docker-compose.yml <name> --with-registry-auth
docker service ls   # confirmar réplicas N/N
```

**Servicios todavía en Compose clásico** (ryzen, pi-dns, y lo que quede sin migrar en retaco/
pi-obs/pi-sonar/pi-utils), en cada nodo:

```bash
cd /srv/homelab/<node>
cp <node>/.env.example <node>/.env
# editar .env con contraseñas reales
docker compose up -d
```

Ver `docs/` para guías completas por nodo, y `docker-swarm/README.md` para el flujo de trabajo con stacks.

---

## Estructura del proyecto

```
homelab-cluster/
├── README.md
├── docs/               ← Documentación completa
├── docker-swarm/       ← Stacks de Docker Swarm (docker stack deploy) -- Traefik, Authentik,
│                          apikey-service, y la mayoría de los servicios que antes vivían por nodo
├── services/           ← apikey-service, markitdown-service, whisper-service (build/push propio)
├── shared/
│   ├── env/            ← .env.example por nodo
│   ├── scripts/        ← Scripts de instalación y operación
│   └── dns/            ← Documentación DNS y registros
├── ryzen/              ← Stack IA + pipeline principal (Compose clásico, fuera del Swarm)
├── retaco/             ← Mayormente histórico -- registry es lo único que sigue en Compose clásico
├── pi-dns/             ← DNS local (Pi-hole + Unbound) + Tailscale -- fuera del Swarm, sin nginx
├── pi-obs/             ← Mayormente histórico -- migrado a docker-swarm/stacks/pi-obs/
├── pi-sonar/           ← Mayormente histórico -- migrado a docker-swarm/stacks/
└── pi-utils/           ← Mayormente histórico -- capataz-frontend es lo que sigue vivo aquí
```

---

## Prerrequisitos comunes a todos los nodos

- Ubuntu Server 24.04 LTS
- Docker Engine (ver `shared/scripts/install-docker-ubuntu.sh`)
- IP fija configurada
- Directorio base `/srv/homelab` creado
- DNS interno apuntando a `192.168.1.170` (Pi-hole)

> Durante la instalación/pruebas, antes de cambiar el DNS de todo el router (`docs/06-instalacion-pi1-dns.md` paso 8), se puede apuntar temporalmente solo el PC de gestión a pi-dns — ver `docs/06-instalacion-pi1-dns.md` sección 8.1.

Ver `docs/03-instalacion-base-ubuntu-raspi.md` para la guía completa.
