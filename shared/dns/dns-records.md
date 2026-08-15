# Registros DNS internos — home.arpa

Estos registros deben añadirse en la interfaz de Pi-hole: **Local DNS → DNS Records**

## Nodos del clúster

| Nombre de host | IP | Descripción |
|---|---|---|
| `ryzen.home.arpa` | `192.168.1.150` | PC Ryzen 9 (cómputo principal) |
| `retaco.home.arpa` | `192.168.1.174` | MiniPC Ryzen 5 (postgres-main + qdrant) |
| `pi-dns.home.arpa` | `192.168.1.170` | Raspberry Pi 5 #1 (DNS + proxy) |
| `pi-obs.home.arpa` | `192.168.1.171` | Raspberry Pi 5 #2 (observabilidad) |
| `pi-sonar.home.arpa` | `192.168.1.172` | Raspberry Pi 5 #3 (SonarQube) |
| `pi-utils.home.arpa` | `192.168.1.173` | Raspberry Pi 5 #4 (utilidades) |

## Servicios (apuntan a pi-dns — nginx hace el proxy)

| Nombre de host | IP | Servicio real | Puerto real |
|---|---|---|---|
| `pihole.home.arpa` | `192.168.1.170` | Panel admin de Pi-hole (contenedor `pihole`) | 80 |
| `index.home.arpa` | `192.168.1.170` | Frontend de Capataz (consola de estado/automatización del clúster) — build estático servido directo por nginx, `/api/` proxifica a `pi-utils.home.arpa:8000` | — / 8000 (api) |
| `old.index.home.arpa` | `192.168.1.170` | Panel estático original de acceso a los servicios del clúster (HTML servido directo por nginx, sin proxy) — movido aquí al desplegar Capataz en `index.home.arpa` | — |
| `openwebui.home.arpa` | `192.168.1.170` | Open-WebUI en retaco (migrado desde ryzen, ver `docs/23-bifrost-gateway-llm.md`) | 8080 |
| `n8n.home.arpa` | `192.168.1.170` | n8n-main en retaco | 5678 |
| `ollama.home.arpa` | `192.168.1.170` | Ollama en ryzen — protegido con apikey-service | 11434 |
| `vllm.home.arpa` | `192.168.1.170` | vLLM en ryzen (alterna con ollama) — protegido con apikey-service | 8010 |
| `comfyui.home.arpa` | `192.168.1.170` | ComfyUI en ryzen (alterna con whisper-service en GPU 1) — protegido con apikey-service | 8188 |
| `qdrant.home.arpa` | `192.168.1.170` | Qdrant en retaco | 6333 |
| `whisper.home.arpa` | `192.168.1.170` | Whisper-service en ryzen | 9800 |
| `grafana.home.arpa` | `192.168.1.170` | Grafana en pi-obs | 3000 |
| `prometheus.home.arpa` | `192.168.1.170` | Prometheus en pi-obs | 9090 |
| `sonarqube.home.arpa` | `192.168.1.170` | SonarQube en pi-sonar | 9000 |
| `bifrost.home.arpa` | `192.168.1.170` | Bifrost (gateway LLM / AWS Bedrock) en pi-sonar — auth propia (virtual keys), no protegido con apikey-service | 8080 |
| `rsshub.home.arpa` | `192.168.1.170` | RSSHub en pi-utils | 1200 |
| `markitdown.home.arpa` | `192.168.1.170` | Markitdown-service en pi-utils — protegido con apikey-service | 8001 |
| `crawl4ai.scraper.home.arpa` | `192.168.1.170` | crawl4ai-scraper-service en pi-utils — protegido con apikey-service. Sub-subdominio a propósito, no un error de nomenclatura. | 8002 |
| `n8n-aux.home.arpa` | `192.168.1.170` | n8n-aux en pi-utils | 5679 |
| `portainer.home.arpa` | `192.168.1.170` | Portainer en pi-utils | 9000 |
| `vaultwarden.home.arpa` | `192.168.1.170` | Vaultwarden en pi-utils | 8222 |
| `apikey.home.arpa` | `192.168.1.170` | apikey-service (gestión de API keys) en pi-dns | 8090 |
| `registry.home.arpa` | `192.168.1.170` | Registry Docker privado en retaco — autenticación propia (htpasswd), no protegido con apikey-service (los clientes Docker no mandan `X-Api-Key`) | 5000 |
| `epub2pdf.home.arpa` | `192.168.1.170` | epub2pdf-service en retaco — protegido con apikey-service | 8003 |
| `pdf2chunks.home.arpa` | `192.168.1.170` | pdf2chunks-service en retaco — protegido con apikey-service | 8004 |
| `open-terminal.home.arpa` | `192.168.1.170` | open-terminal-mcp (servidor MCP) en retaco — protegido con apikey-service, obligatorio (el transporte MCP no tiene auth propia, ver `docs/24-open-terminal-mcp.md`) | 8005 |
| `infisical.home.arpa` | `192.168.1.170` | Infisical (gestor de secretos) en retaco — auth propia, no protegido con apikey-service. Ver `docs/26-infisical-secretos.md` | 8006 |
| `authentik.home.arpa` | `192.168.1.170` | Authentik (SSO/authn para personas) en retaco — auth propia, no protegido con apikey-service. Ver `docs/27-authentik-sso.md` | 9000 |

