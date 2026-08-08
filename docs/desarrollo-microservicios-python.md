# Desarrollo de microservicios Python en homelab-cluster

Guía de referencia con **todas** las convenciones que siguen los microservicios Python de este clúster (`services/apikey-service`, `services/markitdown-service`, `services/whisper-service`, `services/crawl4ai-scraper-service`, `services/epub2pdf-service`, `services/pdf2chunks-service`). No es una propuesta: es una descripción fiel de patrones ya aplicados de forma consistente en varios servicios reales, pensada para poder crear un microservicio nuevo — o adaptar uno existente — sin tener que redescubrir cada decisión desde cero.

Pensada también para usarse como referencia de estilo por un asistente de IA (Claude u otro) al generar o revisar código de estos servicios.

---

## 1. Qué es un "microservicio de este clúster"

Un microservicio propio, en `services/<nombre>-service/`, con:

- Su propio `pyproject.toml`, `uv.lock`, entorno virtual y ciclo de vida — **no** comparte dependencias ni tooling con el resto del monorepo.
- Una imagen Docker propia, publicada en `registry.home.arpa` (nunca construida `on-the-fly` en el nodo donde se despliega — ver sección 9).
- Cobertura de tests obligatoria ≥ 80%, verificada tanto en local (`make test`) como en SonarQube (`make sonar-check`).
- Documentación en un `README.md` con una estructura fija (ver sección 12).

No todos son servicios HTTP: `epub2pdf-service` tiene además un modo CLI. Lo que es constante es la arquitectura por capas interna, no el punto de entrada.

---

## 2. Nombrado

- **Directorio y nombre del proyecto** (`services/<nombre>`, `[project].name` en `pyproject.toml`, `SERVICE_NAME` en el `Makefile`): `kebab-case`, terminado siempre en **`-service`** — `apikey-service`, `markitdown-service`, `whisper-service`, `crawl4ai-scraper-service`, `epub2pdf-service`. La única excepción histórica sería un servicio que ya tuviera un nombre de producto/librería consolidado, pero en este clúster no hay ninguno así todavía.
- **Paquete Python** (`src/<paquete>/`, imports): `snake_case` con el mismo sufijo, en su forma con guion bajo — `apikey_service`, `markitdown_service`, `epub2pdf_service`. Es decir: `nombre-service` (proyecto) ↔ `nombre_service` (paquete). Nunca se abrevia ni se le quita el sufijo al paquete aunque el nombre del proyecto sea largo.
- **Imagen Docker**: `homelab/<nombre>-service` en local, `registry.home.arpa/<nombre>-service` en el registry — mismo nombre que el proyecto, sin variación.

---

## 3. Gestión de dependencias: `uv`, no `pip`/`poetry`/`pipenv`

- `pyproject.toml` con `[project.dependencies]` (runtime) y `[dependency-groups] dev = [...]` (test/lint/análisis) — **nunca** `requirements.txt`/`requirements-dev.txt`.
- Build backend **hatchling**, no `setuptools`:
  ```toml
  [build-system]
  requires = ["hatchling"]
  build-backend = "hatchling.build"

  [tool.hatch.build.targets.wheel]
  packages = ["src/<paquete>"]
  ```
- Layout `src/` siempre (`src/<paquete>/...`), nunca paquete a nivel de raíz del proyecto.
- `uv.lock` **se versiona** (reproducibilidad del build) — nunca lo pongas en `.gitignore`, aunque `.venv/` sí lo esté.
- Versiones de dependencias con mínimo (`fastapi>=0.111.0`), no fijadas a una versión exacta (`==`) salvo que haya una razón documentada para ello. Fijar con `==` dificulta recibir parches de seguridad vía `uv sync` y no aporta más reproducibilidad que la que ya da `uv.lock`.
- Si hay algún riesgo conocido de que `uv run` resuelva un intérprete de sistema incompatible con alguna dependencia (pasó con `markitdown` + `onnxruntime` en Python 3.14, sin wheel disponible), fijar un `.python-version` en la raíz del servicio con la versión exacta que sí funciona, coincidiendo con la imagen base del `Dockerfile`.
- Comandos: `uv sync` (instala), `uv run pytest`/`uv run ruff ...`/`uv run mypy ...` (ejecuta dentro del entorno del proyecto sin activarlo a mano), `uvx --from=<paquete> <comando>` (ejecuta una herramienta puntual sin añadirla como dependencia — se usa para `toml-cli` y `bump2version` en el `Makefile`, ver sección 8).

