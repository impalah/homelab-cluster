# 24 — Open Terminal en modo MCP (Open WebUI + n8n)

## Qué es y por qué está aquí

[Open Terminal](https://github.com/open-webui/open-terminal) (mismo equipo que Open WebUI) expone una terminal, un sistema de ficheros y ejecución de comandos como API — pensado para que un LLM pueda actuar sobre un entorno real, no solo razonar sobre texto. Mejora 17 del backlog (`docs/22-mejoras-futuras.md`): darle esa capacidad tanto a **Open WebUI** (chat) como a **n8n** (automatizaciones), a través de **MCP** (Model Context Protocol), en vez de dos integraciones distintas.

## Por qué `retaco` y no `ryzen`/`mole`

`retaco` es quien ya aloja tanto a Open WebUI como a n8n-main — desplegar ahí evita saltos cross-host innecesarios para el consumidor real de este servicio. `ryzen`/`mole` quedó descartado a petición expresa: no está siempre encendido, y este servicio solo tiene sentido si los clientes (Open WebUI, n8n) pueden alcanzarlo cuando lo necesiten.

Carga comprobada en vivo antes de desplegar (`docker stats` + `free -h` en `retaco`): ~10 GiB libres de 13 GiB, CPU prácticamente ociosa con todos los servicios existentes corriendo (postgres-main, qdrant, n8n-main, registry, open-webui, epub2pdf-service, pdf2chunks-service) — margen de sobra para una imagen `slim` (~430 MB, git/curl/jq, sin Node.js/Docker CLI/ffmpeg).

## Imagen propia — por qué no la oficial directamente

Ninguna variante publicada de `ghcr.io/open-webui/open-terminal` (`latest`/`slim`/`alpine`/`openshift`) trae instalado el extra opcional `[mcp]` (`fastmcp>=2.0.0`) — confirmado leyendo `pyproject.toml`, `Dockerfile` y `Dockerfile.slim` del propio proyecto. Sin él, el subcomando `open-terminal mcp` falla con `Missing MCP dependencies`. La imagen slim/alpine además desinstala `pip` a propósito al final del build (menos superficie) y su entrypoint declara explícitamente que no instala nada en caliente — no hay forma de activar el modo MCP solo con variables de entorno.

Solución: `services/open-terminal-mcp/Dockerfile`, que parte de `ghcr.io/open-webui/open-terminal:slim` y añade `fastmcp` encima (reinstalando `pip` temporalmente vía `ensurepip`, instalando el paquete, y desinstalando `pip` otra vez). Sigue el tag `slim` oficial en cada rebuild sin duplicar su Dockerfile — el único cambio real es una dependencia Python de más. Publicada como `registry.home.arpa/open-terminal-mcp:latest`.

**Nota de proceso (para no repetir el error):** la primera versión de ese
Dockerfile encadenaba las tres instrucciones con `&& ... && ... 2>/dev/null
|| true`, pensado solo para tolerar el fallo del `pip uninstall` final. Por
precedencia de operadores, el `|| true` final enmascaraba un fallo real del
`pip install` anterior — el build "funcionaba" (exit 0) sin `fastmcp`
instalado en absoluto, y no se detectó hasta arrancar el contenedor y
probarlo (`ModuleNotFoundError: No module named 'fastmcp'`). Corregido
quitando el `|| true` de la cadena y usando `python3 -m pip` en vez de
`pip` a secas (justo tras `ensurepip`, el script `pip` no queda en el PATH
del shell aunque el paquete se instale bien).

## Hallazgo de seguridad real — por qué va detrás de `apikey-service`

`OPEN_TERMINAL_API_KEY` protege la API REST propia de Open Terminal (`open-terminal run`), pero **no** el servidor MCP. Leyendo `open_terminal/mcp_server.py` del propio proyecto:

```python
mcp = FastMCP.from_fastapi(
    app=app,
    name="Open Terminal",
    httpx_client_kwargs={"headers": {"Authorization": f"Bearer {API_KEY}"}},
)
```

`FastMCP.from_fastapi()` se instancia **sin ningún proveedor de autenticación** (`auth=...`) — el `Authorization: Bearer` solo se usa para que el propio servidor MCP llame internamente a su FastAPI (transporte ASGI en proceso, sin red real de por medio). El transporte MCP externo (`streamable-http`, el que consumen Open WebUI/n8n) queda **sin ninguna credencial exigida** — cualquiera que alcance el puerto tiene shell y sistema de ficheros completos.

Verificado en vivo antes de exponerlo a la red, contra el contenedor recién arrancado en local, sin pasar por nginx:

```bash
curl -s http://localhost:18005/mcp -X POST \
  -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2026-06-18","capabilities":{},"clientInfo":{"name":"test","version":"0.1"}}}'
# → HTTP 200, sin ninguna cabecera de autenticación
```

Por eso este servicio **nunca** se expone directamente — va siempre detrás de `nginx` + `apikey-service` (mismo patrón que `ollama.home.arpa`, `epub2pdf.home.arpa`), no como capa opcional sino como el único mecanismo de autenticación real que tiene de cara al exterior. `OPEN_TERMINAL_API_KEY` sigue siendo necesario igualmente (lo consume el propio proceso internamente), pero ningún cliente externo lo conoce ni lo necesita — el secreto que sí importa hacia fuera es la API key de `apikey-service`.

## Superficie de riesgo — sin montajes del host

Mismo criterio que Floci (mejora 14) y `docker.sock` en general: dar a un LLM acceso a shell/archivos equivale a darle acceso a todo lo que vea ese contenedor. Se empieza sin montajes del host reales y sin acceso a `docker.sock` — el único volumen es el propio directorio de trabajo del contenedor (`/srv/homelab/retaco/open-terminal-mcp/home`), nada del resto del clúster.

## Despliegue

### Imagen (`services/open-terminal-mcp/`)

```bash
cd services/open-terminal-mcp
cp .env.example .env   # REGISTRY_USER/REGISTRY_PASSWORD, ver Vaultwarden
make build              # login + build + push a registry.home.arpa/open-terminal-mcp:latest
```

### `retaco/docker-compose.yml`

```yaml
open-terminal-mcp:
  image: registry.home.arpa/open-terminal-mcp:latest
  container_name: open-terminal-mcp
  restart: unless-stopped
  command: ["mcp", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8000"]
  environment:
    OPEN_TERMINAL_API_KEY: ${OPEN_TERMINAL_API_KEY}
  volumes:
    - /srv/homelab/retaco/open-terminal-mcp/home:/home/user
  ports:
    - "8005:8000"
  networks:
    - retaco-net
```

`OPEN_TERMINAL_API_KEY` generado con `openssl rand -hex 32` y añadido al `.env` real de `retaco` (no está en `.env.example` con un valor real, solo `CHANGE_ME_...`).

Puerto `8005` — ver tabla de puertos en uso, `docs/desarrollo-microservicios-python.md` sección 15.

### `apikey-service` — key para el servicio

```bash
curl -sk -X POST https://apikey.home.arpa/keys \
  -H "Authorization: Bearer ${APIKEY_ADMIN_TOKEN}" -H "Content-Type: application/json" \
  -d '{"label": "open-terminal-mcp (Open WebUI + n8n)"}'
# → {"id":9,"label":"open-terminal-mcp (Open WebUI + n8n)","key":"..."}
```

Una única key compartida entre Open WebUI y n8n, no una por consumidor — mismo criterio ya usado en el resto del clúster (`ollama.home.arpa`, `vllm.home.arpa`). Guardar el valor en Vaultwarden ("open-terminal-mcp (Open WebUI + n8n)") — no se puede recuperar después, `apikey-service` solo guarda el hash.

### `nginx` (`pi-dns`)

```nginx
server {
    listen 443 ssl;
    server_name open-terminal.home.arpa;
    include /etc/nginx/apikey-auth.conf;
    location / {
        auth_request /_apikey_validate;
        proxy_pass http://192.168.1.174:8005;
        include /etc/nginx/proxy-common.conf;
        # MCP streamable-http mantiene la conexión abierta entre llamadas a
        # herramientas y responde en streaming (SSE) — sin esto, nginx
        # bufferea la respuesta entera (rompe el streaming) y corta
        # conexiones ociosas a los 60s por defecto.
        proxy_buffering off;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}
```

Añadido también `open-terminal.home.arpa` al array `DOMAINS` de `generate-cert.sh` y regenerado el certificado — mismo aviso ya documentado para Bifrost: sin esto, clientes con verificación TLS estricta (no solo `curl -k`) rechazan la conexión por *hostname mismatch* aunque la CA sea de confianza.

⚠️ Recordatorio del gotcha de rutas de `pi-dns` (ver `CLAUDE.md` y `docs/01-topologia.md`): el repo versiona esto en `pi-dns/config/nginx/`, pero el *bind mount* real de nginx está en `/srv/homelab/pi-dns/nginx/conf/` — desplegar a la ruta con forma de repo no da error, simplemente no hace nada.

## Prueba manual — de extremo a extremo, con y sin credencial

```bash
# Sin X-Api-Key → nginx corta antes de llegar al backend
curl -sk -o /dev/null -w "HTTP %{http_code}\n" https://open-terminal.home.arpa/mcp \
  -X POST -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2026-06-18","capabilities":{},"clientInfo":{"name":"test","version":"0.1"}}}'
# → HTTP 401

# Con X-Api-Key válida
curl -sk -o /dev/null -w "HTTP %{http_code}\n" https://open-terminal.home.arpa/mcp \
  -H "X-Api-Key: <key de apikey-service>" \
  -X POST -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2026-06-18","capabilities":{},"clientInfo":{"name":"test","version":"0.1"}}}'
# → HTTP 200
```

Ejecutado desde `ryzen`/`mole`, confirmando ambos casos.

## Conectar desde Open WebUI

Open WebUI ≥ 0.6.31 soporta MCP genérico de forma nativa (confirmado: `retaco` corre 0.11.0). Ruta real del menú en esta versión: **`Admin Settings → Integrations → Tools → External Tool Servers`** → botón **+ (Add Server)**:

- **Type**: por defecto pone "OpenAPI" — pinchar encima del texto para cambiarlo a **"MCP (Streamable HTTP)"** (aparece un aviso amarillo de soporte experimental, es normal, no bloquea nada).
- **Server URL**: `https://open-terminal.home.arpa/mcp`
- **Auth**: **no** usar la opción "Bearer" — manda `Authorization: Bearer <key>`, y `apikey-service` solo reconoce la cabecera `X-Api-Key`, no `Authorization`. Usar el campo libre **Headers** (JSON) con:
  ```json
  {"X-Api-Key": "<key de apikey-service>"}
  ```
- Guardar — puede pedir reiniciar Open WebUI.

⚠️ **No usar** la sección separada **`Terminal → Open Terminal`** que también aparece en `Integrations` — es la integración nativa dedicada al API REST propio de Open Terminal (`open-terminal run`), un mecanismo distinto de MCP. Nuestro contenedor **solo** corre en modo `mcp` (`command` fijado a `mcp --transport streamable-http` en `retaco/docker-compose.yml`) — la API REST ni siquiera está levantada, así que esa integración no funcionaría contra este despliegue.

### Activar la tool en un chat — paso que falta y no es obvio

Añadir el servidor en `Admin Settings → Integrations` **no la deja disponible automáticamente en el chat**. Es un hueco conocido de Open WebUI (varias Tool Servers globales no aparecen en el `+` del chat aunque estén en "Public") — el camino que sí funciona en esta versión:

**`Admin Settings → AI → Models` → seleccionar el modelo (p. ej. "Claude Sonnet 4.6") → `Edit` → sección Tools → marcar el servidor de Open Terminal → guardar.**

Hay que repetirlo **por cada modelo** con el que se quiera usar la herramienta (no es una activación global) — confirmado necesario tanto para modelos vía Bifrost (Bedrock) como para modelos locales de Ollama. Una vez hecho, el chat de ese modelo concreto muestra un indicador `🔧 N` junto al selector de modelo confirmando que hay `N` herramientas enganchadas.

## Conectar desde n8n

`retaco` corre n8n 2.31.6 — el nodo **MCP Client Tool** (`n8n-nodes-langchain.toolMcp`) viene de serie, sin instalar nada aparte. En el workflow/agente que vaya a usarlo:

1. Añadir el nodo **MCP Client Tool**.
2. **Endpoint**: `https://open-terminal.home.arpa/mcp`.
3. **Authentication**: Header Auth — nombre `X-Api-Key`, valor la key de
   `apikey-service`.
4. Las herramientas (terminal, ficheros, ejecución de comandos) se
   auto-descubren desde el propio servidor MCP al conectar.

## Modo multiusuario

`OPEN_TERMINAL_MULTI_USER=true` no está activado — cada sesión comparte el mismo espacio de trabajo (`/home/user`). Activarlo solo si de verdad hace falta aislar sesiones por usuario; de lo contrario, deja el estado innecesariamente más complejo de razonar para lo que este clúster necesita hoy (un solo operador).

## Troubleshooting

| Síntoma | Causa | Solución |
|---|---|---|
| `Missing MCP dependencies. Install with: pip install open-terminal[mcp]` al arrancar | Imagen oficial sin `fastmcp` | Usar `registry.home.arpa/open-terminal-mcp`, no `ghcr.io/open-webui/open-terminal` directamente |
| `/bin/sh: 1: pip: not found` durante el build de la imagen propia | `ensurepip` no deja el script `pip` en el PATH | Usar `python3 -m pip ...`, no `pip ...` a secas |
| El build de la imagen propia "funciona" pero `fastmcp` no está instalado | `\|\| true` al final de una cadena `&&` enmascara fallos previos, no solo el último comando | No usar `\|\| true` salvo en el paso exacto que puede fallar de forma esperada, nunca al final de una cadena larga |
| `curl` a `/mcp` sin ninguna cabecera devuelve 200 en vez de rechazar | Comportamiento esperado de Open Terminal — el transporte MCP no tiene auth propia | Confirmar que se está pasando por `open-terminal.home.arpa` (con `apikey-auth.conf`), no directo al puerto `8005` |
| Conexión MCP se corta a mitad de una tarea larga | Timeout de inactividad de nginx (60s por defecto) | Ya cubierto por `proxy_read_timeout 3600s`/`proxy_send_timeout 3600s` en el bloque `open-terminal.home.arpa` — si sigue pasando, revisar que el bloque desplegado en `pi-dns` sea el actual (gotcha de rutas) |
| Desplegar el nginx.conf o `generate-cert.sh` no tiene efecto | Ruta con forma de repo (`pi-dns/config/nginx/...`) en vez de la real (`/srv/homelab/pi-dns/nginx/conf/...`) | Ver `CLAUDE.md`/`docs/01-topologia.md`, sección de despliegue |
| El servidor aparece bien configurado en `Admin Settings → Integrations` pero no sale en el `+` del chat | Hueco conocido de Open WebUI: las Tool Servers globales no se activan solas | Activarla por modelo en `Admin Settings → AI → Models → Edit → Tools` (ver sección de arriba) |
| Con Claude (vía Bifrost/Bedrock), la herramienta falla con `messages.N.content.0.thinking.signature: Field required` | Bug conocido, no específico de este clúster: al combinar *extended thinking* de Claude con tool-use, la pasarela (Bifrost) traduce la respuesta a formato OpenAI para Open WebUI y pierde la firma criptográfica del bloque `thinking` al reconstruir el turno siguiente — Bedrock lo rechaza. Mismo patrón reportado en otras pasarelas OpenAI↔Bedrock ([spring-ai#6413](https://github.com/spring-projects/spring-ai/issues/6413), [opencode#6176](https://github.com/anomalyco/opencode/issues/6176)) | Sin solución encontrada todavía — desactivar *extended thinking* para el modelo evita el bug (si Open WebUI expone esa opción), pero no se ha confirmado. Pendiente de investigar más adelante, no bloqueante |
| Con modelos locales de Ollama (`qwen2.5:14b`, `qwen2.5:32b`, `qwen3.5:9b`, `qwen3.5:27b`, todos probados), el modelo **no ejecuta la herramienta de verdad** — escribe texto que imita la sintaxis de una llamada de función (p. ej. `</function_calls>`, `<parameter=...>`) y hasta se inventa una salida falsa | Sin diagnosticar del todo — no es previsible por los benchmarks públicos de tool-calling de la familia Qwen, así que probablemente sea la plantilla de chat de Ollama para estas etiquetas concretas, no el modelo en sí | Aparcado para investigar más adelante — con Claude vía Bifrost la llamada a la herramienta sí se genera correctamente (el problema ahí es otro, el de la fila de arriba), así que el camino MCP↔nginx↔apikey-service en sí queda verificado como correcto |
