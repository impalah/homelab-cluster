# ryzen — Nodo de cómputo principal

**IP:** `192.168.1.150`  
**Hardware:** PC Linux con Ryzen 9, GPU NVIDIA, ≥32 GB RAM

## Dos stacks independientes

Este nodo tiene **dos** `docker-compose.yml` separados a propósito, para poder dejar la observabilidad del host en marcha aunque el stack de IA (GPU) esté parado:

| Fichero | Contiene | Depende de `.env` |
|---|---|---|
| `docker-compose.yml` | ollama, vllm, open-webui, whisper-service, comfyui | Sí |
| `docker-compose.observability.yml` | node-exporter, cadvisor, portainer-agent | No — cero variables de entorno, arranca sin configurar nada |

Cada uno es su propio proyecto Compose (`homelab-ryzen` y `homelab-ryzen-observability`), con su propia red Docker — no comparten nada, se pueden parar/arrancar totalmente por separado.

## Servicios

| Servicio | Puerto (host→container) | URL pública |
|---|---|---|
| ollama | 11434 | https://ollama.home.arpa (requiere API key — ver aviso abajo) |
| vllm | 8010→8000 | https://vllm.home.arpa (requiere API key — ver aviso abajo) |
| open-webui | 8080 | https://openwebui.home.arpa |
| whisper-service | 9800 | https://whisper.home.arpa |
| comfyui | 8188 | https://comfyui.home.arpa (requiere API key — ver aviso abajo) |
| node-exporter | 9100 | — (consultado por Prometheus en pi-obs) |
| cadvisor | 8081→8080 | — (consultado por Prometheus en pi-obs) |
| portainer-agent | 9001 | — (conectado al servidor Portainer en pi-utils) |

> Los puertos HTTP se publican en todas las interfaces (no solo loopback) — nginx en `pi-dns`, que se ejecuta en *otro* nodo, necesita alcanzarlos por la LAN para hacer de proxy inverso y exponerlos mediante HTTPS. (Nota: esta tabla decía antes "127.0.0.1", pero no se corresponde con el `docker-compose.yml` real — corregido.)

> `postgres-main`, `qdrant` y `n8n-main` se migraron al nodo `retaco` (192.168.1.174) — ver `docs/05-instalacion-retaco.md`. No hay ningún servicio de datos ni de automatización en este nodo; solo cómputo con GPU.

## ⚠️ ollama y vllm NUNCA a la vez

Ambos compiten por la misma GPU (RTX 5070, 12 GB) — arrancarlos juntos revienta por VRAM o corrompe el contexto CUDA del que arrancó segundo. Usa siempre:

```bash
bash switch-llm-backend.sh ollama   # para vllm si está arriba, arranca ollama
bash switch-llm-backend.sh vllm     # para ollama si está arriba, arranca vllm
```

Nunca `docker compose up -d ollama` / `docker compose up -d vllm` sueltos salvo que sepas con certeza que el otro ya está parado. Ver `docs/07-instalacion-ryzen.md` para la elección de modelo/cuantización de vLLM.

## ⚠️ whisper-service y comfyui NUNCA a la vez

Mismo motivo, otra GPU: ambos compiten por la RTX 3070 (8 GB). Es un interruptor **independiente** del de ollama/vllm — puedes tener p. ej. `ollama` + `comfyui` a la vez sin problema, eso es justo el objetivo (ver `docs/07-instalacion-ryzen.md`).

```bash
bash switch-gpu1-backend.sh whisper-service   # para comfyui si está arriba, arranca whisper-service
bash switch-gpu1-backend.sh comfyui           # para whisper-service si está arriba, arranca comfyui
```

## Acceso externo con API key