---

## 4. Arquitectura por capas

Todos los servicios HTTP siguen la misma separación, con nombres de módulo idénticos entre servicios (facilita moverse de uno a otro):

```
src/<paquete>/
├── __init__.py            ← __version__ (ver sección 6)
├── main.py                ← app FastAPI: arranca logging/telemetría, registra routers
├── config.py               ← Settings (pydantic-settings)
├── schemas.py               ← modelos Pydantic de request/response (el "contrato" HTTP)
├── dependencies.py           ← providers de FastAPI Depends()
├── controllers/               ← un router por endpoint o grupo de endpoints relacionados
│   ├── health_controller.py
│   └── <recurso>_controller.py
├── services/                    ← reglas de negocio
│   └── <algo>_service.py
├── infrastructure/                ← envoltorios sobre librerías/binarios externos
│   └── <dependencia_externa>.py
├── repositories/                   ← SOLO si hay base de datos (ver 4.4)
│   └── <algo>_repository.py
└── domain/                          ← opcional: modelos de negocio puros (ver 4.5)
    └── models.py
```

### 4.1 Regla de dependencia entre capas

```
controllers  →  services  →  infrastructure / repositories
     ↓              ↓
  schemas       domain (si existe)
```

- **`controllers/`** solo sabe de HTTP: recibe la petición, la valida con `schemas.py`, llama al service inyectado por `Depends()`, traduce las excepciones del service a `HTTPException` con el código correcto. **No** contiene lógica de negocio.
- **`services/`** contiene las reglas de negocio. **No conoce FastAPI** (no importa `fastapi`, no lanza `HTTPException`) ni la librería/herramienta externa concreta (no importa `subprocess`, `ebooklib`, `markitdown`, SQLAlchemy...) — habla con `infrastructure`/`repositories` a través de una interfaz mínima. Lanza excepciones propias (subclases de una excepción base del propio módulo), que el controller traduce.
- **`infrastructure/`** aísla una dependencia externa concreta (un binario vía `subprocess`, una librería de terceros, un cliente HTTP). Es la única capa que puede importar esa dependencia. Si mañana se cambia de librería de conversión, solo cambia este fichero.
- **`repositories/`** (solo si hay base de datos) es acceso a datos puro — sin reglas de negocio. Habla con SQLAlchemy, no con FastAPI ni con el resto de servicios.
- **`domain/`** (opcional) son `dataclass`/`Enum` puros que representan conceptos del negocio (p. ej. `ConversionResult`, `ConversionStatus`) — cero dependencias de framework. Se usa cuando el resultado de una operación tiene forma propia y se comparte entre varios puntos de entrada (API + CLI, por ejemplo) sin que ninguno de los dos sea "el dueño" del modelo.

### 4.2 Cuándo usar `repositories/` (persistencia)

Solo cuando el servicio tiene estado propio en base de datos — hoy, únicamente `apikey-service` (PostgreSQL vía `postgres-main`, SQLAlchemy async + `asyncpg`). El resto de servicios son *stateless* (convierten, transcriben, raspan — no guardan nada) y **no llevan `repositories/`, ni `db.py`, ni SQLAlchemy como dependencia**. No añadas una capa de persistencia "por si acaso": auméntala solo cuando el servicio realmente empiece a guardar algo.

Si hace falta, el patrón es:
```python
class AlgoRepository:
    """Acceso a datos puro — sin reglas de negocio (esas viven en el service)."""
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, ...) -> Algo: ...
    async def get_by_id(self, id: int) -> Algo | None: ...
```
con `db.py` exponiendo `Base`, `engine`, `get_session()` (dependencia de FastAPI que abre/cierra la sesión por petición).

