# markitdown-service

Microservicio FastAPI para convertir documentos de cualquier formato a Markdown, usando la librería [MarkItDown de Microsoft](https://github.com/microsoft/markitdown).

## Formatos soportados

PDF, DOCX, XLSX, PPTX, HTML, CSV, JSON, XML, TXT, imágenes (JPEG, PNG, GIF, WebP), audio (MP3, WAV), ZIP.

## Endpoints

### `GET /health`

```json
{"status": "ok", "version": "0.1.0", "service": "markitdown-service"}
```

`version` se lee de los metadatos del paquete instalado (`importlib.metadata`), no está escrita directamente en el código — siempre coincide con `pyproject.toml`.

### `POST /convert`

Parámetros (multipart/form-data):

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `file` | binary | sí | Archivo a convertir |
| `filename_hint` | string | no | Nombre con extensión si el Content-Type no es específico |

Respuesta:

```json
{
  "filename": "documento.pdf",
  "extension": ".pdf",
  "size_bytes": 45678,
  "markdown": "# Título del documento\n\nContenido...",
  "characters": 1234
}
```

## Uso rápido

```bash
# Healthcheck
curl http://localhost:8001/health

# Convertir un PDF
curl -X POST http://localhost:8001/convert \
  -F "file=@/ruta/al/documento.pdf" | jq .markdown

# Convertir una página HTML (como archivo)
curl -X POST http://localhost:8001/convert \
  -F "file=@index.html" \
  -F "filename_hint=index.html" | jq .
```

## Desarrollo local

```bash
# Construir imagen
make build

# Arrancar localmente
make run

# Test contra un contenedor ya arrancado (make run, en otra terminal)
make test-health
make test-convert FILE=/tmp/test.pdf
```

## Estructura del proyecto

Arquitectura por capas (igual que `apikey-service` — ver `docs/06-instalacion-pi1-dns.md`), sin capa de persistencia porque este servicio no tiene estado:

```
src/markitdown_service/
├── main.py                              ← app FastAPI, registro de routers (sin lógica)
├── config.py                            ← Settings (pydantic-settings)
├── schemas.py                           ← modelos de request/response (Pydantic)
├── dependencies.py                      ← providers de FastAPI (Depends)
├── controllers/
│   ├── health_controller.py             ← GET /health
│   └── convert_controller.py            ← POST /convert — traduce excepciones del service a HTTPException
├── services/
│   └── conversion_service.py            ← reglas de negocio (validación, orquestación) — sin FastAPI ni MarkItDown directo
└── infrastructure/
    └── document_converter.py            ← envoltorio sobre la librería MarkItDown
```

`ConversionService` no conoce FastAPI (lanza excepciones propias — `UnsupportedFormatError`, `EmptyFileError`, etc. — que el controller traduce al código HTTP correspondiente), ni conoce `MarkItDown` directamente (habla con `DocumentConverter`, la capa de infraestructura). Mismo criterio de aislamiento por capas que `apikey_service.services.apikey_service`/`apikey_service.repositories.apikey_repository`.

## Tests, cobertura, lint y análisis estático

Proyecto `uv` autocontenido (no comparte tooling con el resto del monorepo). Requiere Python 3.12 — ver nota sobre `.python-version` más abajo.

```bash
cp .env.example .env   # copiar plantilla; ajustar SONAR_TOKEN si vas a ejecutar make sonar

make test        # pytest (cobertura mínima 80%, exigida en pyproject.toml)
make test-cov    # igual, además genera coverage.xml
make lint        # ruff check .
make format      # ruff format .
make typecheck   # mypy src/
```

Estado actual: 22 tests (unitarios de `ConversionService` con el conversor mockeado + de integración HTTP vía `TestClient`), 100% de cobertura de statements en todas las capas, `ruff` y `mypy` limpios.

### Análisis SonarQube

```bash
make sonar-check   # test-cov + análisis pysonar contra la instancia del clúster
```

Requiere `SONAR_HOST_URL`, `SONAR_TOKEN` y `REQUESTS_CA_BUNDLE` en `.env` (ver `.env.example` y `docs/09-instalacion-pi3-sonarqube.md`, sección 8.1, para el porqué de `REQUESTS_CA_BUNDLE`). Resultado del primer análisis: Quality Gate **OK**, cobertura 100%, 0 vulnerabilidades — quedan 8 hallazgos abiertos como backlog de mejora (no bloquean la Quality Gate): 1 bug MAJOR (`tempfile.NamedTemporaryFile` síncrono dentro del endpoint `async /convert` — migrar a `aiofiles`, ya declarado como dependencia) y 7 code smells de estilo moderno de FastAPI (`Annotated` en los parámetros, documentar cada `HTTPException` en `responses`).

### Nota: Python 3.12 obligatorio (`onnxruntime`)

El fichero `.python-version` en la raíz del servicio fija Python 3.12 — `markitdown` arrastra `onnxruntime==1.20.1`, que no publica wheel para Python 3.14. Sin este fichero, `uv run` en un sistema con Python 3.14 por defecto falla en seco al resolver dependencias.
