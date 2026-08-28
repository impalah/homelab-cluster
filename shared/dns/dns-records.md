# Registros DNS internos — 404labo.net

Estos registros deben añadirse en la interfaz de Pi-hole: **Local DNS → DNS Records** (o aplicarse
con `shared/scripts/load-dns-records.sh`, que sustituye la lista entera de una vez).

**Mejora 41 (cerrada 2026-08-28): `home.arpa` retirado por completo del clúster.** Split-horizon
sigue igual que siempre — Pi-hole resuelve estos nombres solo dentro de la LAN, a IPs privadas;
Route53 nunca recibe ningún registro A para `404labo.net`/`*.404labo.net` (invariante de seguridad
de la mejora 41, verificada durante toda la migración). El dominio es real y está delegado en
Route53 solo para poder emitir el certificado wildcard de Let's Encrypt por reto DNS-01
(`_acme-challenge.404labo.net`, ver `shared/scripts/renew-letsencrypt.sh`) — nunca para publicar la
topología del clúster a internet.

## Nodos del clúster

| Nombre de host | IP | Descripción |
|---|---|---|
| `ryzen.404labo.net` | `192.168.1.150` | PC Ryzen 9 (cómputo principal) |
| `retaco.404labo.net` | `192.168.1.174` | MiniPC Ryzen 5 (postgres-main + qdrant) |
| `pi-dns.404labo.net` | `192.168.1.170` | Raspberry Pi 5 #1 (DNS) — fuera del Swarm a propósito |
| `pi-obs.404labo.net` | `192.168.1.171` | Raspberry Pi 5 #2 (observabilidad) |
| `pi-sonar.404labo.net` | `192.168.1.172` | Raspberry Pi 5 #3 (SonarQube) |
| `pi-utils.404labo.net` | `192.168.1.173` | Raspberry Pi 5 #4 (utilidades) |
| `pinchi.404labo.net` | `192.168.1.175` | PC GMKtec NucBox G10 Pro |

## Servicios (Traefik en el swarm)

Todos estos hostnames responden en cualquier nodo del Swarm gracias a la routing mesh de Traefik
(`mode: global`, mejora 39) — se usa `pinchi` (192.168.1.175) por convención (nodo con menos carga
de aplicación), pero cualquier IP del Swarm serviría igual. Certificado real de Let's Encrypt
(wildcard `*.404labo.net`), renovado y rotado automáticamente
(`shared/scripts/renew-letsencrypt.sh` + `shared/scripts/deploy-traefik-cert.sh`, mejora 41). Ver
`docker-swarm/stacks/traefik/dynamic/routes.yml` para el detalle de cada router/middleware.

| Nombre de host | IP | Servicio real | Puerto real |
|---|---|---|---|
| `home.404labo.net` | `192.168.1.175` | Frontend de Capataz (consola de estado/automatización del clúster) — proxy puro hacia el contenedor `capataz-frontend` en `pi-utils.404labo.net:8090` (su propio nginx reenvía `/api/` a `capataz-api.404labo.net`) | 8090 |
| `capataz-api.404labo.net` | `192.168.1.175` | capataz-api en `pi-utils` — auth propia (OIDC/Authentik), no protegido con apikey-service. Ver `docs/28-capataz-consola-automatizacion.md` | 8000 |
| `openwebui.404labo.net` | `192.168.1.175` | Open-WebUI en retaco | 8080 |
| `n8n.404labo.net` | `192.168.1.175` | n8n-main en retaco | 5678 |
| `ollama.404labo.net` | `192.168.1.175` | Ollama en ryzen — protegido con apikey-service | 11434 |
| `vllm.404labo.net` | `192.168.1.175` | vLLM en ryzen (alterna con ollama) — protegido con apikey-service | 8010 |
| `comfyui.404labo.net` | `192.168.1.175` | ComfyUI en ryzen (alterna con whisper-service en GPU 1) — protegido con apikey-service | 8188 |
| `qdrant.404labo.net` | `192.168.1.175` | Qdrant en retaco | 6333 |
| `whisper.404labo.net` | `192.168.1.175` | Whisper-service en ryzen | 9800 |
| `grafana.404labo.net` | `192.168.1.175` | Grafana en pi-obs | 3000 |
| `prometheus.404labo.net` | `192.168.1.175` | Prometheus en pi-obs — protegido con Authentik (forward-auth), verificado de punta a punta (mejora 41, Fase C) | 9090 |
| `sonarqube.404labo.net` | `192.168.1.175` | SonarQube en pi-sonar | 9000 |
| `bifrost.404labo.net` | `192.168.1.175` | Bifrost (gateway LLM / AWS Bedrock) en pi-sonar — auth propia (virtual keys), no protegido con apikey-service | 8080 |
| `rsshub.404labo.net` | `192.168.1.175` | RSSHub en pi-utils | 1200 |
| `markitdown.404labo.net` | `192.168.1.175` | Markitdown-service en pi-utils — protegido con apikey-service | 8001 |
| `crawl4ai.scraper.404labo.net` | `192.168.1.175` | crawl4ai-scraper-service en pi-utils — protegido con apikey-service. Sub-subdominio a propósito, no un error de nomenclatura. | 8002 |
| `n8n-aux.404labo.net` | `192.168.1.175` | n8n-aux en pi-utils | 5679 |
| `portainer.404labo.net` | `192.168.1.175` | Portainer en pi-utils | 9000 |
| `vaultwarden.404labo.net` | `192.168.1.175` | Vaultwarden en pi-utils | 8222 |
| `registry.404labo.net` | `192.168.1.175` | Registry Docker privado en retaco — autenticación propia (htpasswd), no protegido con apikey-service (los clientes Docker no mandan `X-Api-Key`) | 5000 |
| `epub2pdf.404labo.net` | `192.168.1.175` | epub2pdf-service en retaco — protegido con apikey-service | 8003 |
| `pdf2chunks.404labo.net` | `192.168.1.175` | pdf2chunks-service en retaco — protegido con apikey-service | 8004 |
| `open-terminal.404labo.net` | `192.168.1.175` | open-terminal-mcp (servidor MCP) en retaco — protegido con apikey-service, obligatorio (el transporte MCP no tiene auth propia, ver `docs/24-open-terminal-mcp.md`) | 8005 |
| `infisical.404labo.net` | `192.168.1.175` | Infisical (gestor de secretos) en retaco — auth propia, no protegido con apikey-service. Ver `docs/26-infisical-secretos.md` | 8006 |
| `authentik.404labo.net` | `192.168.1.175` | Authentik (SSO/authn para personas) en retaco — auth propia, no protegido con apikey-service. Ver `docs/27-authentik-sso.md` | 9000 |

