# pdf2chunks-service

Microservicio FastAPI que extrae el texto de ficheros **PDF** — nativo, con
fallback a **OCR** (Tesseract, vía [PyMuPDF](https://pymupdf.readthedocs.io/))
en páginas sin texto suficiente — y lo trocea en fragmentos (`chunks`) listos
para indexar en un pipeline RAG.

```
PDF (carpeta entrada) --> pdf2chunks-service --> chunks .json/.jsonl (carpeta salida)
```

Cada chunk incluye `document_id` (hash SHA-256 del PDF), `page`, `chapter`
(resuelto contra la tabla de contenidos del PDF si existe), `title`/`author`
(metadatos del documento), `chunk_index`, `char_count` y `ocr_applied`.

## Endpoints

### `GET /health`

```json
{"status": "ok", "version": "0.1.0", "service": "pdf2chunks-service"}
```

`version` se lee de los metadatos del paquete instalado (`importlib.metadata`), no está escrita directamente en el código — siempre coincide con `pyproject.toml`.

### `POST /process`

Procesa por lote todos los `.pdf` de `input_path` (fichero individual o
carpeta) y escribe los chunks de cada PDF procesado con éxito en
`output_path` (un fichero `.json`/`.jsonl` por PDF, según
`PDF2CHUNKS_OUTPUT_FORMAT`). Nunca lanza excepciones al llamador: cualquier
fallo de un fichero individual se refleja en `results`, permitiendo que n8n
(u otro orquestador) itere y siga con el resto.

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
      "source_file": "/data/input/documento.pdf",
      "success": true,
      "output_file": "/data/output/documento.json",
      "chunk_count": 14,
      "error": null,
      "warnings": []
    }
  ]
}
```

`status` general es `success` (todo bien), `partial_failure` (alguno falló)
o `failure` (todo falló, `input_path` no existe, o no se encontró ningún PDF).
La API usa siempre la configuración del servicio (`PDF2CHUNKS_*`); para
sobrescribir OCR/chunking por invocación, usa el modo CLI.

## Uso rápido

```bash
curl http://localhost:8004/health

curl -X POST http://localhost:8004/process \
  -H "Content-Type: application/json" \
  -d '{"input_path": "/data/input", "output_path": "/data/output"}'
```

## Modo CLI (alternativo a la API)

Pensado para invocarse desde n8n (nodo Execute Command/SSH) como contenedor
efímero por lote de ficheros, sin mantener el servicio siempre arriba. Usa el
mismo `PdfProcessingService` que la API, así que el comportamiento
(extracción, OCR, chunking) es idéntico; a diferencia de la API, el CLI
permite sobrescribir la configuración de troceado por invocación.

```bash
docker run --rm --entrypoint python3 \
  -v /ruta/local/entrada:/data/input:ro \
  -v /ruta/local/salida:/data/output \
  registry.home.arpa/pdf2chunks-service:latest \
  -m pdf2chunks_service.cli /data/input /data/output
```

Flags opcionales de sobrescritura: `--ocr-char-threshold`, `--ocr-language`,
`--chunk-size-tokens`, `--chunk-overlap-ratio`, `--chunking-strategy`,
`--output-format`.

**Códigos de salida** (convención propia de este servicio, distinta de la de
`epub2pdf-service` — ver `cli.py` para el porqué):

| Código | Significado |
|---|---|
| `0` | Éxito total — todos los PDF se procesaron correctamente. |
| `1` | Fallo total — todos fallaron, no había PDF que procesar, o la ruta de entrada no existe. |
| `2` | Fallo parcial — al menos uno tuvo éxito y al menos uno falló. |

## Desarrollo local

```bash
# Construir imagen
make build

# Arrancar localmente en modo API
make run

# Test contra un contenedor ya arrancado (make run, en otra terminal)
make test-health
make test-process FILE=/ruta/al/documento.pdf
```

## Estructura del proyecto

Arquitectura por capas (igual que `apikey-service`/`markitdown-service`/
`epub2pdf-service` — ver `docs/desarrollo-microservicios-python.md`), sin
capa de persistencia porque este servicio no tiene estado:

```
src/pdf2chunks_service/
├── main.py                                ← app FastAPI, registro de routers, arranque de logging
├── cli.py                                 ← modo CLI alternativo (mismo PdfProcessingService que la API, con overrides)
├── config.py                              ← Settings (pydantic-settings, prefijo PDF2CHUNKS_)
├── schemas.py                             ← modelos de request/response (Pydantic)
├── dependencies.py                        ← providers de FastAPI (Depends)
├── logging_setup.py                       ← configuración de loguru (compartida entre main.py y cli.py)
├── controllers/
│   ├── health_controller.py               ← GET /health
│   └── process_controller.py              ← POST /process — traduce resultados del service a la respuesta HTTP
├── services/
│   ├── pdf_processing_service.py          ← reglas de negocio (descubrimiento de ficheros, extracción + OCR por página, orquestación) — sin FastAPI ni PyMuPDF/Tesseract directos
│   └── chunking_strategies.py             ← patrón Strategy de troceado (FixedSizeChunkingStrategy; recursive/semantic reservadas)
├── infrastructure/
│   ├── pdf_document.py                    ← envoltorio sobre PyMuPDF (fitz): abrir, TOC, metadatos, texto nativo por página
│   ├── ocr_engine.py                      ← envoltorio sobre el OCR de PyMuPDF (Tesseract)
│   └── chunk_writer.py                    ← serialización de resultados a fichero (.json/.jsonl)
└── domain/
    └── models.py                          ← modelos puros: TocEntry, DocumentMetadata, PageContent, Chunk, ProcessingResult, excepciones
```

`PdfProcessingService` no conoce FastAPI ni argparse (expone resultados como
`ProcessingResult`, que el controller o el CLI traducen a su formato de
salida correspondiente), ni conoce PyMuPDF/Tesseract directamente (habla con
`infrastructure.pdf_document`/`infrastructure.ocr_engine`). Mismo criterio de
aislamiento por capas que `apikey_service.services.apikey_service` y
`epub2pdf_service.services.conversion_service`.

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

Los tests generan PDFs reales en memoria con PyMuPDF (`tests/conftest.py`,
incluyendo casos con TOC, sin texto nativo, encriptados y corruptos) — no
hace falta ningún PDF externo para correr la batería completa. El OCR real
se mockea a nivel de `infrastructure.ocr_engine.ocr_page` en los tests que no
necesitan verificar Tesseract en sí.

### Análisis SonarQube

```bash
make sonar-check   # test-cov + análisis pysonar contra la instancia del clúster
```

Requiere `SONAR_HOST_URL`, `SONAR_TOKEN` y `REQUESTS_CA_BUNDLE` en `.env`
(ver `.env.example` y `docs/09-instalacion-pi3-sonarqube.md`, sección 8.1,
para el porqué de `REQUESTS_CA_BUNDLE`).