### 4.3 Ejemplo real de la regla de dependencia (markitdown-service)

```python
# services/conversion_service.py — no importa fastapi ni markitdown
class ConversionService:
    def __init__(self, converter: DocumentConverter, max_file_size: int) -> None:
        self._converter = converter  # inyectado, no instanciado aquí
    def convert(self, content: bytes, original_name: str) -> ConversionResult:
        ...
        raise UnsupportedFormatError(ext)  # excepción propia, no HTTPException

# infrastructure/document_converter.py — el único fichero que importa "markitdown"
class DocumentConverter:
    def __init__(self) -> None:
        self._markitdown = MarkItDown()
    def convert(self, file_path: str) -> str:
        return self._markitdown.convert(file_path).text_content

# controllers/convert_controller.py — traduce las excepciones del service a HTTP
try:
    result = service.convert(content, original_name)
except UnsupportedFormatError as exc:
    raise HTTPException(status_code=415, detail=f"Formato no soportado: '{exc.extension}'") from exc
```

### 4.4 Inyección de dependencias

`dependencies.py` es donde se instancian los objetos que necesita cada endpoint, con `Depends()`:

```python
# Objetos "caros" o sin estado por-petición: instancia única a nivel de módulo
_converter = DocumentConverter()

def get_conversion_service() -> ConversionService:
    return ConversionService(_converter, settings.max_file_size)
```

```python
# En el controller:
ConversionServiceDep = Annotated[ConversionService, Depends(get_conversion_service)]

@router.post("/convert")
async def convert(service: ConversionServiceDep, file: UploadFile = File(...)) -> ConversionResponse:
    ...
```

`B008` de ruff (llamada a función en el valor por defecto de un argumento) se dispara en cada endpoint por `= Depends(...)`/`= File(...)`/`= Form(...)` — es el patrón idiomático de FastAPI, no un bug. Se silencia a propósito en `pyproject.toml` (ver sección 7), documentando el motivo en un comentario junto al `ignore`.

---

## 5. Configuración: `pydantic-settings`

Un único fichero `config.py`, un único objeto `settings` instanciado a nivel de módulo:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APIKEY_")  # prefijo = nombre del servicio en mayúsculas

    host: str = "0.0.0.0"
    port: int = 8090
    database_url: str = "postgresql+asyncpg://..."
    admin_token: str = "CHANGE_ME"

settings = Settings()
```

Reglas:
- **Prefijo de variables de entorno = nombre del servicio en mayúsculas** (`APIKEY_`, `MARKITDOWN_`... — nota: `markitdown-service` es la única excepción histórica sin prefijo real, `env_prefix=""`; para servicios nuevos, usa siempre prefijo). Incluye **todas** las variables propias del servicio bajo ese prefijo, incluidas las de OpenTelemetry (`<PREFIJO>_OTEL_EXPORTER_OTLP_ENDPOINT`, no la variable "genérica" `OTEL_EXPORTER_OTLP_ENDPOINT` sin prefijo) — evita colisiones si dos servicios comparten host.
- `settings` es un **singleton** leído una vez, al importar el módulo. Esto es intencional y tiene una consecuencia real para los tests: mutar `os.environ` en mitad de un proceso de test **no** se refleja en `settings` (ya se leyó). Para modificarlo en un test, usa `monkeypatch.setattr(settings, "campo", valor)` directamente sobre el objeto — nunca reasignes `os.environ` esperando que se relea.
- Valores por defecto razonables para desarrollo local, nunca secretos reales hardcodeados (usa placeholders tipo `CHANGE_ME`).
- Un servicio con modo CLI además de API (`epub2pdf-service`) sigue teniendo un único `settings`, compartido entre `main.py` y `cli.py` — las rutas de entrada/salida son *defaults* en `Settings` para el CLI, pero llegan como parámetro explícito en el cuerpo de la petición para la API (no se leen de `settings` en ese camino).

---

## 6. Versión del paquete: una sola fuente de verdad

`__init__.py`:
```python
from importlib.metadata import version
__version__ = version("<nombre-del-proyecto>")  # el de [project].name en pyproject.toml
```

Nunca dupliques la versión escribiéndola también a mano en `main.py` o en el endpoint de salud — `importlib.metadata.version()` la lee de los metadatos del paquete instalado, así que siempre coincide con `pyproject.toml`. Subir de versión es siempre `make bump-version` (ver sección 8), nunca editar el número a mano.

`GET /health` **siempre** devuelve esta forma exacta, en todos los servicios:
```json
{"status": "ok", "version": "0.1.0", "service": "<nombre-service>"}
```

---

## 7. Logging: `loguru` + `InterceptHandler`, salida JSON estructurada

Todos los contenedores del clúster mandan su stdout/stderr a Loki vía Promtail (`docs/04-servicios-comunes.md`, sección promtail) — el logging de cada servicio está pensado para ese destino, no para que una persona lo lea en una terminal.

```python
# logging_setup.py (o core/logging.py — el nombre exacto no importa, la forma sí)
from __future__ import annotations

