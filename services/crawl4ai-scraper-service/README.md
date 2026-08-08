# Crawl4AI Scraper Service

Microservicio en Python que expone la funcionalidad de scraping y limpieza de contenido web de [Crawl4AI](https://github.com/unclecode/crawl4ai) a través de una API HTTP construida con FastAPI. Renderiza páginas con Playwright, limpia el boilerplate y genera markdown listo para consumir (por ejemplo, para pipelines de RAG/LLM).

## Arquitectura

El proyecto sigue la misma Clean Architecture por capas que el resto de servicios de este repo (`apikey-service`, `markitdown-service`, `whisper-service`) — código bajo `src/crawl4ai_scraper_service/`:

```
src/crawl4ai_scraper_service/
├── controllers/     # Routers FastAPI: solo HTTP + validación, sin lógica de negocio
├── services/        # Orquestación: semáforo de concurrencia, timeouts, transformación
├── repositories/     # Adaptador sobre Crawl4AI (sustituible vía Protocol)
├── domain/           # Modelos Pydantic de dominio (request/response/entidades)
├── core/             # Settings, logging (Loguru), config de Crawl4AI, lifespan
├── dependencies.py   # Proveedores de FastAPI Depends
└── main.py           # Punto de entrada de la app
```

- `controllers` depende de `services` a través de `Depends`.
- `services` depende de la interfaz `ScraperRepository` (un `Protocol`), no de
  Crawl4AI directamente — se puede sustituir la implementación sin tocar la
  lógica de negocio.
- `repositories/crawl4ai_repository.py` es el único módulo que importa
  `crawl4ai` para ejecutar el scraping real.
- El navegador de Crawl4AI se inicializa una única vez como singleton en el
  `lifespan` de FastAPI (`src/crawl4ai_scraper_service/core/lifespan.py`) y se
  reutiliza en todas las peticiones.

## Requisitos

- Python 3.14+
- [`uv`](https://docs.astral.sh/uv/) para gestión de dependencias
- Docker (opcional, para despliegue en contenedor)

## Puesta en marcha con `uv`

```bash
# 1. Instalar dependencias (incluye dependencias de desarrollo/test)
uv sync

# 2. Instalar los navegadores de Playwright que usa Crawl4AI
uv run crawl4ai-setup
# o, si prefieres el comando de Playwright directamente:
uv run playwright install --with-deps chromium

# 3. Copiar y ajustar la configuración
cp .env.example .env

# 4. Levantar el servicio en modo desarrollo (con recarga si DEBUG=true)
uv run uvicorn crawl4ai_scraper_service.main:app --host 0.0.0.0 --port 8000 --reload

# También puedes ejecutarlo con el entrypoint del propio módulo:
uv run python -m crawl4ai_scraper_service.main
```

La documentación interactiva (Swagger UI) queda disponible en `http://localhost:8000/docs`.

### Ejecutar los tests

```bash
make test           # pytest + cobertura (mínimo 80%, ver pyproject.toml)
make test-cov        # igual, además genera coverage.xml para SonarQube
make lint             # ruff check
make format            # ruff format
make typecheck          # mypy --strict-ish sobre src/
make sonar-check         # test-cov + análisis SonarQube (requiere SONAR_TOKEN en .env)
```

La configuración de `pytest-cov` en `pyproject.toml` exige una cobertura mínima del 80% (`--cov-fail-under=80`); `make test`/`pytest` falla si no se alcanza. Los tests mockean por completo la capa de infraestructura de Crawl4AI, por lo que no requieren navegador ni red real.

## Puesta en marcha con Docker / Makefile

```bash
make build             # imagen multi-arch (amd64+arm64), publicada en registry.home.arpa
make run                # contenedor local de pruebas (puerto 8000, usa .env)
make test-health         # curl al /health de un contenedor ya arrancado
make test-scrape URL=...  # curl al /scrape con una URL de muestra
```

O directamente con `docker`:

```bash
docker build -t crawl4ai-scraper-service .
docker run --rm -p 8000:8000 --env-file .env crawl4ai-scraper-service
```

## Endpoints

### `POST /scrape`

Recibe una URL, ejecuta el pipeline de Crawl4AI (render con Playwright + limpieza de boilerplate + generación de markdown) y devuelve el markdown resultante junto con metadatos.

```bash
curl -X POST http://localhost:8000/scrape \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'
```

Respuesta:

```json
{
  "markdown": "# Example Domain\n\nThis domain is for use in illustrative examples...",
  "metadata": {
    "original_url": "https://example.com/",
    "timestamp": "2026-08-01T09:22:00.123456+00:00",
    "content_length": 187,
    "fallback_applied": false,
    "attempts": 1,
    "resolved_by": "direct",
    "dedicated_browser": false
  }
}
```

#### `params` — overrides opcionales por petición

Cualquier campo omitido (o `null`) usa el valor por defecto del `.env` del despliegue. No hace falta enviar `params` en absoluto si no se necesita cambiar nada.

```bash
curl -X POST http://localhost:8000/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "params": {
      "stealth_mode": true,
      "wait_until": "networkidle",
      "word_count_threshold": 5
    }
  }'
```

| Campo | Tipo | Nivel | Coste |
|---|---|---|---|
| `stealth_mode` | `bool` | Navegador | Navegador **dedicado** si difiere del `.env` — más lento, limitado por `MAX_CONCURRENT_DEDICATED_BROWSERS` |
| `undetected_browser` | `bool` | Navegador | Igual que `stealth_mode` |
| `magic_mode` | `bool` | Ejecución | Sin coste extra — navegador compartido |
| `wait_until` | `"domcontentloaded"` \| `"load"` \| `"networkidle"` | Ejecución | Sin coste extra |
| `page_timeout_ms` | `int` | Ejecución | Sin coste extra |
| `word_count_threshold` | `int` | Ejecución | Sin coste extra |
| `max_retries` | `int` | Ejecución | Sin coste extra |

`stealth_mode`/`undetected_browser` se fijan al lanzar Chromium, no se pueden cambiar en el navegador ya arrancado — por eso, cuando su valor efectivo difiere del `.env` del despliegue, esta petición lanza un Chromium **dedicado** solo para ella (unos segundos más de latencia), limitado por `MAX_CONCURRENT_DEDICATED_BROWSERS` (2 por defecto) para no agotar la RAM en nodos pequeños. El resto de campos (`CrawlerRunConfig` de Crawl4AI) se pueden variar libremente en cada petición sin ningún coste, reutilizando siempre el navegador compartido. `metadata.dedicated_browser` en la respuesta indica cuál de los dos caminos se usó.

Un nombre de campo no reconocido en `params` da `422` (validación estricta, `extra="forbid"`) en vez de ignorarse en silencio.

Códigos de error:

| Situación | HTTP |
|---|---|
| URL inválida en el body, o campo desconocido/inválido en `params` | `422` |
| Timeout esperando un slot de concurrencia (general o de navegador dedicado) | `503` |
| Timeout del scraping individual | `504` |
| Fallo de scraping (bloqueo tras agotar reintentos, error del navegador, etc.) | `502` |

### `GET /health`

Healthcheck del servicio. Devuelve el estado general, si el navegador headless está inicializado y el uso actual del semáforo de concurrencia.

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "ok",
  "browser_ready": true,
  "active_scrapes": 0,
  "max_concurrent_scrapes": 12
}
```

## Configuración (variables de entorno)

Todas las variables se definen en `src/crawl4ai_scraper_service/core/config.py` (pydantic-settings) y se documentan con valores de ejemplo en [`.env.example`](.env.example).

### Aplicación

| Variable | Descripción | Por defecto |
|---|---|---|
| `APP_NAME` | Nombre del servicio | `Crawl4AI Scraper Service` |
| `APP_ENV` | Entorno: `local` / `staging` / `production` | `local` |
| `DEBUG` | Activa recarga automática y trazas detalladas | `false` |
| `HOST` | Host de escucha de Uvicorn | `0.0.0.0` |
| `PORT` | Puerto de escucha | `8000` |

### Logging (Loguru)

| Variable | Descripción | Por defecto |
|---|---|---|
| `LOG_LEVEL` | Nivel mínimo de log (`TRACE`..`CRITICAL`) | `INFO` |
| `LOG_FORMAT` | `text` (legible) o `json` (estructurado) | `text` |
| `LOG_FILE_PATH` | Ruta de fichero de log; vacío = solo consola | *(vacío)* |
| `LOG_ROTATION` | Política de rotación del fichero de log | `10 MB` |
| `LOG_RETENTION` | Retención de logs rotados | `7 days` |

Todo el logging de la aplicación (incluyendo Uvicorn, FastAPI, Playwright y Crawl4AI) se redirige a Loguru mediante un `InterceptHandler` instalado en `src/crawl4ai_scraper_service/core/logging.py`, de forma que exista un único formato y destino de logs.

### Concurrencia y timeouts

| Variable | Descripción | Por defecto |
|---|---|---|
| `MAX_CONCURRENT_SCRAPES` | Nº máximo de scrapes simultáneos (semáforo) | `12` |
| `SCRAPE_TIMEOUT_SECONDS` | Timeout de un scrape individual | `60` |
| `SEMAPHORE_ACQUIRE_TIMEOUT_SECONDS` | Timeout esperando un slot libre del semáforo (`0` = esperar indefinidamente) | `90` |

Las peticiones que exceden `MAX_CONCURRENT_SCRAPES` no se rechazan de inmediato: quedan en espera (backpressure) hasta que se libera un slot o se agota `SEMAPHORE_ACQUIRE_TIMEOUT_SECONDS`.

### Navegador de Crawl4AI

| Variable | Descripción | Por defecto |
|---|---|---|
| `CRAWLER_HEADLESS` | Ejecuta el navegador sin interfaz gráfica | `true` |
| `CRAWLER_VERBOSE` | Logging detallado de Crawl4AI | `false` |
| `CRAWLER_PAGE_TIMEOUT_MS` | Timeout (ms) de carga de página | `60000` |
| `CRAWLER_WAIT_UNTIL` | `domcontentloaded` / `load` / `networkidle` | `domcontentloaded` |
| `MAX_PAGES_BEFORE_RECYCLE` | Nº de páginas servidas por el navegador compartido antes de reciclarlo (crea uno nuevo, drena y cierra el anterior). `0` = deshabilitado (default de la librería, no usar) | `50` |

### Anti-bot / anti-detección

Cada mecanismo es independiente y se activa/desactiva por variable de entorno; toda la configuración se resuelve dinámicamente en `src/crawl4ai_scraper_service/core/crawler_config.py` a partir de estos settings (nada escrito directamente en el código).

| Variable | Descripción | Por defecto |
|---|---|---|
| `ENABLE_STEALTH_MODE` | Stealth mode de Crawl4AI (`navigator.webdriver`, fingerprint de canvas/WebGL, etc.) | `false` |
| `ENABLE_UNDETECTED_BROWSER` | Undetected Browser Adapter de Crawl4AI, para bot-detection avanzada (Cloudflare, DataDome, Akamai) | `false` |
| `ENABLE_MAGIC_MODE` | Magic Mode: simulación de comportamiento humano, gestión de cookies/popups, retardos aleatorios | `false` |
| `ENABLE_PROXY` | Activa el uso de proxy (por ejemplo, un proxy residencial en dominios problemáticos) | `false` |
| `PROXY_SERVER` | URL del proxy (`http://host:puerto`) | *(vacío)* |
| `PROXY_USERNAME` | Usuario del proxy | *(vacío)* |
| `PROXY_PASSWORD` | Contraseña del proxy | *(vacío)* |
| `MAX_RETRIES` | Nº de rondas de reintento cuando se detecta un bloqueo (`0` = sin reintentos) | `2` |

### Markdown

| Variable | Descripción | Por defecto |
|---|---|---|
| `MARKDOWN_WORD_COUNT_THRESHOLD` | Nº mínimo de palabras de un bloque de texto para conservarlo en el markdown final | `10` |

## Notas de diseño

- **Semáforo de concurrencia**: `src/crawl4ai_scraper_service/services/concurrency.py` implementa
  `ScrapeConcurrencyLimiter`, que envuelve un `asyncio.Semaphore` y expone un
  context manager (`slot()`) usado por `ScrapeService`. Si
  `SEMAPHORE_ACQUIRE_TIMEOUT_SECONDS > 0` y se agota, se lanza
  `ConcurrencyLimitTimeoutError`, que el controller traduce a `503`.
- **Timeout individual**: `ScrapeService.scrape_url` envuelve la llamada al
  repositorio en `asyncio.wait_for(..., timeout=SCRAPE_TIMEOUT_SECONDS)`, de
  forma que una web lenta no bloquea el slot del semáforo indefinidamente.
- **Sustitución de la capa de infraestructura**: `ScraperRepository`
  (`src/crawl4ai_scraper_service/repositories/interfaces.py`) es un `Protocol`; cualquier clase que
  implemente `start`, `stop`, `is_ready` y `scrape` puede inyectarse en
  `ScrapeService` sin cambiar la lógica de negocio (útil para tests o para
  sustituir Crawl4AI por otro motor en el futuro).
- ⚠️ **`MAX_PAGES_BEFORE_RECYCLE` no es opcional en la práctica** — el
  navegador Chromium compartido de Crawl4AI acumula procesos `renderer`
  huérfanos con el uso (páginas que la propia librería no logra cerrar tras
  un timeout/crash, error tragado internamente sin excepción visible). Con
  el valor por defecto de la librería (`0`, deshabilitado) esto no tiene
  límite: visto en producción, 39 procesos `renderer` huérfanos y ~5GB de
  RAM en un contenedor sin scrapes en curso. Con el reciclado periódico
  activado, el navegador se relanza cada N páginas y purga lo acumulado.
  **Actualización (2026-08-05)**: el valor de 50 tampoco fue suficiente bajo
  una tanda real con muchos bloqueos anti-bot (452MB -> 5,7GB en ~1h,
  suficiente para agotar la RAM de todo el nodo `pi-utils`, no solo del
  contenedor) — cada reintento de `MAX_RETRIES` sobre una URL bloqueada abre
  más páginas de las que 50 páginas "buenas" compensaban a tiempo. Bajado a
  `15` por defecto. Si vuelve a ocurrir, considerar además: (a) contar
  reintentos, no solo páginas servidas, hacia el umbral de reciclado, o
  (b) un límite de memoria a nivel de contenedor como red de seguridad
  (ver `deploy.resources.limits.memory` en `pi-utils/docker-compose.yml`).
- ⚠️ **`ENABLE_UNDETECTED_BROWSER=true` necesita el navegador de `patchright`,
  no el de `playwright`** — el Undetected Browser Adapter de Crawl4AI corre
  sobre `patchright` (fork de Playwright), que gestiona su propio build de
  Chromium bajo el mismo `PLAYWRIGHT_BROWSERS_PATH`. El `Dockerfile` instala
  ambos (`playwright install --with-deps chromium` y `patchright install
  --with-deps chromium`) — si se quita uno de los dos, el modo
  correspondiente falla en el arranque con `BrowserType.launch: Executable
  doesn't exist`. Los tests no lo detectan (mockean el repositorio, nunca
  lanzan un navegador real) — solo se manifiesta desplegado de verdad.
- ⚠️ **`PruningContentFilter` (el filtro de `core/crawler_config.py` que
  genera el markdown final) puede descartar el artículo real en sitios con
  maquetación compleja** — visto en producción con `arstechnica.com`
  (devolvía solo el `<title>`) y un blog de Substack (devolvía la sección
  de comentarios/recomendados en vez del artículo). Confirmado con una
  llamada directa a `crawler.arun()` que el HTML completo sí se captura —
  el problema es la heurística de puntuación del filtro, no la carga de la
  página ni bloqueo anti-bot; cambiar `wait_until` a `networkidle` no lo
  soluciona. Sin resolver todavía — ver `docs/10-instalacion-pi4-utils.md`
  para el detalle y las vías de arreglo consideradas.