`ollama.home.arpa`, `vllm.home.arpa` y `comfyui.home.arpa` exigen la cabecera `X-Api-Key` (protegidos con `apikey-service`, ver `docs/06-instalacion-pi1-dns.md`) — cualquier cliente en la LAN o workflow de n8n que los llame por el nombre de host público necesita una key emitida ahí. **Open WebUI no se ve afectado**: le llega por la red Docker interna de este nodo (`http://ollama:11434`, `http://vllm:8000`), sin pasar por nginx. ComfyUI, si lo usas desde el propio navegador de esta máquina, tampoco necesita key: `http://localhost:8188` directo.

## Arranque rápido

```bash
cp .env.example .env
nano .env          # Rellenar todos los CHANGE_ME

# Stack de IA (docker-compose.yml es el nombre por defecto, no hace falta -f)
docker compose pull   # importante: ver aviso más abajo sobre imágenes ":latest" desactualizadas
docker compose up -d
docker compose ps

# Stack de observabilidad — completamente independiente, sin .env
docker compose -f docker-compose.observability.yml up -d
docker compose -f docker-compose.observability.yml ps
```

> ⚠️ `docker compose up -d` sin indicar un servicio concreto arranca **todos** los servicios definidos en ese fichero. Si solo quieres levantar uno, indícalo explícitamente: `docker compose up -d ollama`.

> ⚠️ **`docker compose pull` antes de cada arranque, especialmente en este nodo.** Como este stack se para y arranca a demanda (para ahorrar GPU), la imagen `ollama/ollama:latest` puede llevar semanas o meses cacheada sin refrescar — Docker no vuelve a comprobar si hay una versión nueva salvo que se lo pidas explícitamente, `latest` es solo un nombre, no una promesa de actualización automática. Síntoma típico si no se hace: Ollama rechaza descargar un modelo reciente pidiendo "actualizar a la última versión", cuando la versión instalada simplemente lleva tiempo desfasada.

### Parar solo uno de los dos stacks

```bash
docker compose down                                    # para IA (GPU), deja observabilidad intacta
docker compose -f docker-compose.observability.yml down  # para observabilidad, deja IA intacta
```

## Encendido remoto (Wake-on-LAN)

Este nodo puede apagarse por completo cuando no se usa y encenderse desde
otro nodo del clúster con `shared/scripts/wake-mole.sh` — detalle completo
(requisitos, por qué apagado completo y no hibernar/suspender, ajuste de
BIOS pendiente de confirmar) en `docs/19-wake-on-lan.md`.

## Prerrequisitos

- Docker Engine + NVIDIA Container Toolkit instalados (`shared/scripts/install-docker-ubuntu.sh`)
- Directorios de datos creados (`shared/scripts/prepare-host.sh ryzen`)
- GPU NVIDIA con driver ≥ 535 y CUDA 12.x

## Estructura

```
ryzen/
├── docker-compose.yml                 ← stack de IA (ollama, vllm, open-webui, whisper-service, comfyui)
├── docker-compose.observability.yml   ← stack de observabilidad (independiente, sin .env)
├── switch-llm-backend.sh              ← alterna ollama/vllm en GPU 0, nunca a la vez (ver aviso arriba)
├── switch-gpu1-backend.sh             ← alterna whisper-service/comfyui en GPU 1, nunca a la vez
├── .env.example
└── README.md
```

`whisper-service` ya no tiene código aquí — vive en `services/whisper-service/` (raíz del repo) y se publica en `registry.home.arpa` mediante `make build`; este nodo solo hace `image:` + `pull` (`docs/05-instalacion-retaco.md` sección 5.3).

## Notas

- Si algún workflow de n8n (ahora en `retaco`) llama a `ollama` o `whisper-service` por nombre de contenedor Docker (p. ej. `http://ollama:11434`), hay que actualizarlo al nombre de host público (`https://ollama.home.arpa`) — ya no comparten red Docker desde que n8n se migró.
- `whisper-service` tarda ~90 segundos en arrancar (carga del modelo en GPU). El healthcheck tiene `start_period: 90s`.
- Para descargar modelos en Ollama: `docker exec ollama ollama pull llama3.2:3b`