import logging
import sys
from types import FrameType
from typing import cast

from loguru import logger

from <paquete>.config import Settings


class InterceptHandler(logging.Handler):
    """Handler de `logging` estándar que reenvía los registros a Loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        level: int | str
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = cast(FrameType, frame.f_back)
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


# uvicorn/fastapi/asyncio siempre; añade aquí cualquier librería de terceros
# propia del servicio que use logging estándar (playwright/crawl4ai,
# faster_whisper/ctranslate2, markitdown...).
_THIRD_PARTY_LOGGERS: tuple[str, ...] = ("uvicorn", "uvicorn.access", "uvicorn.error", "fastapi", "asyncio")


def setup_logging(settings: Settings) -> None:
    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.log_level,
        serialize=settings.log_format == "json",
        enqueue=True,
    )

    # Redirige el logging estándar (uvicorn incluido) a Loguru.
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for logger_name in _THIRD_PARTY_LOGGERS:
        std_logger = logging.getLogger(logger_name)
        std_logger.handlers = [InterceptHandler()]
        std_logger.propagate = False

    # "uvicorn.access" (una línea por petición HTTP, incluidos los
    # healthchecks de Docker cada pocos segundos) solo aporta valor en modo
    # depuración — a nivel normal queda por debajo de INFO para no inundar
    # Loki de líneas "GET /health 200" sin información útil.
    logging.getLogger("uvicorn.access").setLevel(
        logging.DEBUG if settings.log_level.upper() == "DEBUG" else logging.WARNING
    )
```

En `config.py` (sección 5), dos campos nuevos junto al resto de `Settings`:

```python
log_level: str = "INFO"
log_format: Literal["text", "json"] = "text"   # ver docs/04-servicios-comunes.md, sección promtail
```

- El **valor por defecto en código es `"text"`** (cómodo para desarrollo local sin filtrar por Loki) — el `docker-compose.yml` de cada nodo lo sobreescribe explícitamente a `json` en producción (`<PREFIJO>_LOG_FORMAT: ${<PREFIJO>_LOG_FORMAT:-json}`), igual que ya se hacía con `LOG_LEVEL`.
- Se llama **una vez**, al arrancar (`main.py` a nivel de módulo para la API; al inicio de `main()` en `cli.py` si el servicio tiene modo CLI — son procesos/entrypoints distintos, cada uno configura su propio sink).
- `enqueue=True` siempre — hace el logging seguro entre hilos/procesos (relevante porque FastAPI/uvicorn y `run_in_executor` pueden loggear desde hilos distintos).
- Salida a `stdout`, nunca a fichero dentro del contenedor — el contenedor es efímero, el destino real de los logs es `docker logs`/Loki, no un fichero local.
- El `InterceptHandler` es necesario porque uvicorn/fastapi/las librerías de terceros usan el módulo `logging` estándar, no loguru directamente — sin interceptarlo, esos logs (incluidos los de acceso HTTP) saldrían con un formato de texto plano distinto al del resto de la aplicación, JSON o no.
- Si un servicio necesita un canal de logging **separado** del general (p. ej. auditoría de seguridad exportada por OTLP en `apikey-service`, distinta del logging general a stdout), usa el módulo estándar `logging` con un logger nombrado aparte y `propagate = False`, integrado con `opentelemetry.sdk._logs.LoggingHandler` — no mezcles ambos logging (loguru + `logging`) para el mismo propósito. Ese canal es aparte de todo lo anterior y no lo sustituye.

---

## 8. `Makefile`: comandos estándar, siempre los mismos nombres

Todo servicio tiene estos targets, con el mismo nombre en todos (aunque el contenido varíe):

| Target | Qué hace |
|---|---|
| `build` | Construye la imagen (multi-arch si aplica, ver 8.1), la etiqueta con la versión de `pyproject.toml` + `latest`, la sube al registry |
| `run` | Arranca un contenedor de pruebas en local, con `.env` |
| `test` | `uv run pytest` |
| `test-cov` | Igual que `test`, además genera `coverage.xml` (lo consume SonarQube) |
| `test-health` | `curl` al `/health` de un contenedor ya arrancado |
| `test-<algo>` | Uno por servicio, prueba manual del endpoint principal (`test-convert`, `test-transcribe`...) |
| `lint` | `uv run ruff check .` |
| `format` | `uv run ruff format .` |
| `typecheck` | `uv run mypy src/` |
| `sonar` | Análisis SonarQube vía `pysonar` |
| `sonar-check` | `test-cov` + `sonar` en un solo paso |
| `bump-version` | Sube la versión en `pyproject.toml` (`PART=patch\|minor\|major`, patch por defecto) |
| `clean` | Borra las imágenes Docker locales |

Detalles que **no** son arbitrarios:

- **`-include .env` sin `export` global.** Un `export` a secas inyectaría las variables del `.env` real (contraseñas, DSN de producción...) en el entorno de `make test`, pisando los valores por defecto que los propios tests dan por hecho (`test_config.py` comprueba `Settings()` sin nada more inyectado). Cada target que sí necesita algo de `.env` (`build`, `sonar`) lo pasa **explícito** en su propio comando (`SONAR_TOKEN=$(SONAR_TOKEN) uv run pysonar`), nunca por `export` global.
- **`REQUESTS_CA_BUNDLE` en `sonar`/`sonar-check`.** `pysonar` usa la librería `requests`, que valida TLS contra el paquete `certifi`, no contra el almacén de certificados del sistema operativo. Sin fijar esta variable a la CA interna del clúster (`/etc/ssl/certs/ca-certificates.crt` tras instalarla — `docs/15-ca-interna.md`), `https://sonarqube.home.arpa` falla con `CERTIFICATE_VERIFY_FAILED` aunque `curl` lo acepte sin avisar.
- **Multi-arch por defecto (`PLATFORMS ?= linux/amd64,linux/arm64`)** vía `docker buildx build --platform ... --push` — nunca `docker build` clásico para lo que se sube al registry, porque no genera manifiestos multi-plataforma. Se usa así porque varios nodos destino son Raspberry Pi (arm64) y el build normalmente se hace desde una máquina x86. Requiere, una vez por máquina de build: `docker run --privileged --rm tonistiigi/binfmt --install all` y `docker buildx create --driver docker-container --use`.
- **Excepción amd64-only**, documentada con un comentario explícito en el propio target `build`: servicios que necesitan GPU/CUDA (`whisper-service`) solo se despliegan en `ryzen` (x86 con GPU NVIDIA) — no tiene sentido, y probablemente ni sería posible, generar una variante arm64.
- **`uvx --from=toml-cli toml get ...` para leer la versión**, en vez de parsear `pyproject.toml` a mano — evita añadir `toml`/`tomli` como dependencia del propio proyecto solo para esto.
- Antes de `sonar`, limpiar `__pycache__` (y cualquier fichero de test tipo SQLite) a mano: sin repositorio git, el sensor de `pysonar` no filtra bien estos artefactos y los analiza como si fueran código, generando ruido de "Invalid character... UTF-8".

---

## 9. Registry Docker privado y publicación de imágenes

- Ningún `docker-compose.yml` de ningún nodo del clúster construye estas imágenes (`build:`) — todos usan `image: registry.home.arpa/<nombre>-service:latest` + `docker compose pull`. El build/push vive **solo** en el `Makefile` del propio servicio, ejecutado desde donde se desarrolla el código.
- Login previo (`docker login registry.home.arpa`, credenciales en Vaultwarden — "Docker Registry (registry.home.arpa)") requerido tanto para hacer `push` (build local) como `pull` (cada nodo consumidor) — detalle completo, incluida la instalación de la CA interna dentro del propio contenedor del builder de `buildx` (no la hereda del host), en `docs/05-instalacion-retaco.md` sección 5.3.
- El `Makefile` falla explícitamente (`test -n "$(REGISTRY_USER)" || ...`) si `REGISTRY_USER`/`REGISTRY_PASSWORD` no están en `.env`, en vez de intentar construir sin credenciales y fallar más tarde con un error de Docker menos claro.

---

## 10. Calidad de código: `ruff` + `mypy`

`pyproject.toml`, siempre estos bloques (ajustando `target-version`/`python_version` a la versión real del servicio):

```toml
[tool.ruff]
line-length = 100
target-version = "py312"   # o py311, la que use el servicio
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "C4"]
ignore = ["B008"]  # Depends()/File()/Form() de FastAPI — ver sección 4.4

[tool.mypy]
python_version = "3.12"
mypy_path = "src"
explicit_package_bases = true
disallow_untyped_defs = true
disallow_incomplete_defs = true
no_implicit_optional = true
warn_redundant_casts = true
warn_unused_ignores = true
warn_return_any = true
ignore_missing_imports = true
```

- `select` incluye `UP` (pyupgrade) — respeta sus avisos, no los silencies sin motivo. Ejemplo real: `class X(str, Enum)` lo marca como `UP042`, sugiriendo `enum.StrEnum` (disponible desde Python 3.11) — es el cambio correcto, no un falso positivo.
- `disallow_untyped_defs`/`disallow_incomplete_defs` — todo el código nuevo lleva *type hints* completos, sin excepciones "porque es un script pequeño".
- Objetivo real, no aspiracional: `uv run ruff check .` y `uv run mypy src/` deben terminar **sin ningún aviso** antes de dar un servicio por listo, no solo "sin errores que rompan el build".

---

## 11. Tests

- `pytest` + `pytest-cov`, cobertura mínima **80%** exigida en el propio `pyproject.toml` (`addopts = "--cov=<paquete> --cov-report=term-missing --cov-fail-under=80"`) — no en el CI aparte, para que falle igual en local que en cualquier otro sitio.
- `tests/conftest.py`:
  - Fixtures compartidas (`client` para `TestClient(app)`, builders de datos de prueba tipo `build_epub`/`valid_epub_path`).
  - Si algo del servicio lee variables de entorno **al importar el módulo** (un motor de base de datos construido a nivel de módulo, por ejemplo), esas variables se fijan con `os.environ.setdefault(...)` en la **cabecera** de `conftest.py`, antes de cualquier `import` del propio paquete — pytest carga `conftest.py` antes de recolectar los tests, así que es el único sitio donde da tiempo a hacerlo. `setdefault` (no asignación directa) para no pisar un valor que ya viniera fijado desde fuera a propósito.
- **Mockear en el límite de la capa `infrastructure/`**, no más arriba ni más abajo: `@patch("<paquete>.infrastructure.<modulo>.subprocess.run", ...)` (o la llamada externa que corresponda), nunca mockear `services/` por dentro. Así el test sigue ejercitando toda la lógica de negocio real, y solo sustituye la parte que de verdad no se puede/quiere ejecutar en CI (un binario externo, una llamada de red).
- Para mutar `settings` en un test: `monkeypatch.setattr(settings, "campo", valor)` (ver sección 5) — nunca reasignar variables de entorno esperando que un singleton ya construido las relea.
- Para sustituir un colaborador instanciado a nivel de módulo en `dependencies.py` (p. ej. el conversor real) en un test de la API: `monkeypatch.setattr(dependencies_module._converter, "convert", <fake>)` — parcheando el objeto módulo, no con `app.dependency_overrides` (mismo patrón en todos los servicios, mantenerlo por consistencia aunque `dependency_overrides` sea "más FastAPI-idiomático").
- Nombre de fichero de test = nombre del módulo que prueba, con prefijo `test_` (`services/conversion_service.py` → `tests/test_conversion_service.py`). Los tests de la API HTTP van en `tests/test_controllers.py`, no repartidos por controller.

---

## 12. `README.md`: estructura fija

En este orden, siempre:

1. **Título + una línea** de qué hace el servicio.
2. **Endpoints** — cada uno con su forma de petición/respuesta en JSON real (no un esquema abstracto).
3. **Uso rápido** — un par de `curl` copiables.
4. (Si aplica) **Modo alternativo** (CLI, batch...) con su propio ejemplo.
5. **Desarrollo local** — los `make` más usados (`build`, `run`, `test-health`, `test-<algo>`).
6. **Estructura del proyecto** — árbol de `src/<paquete>/` con un comentario de una línea por fichero explicando su capa/responsabilidad, más un párrafo corto reafirmando la regla de dependencia de la sección 4.1 aplicada a ese servicio en concreto.
7. **Tests, cobertura, lint y análisis estático** — comandos + una nota de qué se mockea y por qué no hace falta tener la dependencia externa instalada para testear.
8. **Análisis SonarQube** — el comando y qué variables de `.env` necesita.
9. Notas específicas del servicio al final (limitaciones conocidas, decisiones de diseño no obvias) — no al principio, para no tapar lo esencial.

---

## 13. `.env.example`, `.gitignore`, `sonar-project.properties`

Los tres, calcados entre servicios salvo por el nombre/prefijo:

- **`.env.example`**: comentario de cabecera explicando que el `Makefile` lo carga sin `export` global (referencia cruzada a la sección 8), agrupado por qué `make` target usa cada bloque de variables, placeholders `CHANGE_ME_<algo>` nunca valores reales, referencia a dónde están las credenciales reales (Vaultwarden, con el nombre exacto de la entrada).
- **`.gitignore`**: `.venv/`, `__pycache__/`, `*.py[cod]`, `build/`, `dist/`, `*.egg-info/`, `.pytest_cache/`, `.coverage*`, `htmlcov/`, `coverage.xml`, `.mypy_cache/`, `.ruff_cache/`, `.scannerwork/`, `.sonar/`, `.env`, `.DS_Store`, `*.swp`. **`uv.lock` nunca va aquí** (sección 3). Si el servicio genera ficheros de test con datos reales (una base SQLite de test, por ejemplo), su ruta exacta también se excluye explícitamente.
- **`sonar-project.properties`**: `sonar.projectKey`/`sonar.projectName` = nombre del servicio, `sonar.sources=src`, `sonar.tests=tests`, `sonar.python.version` = la del servicio, `sonar.python.coverage.reportPaths=coverage.xml`, `sonar.sourceEncoding=UTF-8`, y un `sonar.exclusions` que cubra los mismos patrones que el `.gitignore` (evita que el análisis se llene de avisos sobre bytecode/artefactos binarios).

---

## 14. `Dockerfile`

Patrón común:

```dockerfile
FROM python:3.12-slim          # o la versión que use el servicio

# (Si hace falta: dependencias de sistema aquí — apt-get, binarios externos)

RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml .
COPY src/ ./src/
RUN uv pip install --system --no-cache .

EXPOSE <puerto>                 # ver registro de puertos, sección 15
ENV <PREFIJO>_HOST=0.0.0.0
ENV <PREFIJO>_PORT=<puerto>

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:<puerto>/health')" || exit 1

CMD ["python3", "-m", "uvicorn", "<paquete>.main:app", "--host", "0.0.0.0", "--port", "<puerto>", "--app-dir", "src"]
```

- `uv pip install --system --no-cache .` (no `uv sync`) dentro del contenedor — no hace falta un entorno virtual aislado dentro de una imagen que ya está aislada por sí misma, y evita el peso extra de `.venv/` en la imagen final.
- El `HEALTHCHECK` usa `urllib.request` de la librería estándar (no `curl`) cuando la imagen no instala `curl` a propósito para mantenerla ligera; si el servicio ya necesita `curl`/herramientas de sistema por otro motivo (como `epub2pdf-service` con Calibre), usar `curl -sf` es igual de válido y más legible.
- `start_period` se sube por encima de 10s si el servicio tarda de verdad en arrancar (whisper-service: 90s, por la carga del modelo en GPU) — documentarlo con un comentario si no es el valor por defecto.

---

## 15. Registro de puertos en uso (evitar colisiones)

| Puerto | Servicio | Nodo |
|---|---|---|
| 8090 | apikey-service | pi-dns |
| 8001 | markitdown-service | pi-utils |
| 8002→8000 | crawl4ai-scraper-service | pi-utils |
| 9800 | whisper-service | ryzen |
| 8003 | epub2pdf-service | retaco |
| 8004 | pdf2chunks-service | retaco |
| 8005→8000 | open-terminal-mcp | retaco |

**Nunca uses el `8000`** como puerto final de un servicio nuevo — es el puerto por defecto de un número enorme de herramientas FastAPI/dev, y colisiona con facilidad en local. Antes de fijar un puerto para un servicio nuevo, revisa esta tabla y `docs/17-firewall-acceso-directo.md` (que documenta qué puertos están además gestionados por el cortafuegos), y añade la fila correspondiente aquí.

---

## 16. Checklist para crear un microservicio nuevo desde cero

1. `services/<nombre>-service/`, con `src/<nombre>_service/` dentro (sección 2).
2. `pyproject.toml` con el bloque completo de la sección 3 + 10 (uv/hatchling + ruff/mypy), `requires-python` fijado.
3. `domain/` solo si hace falta compartir un resultado entre más de un punto de entrada; si no, empieza sin él y añádelo cuando de verdad aparezca esa necesidad.
4. `infrastructure/` con un envoltorio por cada dependencia externa real (binario, librería de terceros, cliente HTTP a otro servicio).
5. `services/` con la orquestación — recibe sus colaboradores por constructor, nunca los instancia dentro salvo que sean values puros sin estado.
6. `controllers/` + `schemas.py` + `dependencies.py` + `main.py`, siguiendo el patrón de la sección 4.
7. `config.py` con `Settings(BaseSettings)`, prefijo = nombre del servicio en mayúsculas (sección 5).
8. `logging_setup.py` con loguru (sección 7).
9. Puerto nuevo: revisar la tabla de la sección 15, elegir uno libre, añadirlo a la tabla.
10. `tests/` — `conftest.py` con las fixtures compartidas, un fichero de test por módulo de `services/`+`infrastructure/`, `tests/test_controllers.py` para la API. Cobertura ≥ 80% antes de dar nada por terminado.
11. `Makefile` calcado del de otro servicio existente, cambiando solo `SERVICE_NAME`/`PORT`/el target `test-<algo>` específico.
12. `Dockerfile` siguiendo la sección 14, decidiendo multi-arch vs amd64-only según si el servicio necesita GPU.
13. `.env.example`, `.gitignore`, `sonar-project.properties` (sección 13) — cópialos de otro servicio y ajusta solo lo específico.
14. `README.md` con la estructura fija de la sección 12.
15. Verificación final antes de considerarlo terminado: `uv sync && uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run mypy src/` — los cuatro sin ningún error ni aviso.
16. Wiring en el clúster (fuera del propio servicio, si aplica): entrada en `docker-compose.yml` del nodo destino con `image: registry.home.arpa/<nombre>-service:latest` (nunca `build:`), registro DNS en `shared/dns/dns-records.md`, protección con `apikey-service` si el servicio no tiene autenticación propia, y actualización del documento de instalación del nodo correspondiente en `docs/`.