**Retirados sin sustituto de hostname** (mejora 41, cierre): `old.index.404labo.net` (panel estático
original, superseded por Capataz, mejora 15), `apikey.404labo.net` (gestión de API keys — acceso
administrativo directo por IP:puerto a la instancia del propio Swarm, `http://192.168.1.175:8091`,
en vez de un hostname propio; la copia de `apikey-service` que vivía en `pi-dns` para servir a nginx
se retiró junto con este — ver más abajo), `pihole.404labo.net` (panel de Pi-hole — publicado
directo en la LAN por IP:puerto, ver la sección siguiente).

## Pi-hole (sin hostname, sin proxy)

Con `nginx` decomisionado en `pi-dns` (mejora 41, cierre), el panel de administración de Pi-hole se
publica directo en la interfaz LAN del nodo, sin hostname ni proxy inverso delante:

```
http://192.168.1.170:8053
```

Antes solo escuchaba en `127.0.0.1:8053` (nginx hacía de intermediario vía `pihole.home.arpa`) — ver
`pi-dns/docker-compose.yml`.

## Alias directos (sin proxy — no son HTTP)

| Nombre de host | IP | Servicio real | Puerto real |
|---|---|---|---|
| `postgresql.404labo.net` | `192.168.1.174` | postgres-main en retaco | 5432 |
| `valkey.404labo.net` | `192.168.1.174` | Valkey (caché clave-valor) en retaco — TLS con cert propio autofirmado por la CA interna del clúster (CN=valkey.404labo.net), protegido además por ACL propia (usuario `default` desactivado). No usa el wildcard real de Let's Encrypt — bug real de Swarm con bind-mounts `:ro` y claves TLS obligó a revertir a autofirmado (ver comentario en `docker-swarm/stacks/valkey/docker-compose.yml`); es el único consumidor que deja la CA interna del clúster todavía en uso tras la mejora 41 | 6379 |
| `ketekasko.404labo.net` | `192.168.1.180` | NAS UGREEN NASync DH2300 (UGOS Pro) — no forma parte del clúster Docker | 9443 |

`postgresql.404labo.net`/`valkey.404labo.net` **no** pasan por Traefik como el resto de la tabla
anterior — son alias directos a la IP de `retaco`. Motivo: ambos hablan su propio protocolo binario
por TCP, no HTTP, así que no pueden convivir con los routers HTTP/HTTPS de Traefik del mismo modo.
El cliente conecta directamente a `retaco:<puerto>`, exactamente igual que si usara la IP a secas,
solo que con un nombre más cómodo de recordar. Ver `docs/05-instalacion-retaco.md` y
`docs/25-valkey-cache.md`.

`ketekasko.404labo.net` tampoco pasa por Traefik — es HTTP(S), pero UGOS Pro sirve su propia
interfaz con su propio certificado TLS en el puerto `9443` (no el 443 de Traefik), así que un alias
directo a la IP es más simple que meterlo detrás del proxy inverso. El NAS tiene IP fija
`192.168.1.180` configurada en el propio dispositivo (fuera del rango que gestiona este repo), no en
`pi-dns`.

`qdrant.404labo.net`, en cambio, **sí** pasa por el proxy (es HTTP) — ya está en la tabla de arriba.

## Flujo de resolución DNS

```
Cliente
  └─► Pi-hole (192.168.1.170:53)
        ├─► 404labo.net → responde con IP local (tabla anterior)
        └─► internet → Unbound (127.0.0.1:5335)
                         └─► resolución recursiva (raíz → TLD → autoritativo)
```

Unbound ya no necesita ninguna `local-zone` especial para `404labo.net` — a diferencia de
`home.arpa` (dominio de uso especial, RFC 8375, que Unbound trataba de forma distinta por defecto),
`404labo.net` es un dominio público real y corriente: Pi-hole responde primero con sus registros
locales para lo que resuelve en la LAN, y Unbound nunca llega siquiera a intentar recursarlo.

Acceso remoto (Tailscale, `docs/18-tailscale.md`): Split DNS configurado en el panel de Tailscale
con "Restrict to domain" → `404labo.net`, apuntando a `pi-dns` (192.168.1.170) — mismo mecanismo que
antes con `home.arpa`, solo cambia el dominio.

## Notas

- Pi-hole está configurado con `404labo.net` como dominio local. Todos los registros anteriores se
  añaden con `shared/scripts/load-dns-records.sh` (sustituye la lista entera de una vez,
  idempotente).
- Si Pi-hole está caído, la resolución DNS falla para `*.404labo.net`. Tener siempre el nodo pi-dns
  en alta disponibilidad.
- Para acceso temporal sin Pi-hole (emergencia), añadir entradas en `/etc/hosts` del cliente:
  ```
  192.168.1.175  openwebui.404labo.net grafana.404labo.net n8n.404labo.net
  ```