## Alias directos (sin proxy — no son HTTP)

| Nombre de host | IP | Servicio real | Puerto real |
|---|---|---|---|
| `postgresql.home.arpa` | `192.168.1.174` | postgres-main en retaco | 5432 |
| `valkey.home.arpa` | `192.168.1.174` | Valkey (caché clave-valor) en retaco — protegido por ACL propia (usuario `default` desactivado), no por `apikey-service` | 6379 |
| `ketekasko.home.arpa` | `192.168.1.180` | NAS UGREEN NASync DH2300 (UGOS Pro) — no forma parte del clúster Docker | 9443 |

`postgresql.home.arpa`/`valkey.home.arpa` **no** pasan por `pi-dns`/nginx como el resto de la tabla anterior — son alias directos a la IP de `retaco`. Motivo: ambos hablan su propio protocolo binario por TCP, no HTTP, así que no pueden convivir con los vhosts HTTP/HTTPS de nginx del mismo modo. El cliente conecta directamente a `retaco:<puerto>`, exactamente igual que si usara la IP a secas, solo que con un nombre más cómodo de recordar. Ver `docs/05-instalacion-retaco.md` y `docs/25-valkey-cache.md`.

`ketekasko.home.arpa` tampoco pasa por nginx — es HTTP(S), pero UGOS Pro sirve su propia interfaz con su propio certificado TLS en el puerto `9443` (no el 443 que usa nginx), así que un alias directo a la IP es más simple que meterlo detrás del proxy inverso. El NAS tiene IP fija `192.168.1.180` configurada en el propio dispositivo (fuera del rango que gestiona este repo), no en `pi-dns`.

`qdrant.home.arpa`, en cambio, **sí** pasa por el proxy (es HTTP) — ya está en la tabla de arriba.

## Flujo de resolución DNS

```
Cliente
  └─► Pi-hole (192.168.1.170:53)
        ├─► home.arpa → responde con IP local (tabla anterior)
        └─► internet → Unbound (127.0.0.1:5335)
                         └─► resolución recursiva (raíz → TLD → autoritativo)
```

## Notas

- Pi-hole está configurado con `home.arpa` como dominio local. Todos los registros anteriores se añaden manualmente una sola vez.
- Unbound NO necesita conocer los registros `home.arpa`; Pi-hole los resuelve directamente sin reenviar al upstream.
- Si Pi-hole está caído, la resolución DNS falla para `*.home.arpa`. Tener siempre el nodo pi-dns en alta disponibilidad.
- Para acceso temporal sin Pi-hole (emergencia), añadir entradas en `/etc/hosts` del cliente:
  ```
  192.168.1.170  openwebui.home.arpa grafana.home.arpa n8n.home.arpa
  ```
