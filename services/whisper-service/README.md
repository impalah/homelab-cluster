# whisper-service

Microservicio FastAPI para transcripción de audio a texto, usando [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (CTranslate2) con soporte CUDA.

## Endpoints

### `GET /health`

```json
{"status": "ok", "version": "0.1.0", "service": "whisper-service", "model": "large-v3", "device": "cuda", "compute_type": "float16", "language": "es"}
```

`version` se lee de los metadatos del paquete instalado (`importlib.metadata`), no está escrita directamente en el código — siempre coincide con `pyproject.toml`.

### `POST /transcribe`

Parámetros (multipart/form-data):

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `file` | binary | sí | Audio en mp3, wav, ogg, m4a o flac |
| `language` | string | no | Código ISO 639-1 (ej. `es`, `en`). Por defecto, `WHISPER_LANGUAGE` |
| `task` | string | no | `transcribe` (por defecto) o `translate` (traduce al inglés) |

Respuesta:

```json
{
  "text": "Texto transcrito...",
  "language": "es",
  "language_probability": 0.9877,
  "duration": 12.35,
  "model": "large-v3"
}
```

El modelo se carga **una sola vez** al arrancar el servicio (`lifespan` en `main.py`, delega en `infrastructure/whisper_model.py`); si se llama a `/transcribe` antes de que termine de cargar, responde `503`. Si la carga falla en el `device`/`compute_type` configurados (típicamente `cuda`/`float16` sin GPU disponible), cae automáticamente a `cpu`/`int8` — mucho más lento, pero evita que el servicio no arranque en absoluto. El fallback solo se intenta una vez al arrancar; si también falla en CPU, el error sí se propaga y el servicio no arranca.

El `content-type` del fichero subido se valida contra `ALLOWED_CONTENT_TYPES` en `services/transcription_service.py` — si el cliente envía uno y no está en la lista, responde `415` (si no envía ninguno, no hay nada que validar y se intenta transcribir igual). La decodificación real del audio la hace `faster-whisper` internamente mediante PyAV (FFmpeg estático embebido en el wheel) — soporta bastantes más formatos de los que se anuncian aquí; esta lista es la barrera de entrada explícita de la API, no una limitación real del decodificador.

La transcripción en sí se ejecuta en un hilo del ejecutor por defecto de asyncio (`loop.run_in_executor`, en `TranscriptionService.transcribe`), no directamente en el bucle de eventos — así `/health` y otras peticiones concurrentes no se bloquean mientras se transcribe un audio largo. Ojo con esto si se toca `infrastructure/whisper_model.py`: `faster-whisper` devuelve los segmentos como un generador perezoso, así que el trabajo pesado ocurre al **iterarlos**, no en la llamada a `model.transcribe()` — por eso `run_transcription()` envuelve ambas cosas juntas antes de pasarlo al executor; envolver solo la llamada a `transcribe()` no habría resuelto el bloqueo.

## Uso rápido

```bash
curl http://localhost:9800/health

curl -X POST http://localhost:9800/transcribe \
  -F "file=@/ruta/al/audio.mp3" | jq .text
```

## Desarrollo local

```bash
# Construir imagen
make build

# Arrancar localmente (requiere GPU NVIDIA — usa --gpus all)
make run

# Test contra un contenedor ya arrancado (make run, en otra terminal)
make test-health
make test-transcribe FILE=/tmp/audio.mp3
```

## Estructura del proyecto

Arquitectura por capas (igual que `apikey-service` — ver `docs/06-instalacion-pi1-dns.md`), sin capa de persistencia porque este servicio no tiene estado:

```
src/whisper_service/
├── main.py                                    ← app FastAPI, lifespan (carga el modelo al arrancar), registro de routers
├── config.py                                   ← Settings (pydantic-settings)
├── schemas.py                                  ← modelos de request/response (Pydantic)
├── dependencies.py                             ← providers de FastAPI (Depends)
├── controllers/
│   ├── health_controller.py                    ← GET /health
│   └── transcribe_controller.py                ← POST /transcribe — traduce excepciones del service a HTTPException
├── services/
│   └── transcription_service.py                ← reglas de negocio (validación, orquestación) — sin FastAPI ni faster-whisper directo
└── infrastructure/
    └── whisper_model.py                        ← envoltorio sobre faster-whisper: carga con fallback CUDA→CPU y ejecución de la transcripción
```

`TranscriptionService` no conoce FastAPI (lanza excepciones propias — `ModelNotLoadedError`, `UnsupportedContentTypeError`, etc. — que el controller traduce al código HTTP correspondiente), ni conoce `faster_whisper` directamente (habla con las funciones de `infrastructure/whisper_model.py`). El modelo cargado vive como estado de módulo en esa misma capa de infraestructura (`set_model`/`get_model`), no en `main.py`.

## Tests, cobertura, lint y análisis estático

Proyecto `uv` autocontenido (no comparte tooling con el resto del monorepo). Los tests **no** cargan un `WhisperModel` real ni tocan CUDA:
- `test_whisper_model.py` — unitarios de la carga con fallback CUDA→CPU (`WhisperModel` mockeado).
- `test_transcription_service.py` — unitarios del service con un modelo falso inyectado directamente (sin pasar por FastAPI).
- `test_controllers.py`/`test_main.py` — de integración vía `TestClient`, monkeypatcheando `whisper_service.infrastructure.whisper_model._model`.

```bash
cp .env.example .env   # copiar plantilla; ajustar SONAR_TOKEN si vas a ejecutar make sonar

make test        # pytest (cobertura mínima 80%, exigida en pyproject.toml)
make test-cov    # igual, además genera coverage.xml
make lint        # ruff check .
make format      # ruff format .
make typecheck   # mypy src/
```

Estado actual: 21 tests, 100% de cobertura de statements en todas las capas, `ruff` y `mypy` limpios.

### Análisis SonarQube

```bash
make sonar-check   # test-cov + análisis pysonar contra la instancia del clúster
```

Requiere `SONAR_HOST_URL`, `SONAR_TOKEN` y `REQUESTS_CA_BUNDLE` en `.env` (ver `.env.example` y `docs/09-instalacion-pi3-sonarqube.md`, sección 8.1). Quality Gate **OK**, cobertura 100%, 0 bugs, 0 vulnerabilidades — quedan 7 code smells abiertos como backlog de mejora (no bloquean la Quality Gate), mismo tipo de sugerencias de estilo moderno de FastAPI que en `apikey-service`/`markitdown-service` (`Annotated` en los parámetros de `File`/`Form`, y el propio `S8415` de documentar `HTTPException` en `responses` sigue sugiriéndose incluso después de añadir el parámetro `responses={...}` al decorador de `/transcribe` — se dejó así, cosmético, igual que en los otros dos servicios).

⚠️ Al añadir el rechazo real por `content-type` (415, ver más arriba) en un servicio que ya tenía un análisis previo, el nuevo `HTTPException` disparó un hallazgo `S8415` que SonarQube contó como "código nuevo" y **tumbó la Quality Gate** (`new_violations > 0`) hasta documentar `responses=` en el endpoint. Al añadir un `raise HTTPException(...)` nuevo en un servicio con baseline ya establecida, conviene documentarlo en `responses=` desde el principio para no repetir esto.
