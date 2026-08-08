# homelab-cluster

Infraestructura doméstica distribuida en 6 nodos: dos PCs (Ryzen 9 y MiniPC Ryzen 5) y 4 Raspberry Pi 5. Orquestación con Docker Engine + Docker Compose v2. Sin Kubernetes. Sin Docker Swarm. Además del clúster, la misma LAN aloja un NAS UGREEN (`ketekasko`) que no está gestionado por Docker — ver la sección "NAS UGREEN" más abajo.

---

## Nodos

| Nodo              | IP              | Función principal                                    |
|-------------------|-----------------|------------------------------------------------------|
| ryzen.home.arpa   | 192.168.1.150   | IA con GPU: Ollama, Whisper, Open WebUI              |
| retaco.home.arpa  | 192.168.1.174   | Datos y automatización: Postgres main, Qdrant, n8n-main |
| pi-dns.home.arpa  | 192.168.1.170   | DNS (Pi-hole + Unbound), nginx reverse proxy         |
| pi-obs.home.arpa  | 192.168.1.171   | Observabilidad (OTel, Prometheus, Grafana, Loki, Tempo)|
| pi-sonar.home.arpa| 192.168.1.172   | SonarQube (base de datos en retaco)                  |
| pi-utils.home.arpa| 192.168.1.173   | Utilidades: RSSHub, markitdown-service, crawl4ai-scraper-service, n8n-aux |

---

## Servicios expuestos por nombre de host

| Hostname                    | Nodo destino        | Puerto upstream |
|-----------------------------|---------------------|-----------------|
| openwebui.home.arpa         | ryzen.home.arpa     | 8080            |
| n8n.home.arpa               | retaco.home.arpa    | 5678            |
| ollama.home.arpa            | ryzen.home.arpa     | 11434           |
| vllm.home.arpa              | ryzen.home.arpa     | 8010            |
| comfyui.home.arpa           | ryzen.home.arpa     | 8188            |
| qdrant.home.arpa            | retaco.home.arpa    | 6333            |
| whisper.home.arpa           | ryzen.home.arpa     | 9800            |
| grafana.home.arpa           | pi-obs.home.arpa    | 3000            |
| prometheus.home.arpa        | pi-obs.home.arpa    | 9090            |
| otel.home.arpa              | pi-obs.home.arpa    | 4317/4318       |
| sonarqube.home.arpa         | pi-sonar.home.arpa  | 9000            |
| rsshub.home.arpa            | pi-utils.home.arpa  | 1200            |
| markitdown.home.arpa        | pi-utils.home.arpa  | 8001            |
| n8n-aux.home.arpa           | pi-utils.home.arpa  | 5679            |
| portainer.home.arpa         | pi-utils.home.arpa  | 9000            |
| vaultwarden.home.arpa       | pi-utils.home.arpa  | 8222            |
| apikey.home.arpa            | pi-dns.home.arpa    | 8090            |
| registry.home.arpa          | retaco.home.arpa    | 5000            |
| index.home.arpa             | pi-dns.home.arpa    | — (estático, sin proxy) |

`index.home.arpa` es un panel HTML simple con tarjetas a todos los servicios con interfaz web — ver `pi-dns/README.md`.

---

## Acceso remoto (fuera de la LAN)

El acceso remoto se realiza mediante Tailscale, con un subnet router en `pi-dns` que da acceso autenticado a toda la LAN, incluida la resolución de `*.home.arpa` (Split DNS). Ver `docs/18-tailscale.md`.

---

## Wake-on-LAN

`ryzen` (alias `mole`) puede apagarse cuando no se usa y encenderse remotamente desde otro nodo del clúster — ver `docs/19-wake-on-lan.md`.

---

## NAS UGREEN (`ketekasko`)

Dispositivo LAN adicional (`192.168.1.180`, UGOS Pro) — no forma parte del clúster Docker, pero resuelve por DNS y tiene tarjeta en `index.home.arpa`. SMB, NFSv4 y carpetas compartidas — ver `docs/21-configuracion-nas-ugreen.md`.

---

## Arranque rápido

```bash
# En cada nodo, clonar/copiar el directorio correspondiente a /srv/homelab/
# Ejemplo para Ryzen:
cd /srv/homelab
cp ryzen/.env.example ryzen/.env
# editar ryzen/.env con contraseñas reales
docker compose -f ryzen/docker-compose.yml up -d
```

Ver `docs/` para guías completas por nodo.

---

## Estructura del proyecto

```
homelab-cluster/
├── README.md
├── docs/               ← Documentación completa
├── shared/
│   ├── env/            ← .env.example por nodo
│   ├── scripts/        ← Scripts de instalación y operación
│   └── dns/            ← Documentación DNS y registros
├── ryzen/              ← Stack IA + pipeline principal
├── retaco/             ← Postgres main + Qdrant + n8n-main
├── pi-dns/             ← DNS local + nginx proxy
├── pi-obs/             ← Observabilidad completa
├── pi-sonar/           ← SonarQube
└── pi-utils/           ← Utilidades ligeras
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
