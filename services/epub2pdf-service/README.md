# epub2pdf-service

Microservicio FastAPI que convierte ficheros **EPUB** a **PDF** usando el motor de conversión de [Calibre](https://calibre-ebook.com/) (`ebook-convert`), y extrae los metadatos del EPUB (título, autor, fecha, idioma, editorial) con [`ebooklib`](https://github.com/aerkalov/ebooklib) en un fichero `.meta.json` junto al PDF generado.

```
EPUB (carpeta entrada) --> epub2pdf-service --> PDF + .meta.json (carpeta salida)
```

## Endpoints

### `GET /health`

```json
{"status": "ok", "version": "0.1.0", "service": "epub2pdf-service"}
```

`version` se lee de los metadatos del paquete instalado (`importlib.metadata`), no está escrita directamente en el código — siempre coincide con `pyproject.toml`.

### `POST /convert`

Convierte por lote todos los `.epub` de `input_path` (fichero individual o carpeta) y deja los PDF junto con sus sidecars `.meta.json` en `output_path`. Nunca lanza excepciones al llamador: cualquier fallo de un fichero individual se refleja en `results`, permitiendo que n8n (u otro orquestador) itere y siga con el resto.

```json
{"input_path": "/data/input", "output_path": "/data/output"}
```

Respuesta:

```json
{
  "status": "success",
  "total": 2,
  "successes": 2,
  "failures": 0,
  "results": [
    {
      "source_path": "/data/input/libro.epub",
      "output_path": "/data/output/libro.pdf",
      "status": "success",
      "reason": null,
      "message": null,
      "duration_seconds": 4.21
    }
  ]
}
```

`status` general es `success` (todo bien), `partial_failure` (alguno falló) o `failure` (todo falló, o `input_path` no existe). Motivos de fallo posibles en `reason`: `corrupt_epub`, `timeout`, `drm_protected`, `calibre_failure`, `unknown`.

## Uso rápido

```bash
curl http://localhost:8003/health

curl -X POST http://localhost:8003/convert \
  -H "Content-Type: application/json" \
  -d '{"input_path": "/data/input", "output_path": "/data/output"}'
```

## Modo CLI (alternativo a la API)

Pensado para invocarse desde n8n (nodo Execute Command/SSH) como contenedor efímero por lote de ficheros, sin mantener el servicio siempre arriba. Usa el mismo `ConversionService` que la API, así que el comportamiento (metadatos, colisiones de nombre, manejo de errores) es idéntico.

```bash
docker run --rm --entrypoint python3 \
  -v /ruta/local/entrada:/data/input:ro \
  -v /ruta/local/salida:/data/output \
  registry.home.arpa/epub2pdf-service:latest \
  -m epub2pdf_service.cli --input /data/input --output /data/output
```

Sin `--input`/`--output`, el CLI usa `EPUB2PDF_INPUT_PATH`/`EPUB2PDF_OUTPUT_PATH`. Códigos de salida: `0` éxito total, `1` fallo parcial, `2` fallo total (ruta de entrada inexistente, carpeta vacía, o todos los ficheros fallaron).

## Desarrollo local

```bash
# Construir imagen
make build

# Arrancar localmente en modo API
make run

# Test contra un contenedor ya arrancado (make run, en otra terminal)
make test-health
make test-convert FILE=/ruta/al/libro.epub
```

## Estructura del proyecto

Arquitectura por capas (igual que `apikey-service`/`markitdown-service` — ver `docs/06-instalacion-pi1-dns.md`), sin capa de persistencia porque este servicio no tiene estado:

```
src/epub2pdf_service/
├── main.py                              ← app FastAPI, registro de routers, arranque de logging/telemetría
├── cli.py                               ← modo CLI alternativo (mismo ConversionService que la API)
├── config.py                            ← Settings (pydantic-settings, prefijo EPUB2PDF_)
├── schemas.py                           ← modelos de request/response (Pydantic)
├── dependencies.py                      ← providers de FastAPI (Depends)
├── logging_setup.py                     ← configuración de loguru (compartida entre main.py y cli.py)
├── telemetry.py                         ← instrumentación OpenTelemetry (trazas, modo no-op sin endpoint)
├── controllers/
│   ├── health_controller.py             ← GET /health
│   └── convert_controller.py            ← POST /convert — traduce resultados del service a la respuesta HTTP
├── services/
│   └── conversion_service.py            ← reglas de negocio (descubrimiento de ficheros, resolución de nombres, orquestación) — sin FastAPI ni subprocess directo
├── infrastructure/
│   ├── calibre_converter.py             ← envoltorio sobre el binario `ebook-convert` (subprocess)
│   └── metadata_extractor.py            ← envoltorio sobre la librería `ebooklib`
└── domain/
    └── models.py                        ← modelos puros: ConversionResult, EpubMetadata, enums de estado/motivo
```

`ConversionService` no conoce FastAPI ni argparse (expone resultados como `ConversionResult`, que el controller o el CLI traducen a su formato de salida correspondiente), ni conoce `ebooklib`/`subprocess` directamente (habla con `infrastructure.calibre_converter`/`infrastructure.metadata_extractor`). Mismo criterio de aislamiento por capas que `apikey_service.services.apikey_service` y `markitdown_service.services.conversion_service`.

## Tests, cobertura, lint y análisis estático

Proyecto `uv` autocontenido (no comparte tooling con el resto del monorepo).

```bash
cp .env.example .env   # copiar plantilla; ajustar SONAR_TOKEN si vas a ejecutar make sonar

make test        # pytest (cobertura mínima 80%, exigida en pyproject.toml)
make test-cov    # igual, además genera coverage.xml
make lint         # ruff check .
make format       # ruff format .
make typecheck    # mypy src/
```

Todas las invocaciones a Calibre se mockean en los tests vía `subprocess.run` (dentro de `infrastructure/calibre_converter.py`) — no hace falta tener `ebook-convert` instalado en el entorno de desarrollo para correr los tests.

### Análisis SonarQube

```bash
make sonar-check   # test-cov + análisis pysonar contra la instancia del clúster
```

Requiere `SONAR_HOST_URL`, `SONAR_TOKEN` y `REQUESTS_CA_BUNDLE` en `.env` (ver `.env.example` y `docs/09-instalacion-pi3-sonarqube.md`, sección 8.1, para el porqué de `REQUESTS_CA_BUNDLE`).

## Instrumentación OpenTelemetry

Cada conversión individual crea un span `epub_to_pdf.convert` con los atributos `epub2pdf.filename`, `epub2pdf.file_size_bytes`, `epub2pdf.duration_seconds` y `epub2pdf.result` (`success`|`failure`). Si `EPUB2PDF_OTEL_EXPORTER_OTLP_ENDPOINT` no está configurado (o `EPUB2PDF_OTEL_ENABLED=false`), el servicio sigue funcionando con normalidad: los spans se generan pero no se exportan a ningún backend (modo no-op), sin producir errores.

## Notas sobre Calibre y DRM

Calibre **no puede** convertir EPUB protegidos con DRM sin complementos adicionales (fuera del alcance de este servicio). Estos casos se detectan a partir de la salida de error de `ebook-convert` y se registran con `reason: "drm_protected"`, permitiendo que el resto del lote continúe procesándose con normalidad.

## Notas sobre el `Dockerfile` — tres fallos reales al construir la imagen

El primer `make build` real falló tres veces seguidas, cada vez un poco más adentro. Documentado aquí para no volver a perder el tiempo si algún día hay que tocar la instalación de Calibre:

1. **Faltaban varias librerías del sistema.** El instalador de Calibre hace
   su propia comprobación de dependencias antes de instalar nada — en la
   base `python:3.12-slim` actual (Debian 13 "trixie"), `libgl1` ya no trae
   consigo `libopengl0`, y Calibre 9.x usa Qt6, que necesita bastantes más
   librerías `libxcb-*` de las que hacían falta con Qt5. Sin ellas, el
   propio instalador aborta con "You are missing the system library...".
2. **El símlink a `ebook-convert` apuntaba a una ruta que no existe.** El
   instalador, con `isolated=y`, deja los binarios en
   `/opt/calibre/calibre/ebook-convert` (un nivel más adentro de lo que
   parece), no en `/opt/calibre/ebook-convert`. Un símlink roto no da error
   al construir la imagen — solo se nota al intentar ejecutar `ebook-convert`
   de verdad.
3. **La conversión a PDF usa Qt WebEngine (Chromium embebido) para
   renderizar, y Chromium se niega a arrancar como root sin `--no-sandbox`.**
   El contenedor corre como root (la imagen base no define un usuario
   propio), así que sin `ENV QTWEBENGINE_CHROMIUM_FLAGS=--no-sandbox` la
   conversión fallaba en el último paso con `Running as root without
   --no-sandbox is not supported`, después de haber cargado bien tanto
   Calibre como los metadatos del EPUB.

Verificado de extremo a extremo tras corregir los tres: `docker build` limpio, conversión real de un EPUB de prueba a PDF (modo CLI y modo API), con metadatos correctos en el `.meta.json`.

**Pendiente, no bloqueante:** el contenedor sigue corriendo como root. El `--no-sandbox` de Chromium es la solución estándar para este caso (el aislamiento real ya lo da el propio contenedor, no el sandbox interno de Chromium), pero migrar a un usuario sin privilegios seguiría siendo una mejora de seguridad en profundidad razonable — no se ha hecho todavía porque implica revisar permisos de `/data/input`/`/data/output` cuando se montan volúmenes del host, y no era el objetivo de este arreglo puntual.
