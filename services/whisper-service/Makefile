# Carga .env si existe (copiar antes desde .env.example) como variables de
# Make ($(SONAR_TOKEN), etc.) — a propósito SIN "export" global: un "export"
# a secas inyectaría también WHISPER_MODEL/WHISPER_DEVICE en el entorno de
# "make test", pisando los defaults que exercitan los propios tests
# (test_config.py comprueba los valores por defecto de Settings()). Cada
# target que necesite algo de .env lo pasa explícito en su propio comando
# (ver "sonar"/"build" más abajo), nunca por export global — mismo patrón que
# apikey-service/markitdown-service.
-include .env

# Bundle de certificados que valida la CA interna del clúster (ver "sonar" más
# abajo) — se puede sobreescribir desde .env si hace falta, pero funciona sin
# tocar nada en cualquier Debian/Ubuntu con la CA instalada (docs/15-ca-interna.md).
REQUESTS_CA_BUNDLE ?= /etc/ssl/certs/ca-certificates.crt

# Parte a subir con "make bump-version" — patch por defecto, sobreescribible:
# make bump-version PART=minor
PART ?= patch

.PHONY: build run test test-cov test-health test-transcribe lint format typecheck sonar sonar-check bump-version clean

SERVICE_NAME := whisper-service
IMAGE_NAME   := homelab/$(SERVICE_NAME)
IMAGE_TAG    := latest
PORT         := 9800

# --- Registry privado del clúster (docs/05-instalacion-retaco.md, sección 5.3) ---
# REGISTRY_USER/REGISTRY_PASSWORD deben venir de .env (copiar desde
# .env.example) — nunca hardcodeados aquí. "?=" permite sobreescribirlos
# desde fuera si hiciera falta, pero el valor real vive solo en .env.
REGISTRY_URI       ?= registry.home.arpa
REGISTRY_USER      ?=
REGISTRY_PASSWORD  ?=
REGISTRY_IMAGE     := $(REGISTRY_URI)/$(SERVICE_NAME)

## Construir imagen, etiquetarla (versión de pyproject.toml + "latest") y subirla al registry
# Imagen pesada (base nvidia/cuda, varios GB) — el push puede tardar bastante
# en la primera subida; nginx en pi-dns ya tiene timeouts largos para esto
# (docs/05-instalacion-retaco.md, sección 5.3).
# Solo amd64 a propósito, sin buildx multi-plataforma (a diferencia de
# apikey-service/markitdown-service): requiere GPU NVIDIA/CUDA, que las
# Raspberry Pi del clúster no tienen — este servicio solo corre en ryzen (x86).
build:
	@test -n "$(REGISTRY_USER)" || (echo "ERROR: define REGISTRY_USER en .env (copiar desde .env.example)"; exit 1)
	@test -n "$(REGISTRY_PASSWORD)" || (echo "ERROR: define REGISTRY_PASSWORD en .env (copiar desde .env.example)"; exit 1)
	@VERSION=$$(uvx --from=toml-cli toml get --toml-path=pyproject.toml project.version) && \
	echo "[INFO] Construyendo $(SERVICE_NAME) versión $$VERSION" && \
	echo "$(REGISTRY_PASSWORD)" | docker login $(REGISTRY_URI) -u "$(REGISTRY_USER)" --password-stdin && \
	docker build \
		-t $(IMAGE_NAME):$(IMAGE_TAG) \
		-t $(REGISTRY_IMAGE):$$VERSION \
		-t $(REGISTRY_IMAGE):latest \
		. && \
	docker push $(REGISTRY_IMAGE):$$VERSION && \
	docker push $(REGISTRY_IMAGE):latest && \
	echo "[OK] Subido: $(REGISTRY_IMAGE):$$VERSION y $(REGISTRY_IMAGE):latest"

## Sube la versión en pyproject.toml (patch por defecto — make bump-version PART=minor|major)
bump-version:
	@v=$$(uvx --from=toml-cli toml get --toml-path=pyproject.toml project.version) && \
	echo "[INFO] Versión actual: $$v" && \
	uvx --from bump2version bumpversion --allow-dirty --current-version "$$v" $(PART) pyproject.toml && \
	echo "[OK] Versión subida ($(PART))"

## Arrancar contenedor de pruebas local (requiere GPU NVIDIA — usa --gpus all)
run:
	docker run --rm -it \
		--gpus all \
		-p $(PORT):$(PORT) \
		-e WHISPER_MODEL=medium \
		$(IMAGE_NAME):$(IMAGE_TAG)

## Tests unitarios (pytest + cobertura, obligatorio >80% — ver pyproject.toml)
# No cargan WhisperModel de verdad (ni CUDA, ni descarga de pesos): los tests
# de /transcribe monkeypatchean src.main._model con un modelo falso.
test:
	uv run pytest

## Igual que test, pero además genera coverage.xml (formato Cobertura, lo consume SonarQube)
test-cov:
	uv run pytest --cov-report=xml

## Test de healthcheck contra un contenedor ya arrancado (make run, en otra terminal)
test-health:
	curl -sf http://localhost:$(PORT)/health | python3 -m json.tool

## Test de transcripción con un audio de muestra
test-transcribe:
	@if [ -z "$(FILE)" ]; then echo "Uso: make test-transcribe FILE=/path/to/audio.mp3"; exit 1; fi
	curl -X POST http://localhost:$(PORT)/transcribe \
		-F "file=@$(FILE)" \
		-H "Accept: application/json" | python3 -m json.tool

## Revisar estilo/errores con ruff
lint:
	uv run ruff check .

## Formatear código con ruff
format:
	uv run ruff format .

## Revisar tipos con mypy
typecheck:
	uv run mypy src/

## Analizar con SonarQube (pysonar) — requiere SONAR_HOST_URL y SONAR_TOKEN en .env
# Sin repo git, el sensor de texto/secretos de pysonar no respeta del todo
# "sonar.exclusions" (usa detección de "ficheros sucios" vía git, y sin git
# cae a escanear de más) — se limpia antes __pycache__ a mano para no llenar
# el análisis de avisos de "Invalid character... UTF-8" sobre bytecode que no
# es código real.
# REQUESTS_CA_BUNDLE: pysonar usa "requests", que valida TLS contra el bundle
# de certifi, no contra el almacén de certificados del sistema — sin esto,
# "https://sonarqube.home.arpa" falla con CERTIFICATE_VERIFY_FAILED aunque
# curl lo acepte sin problema.
sonar:
	@test -n "$(SONAR_TOKEN)" || (echo "ERROR: define SONAR_TOKEN en .env (copiar desde .env.example)"; exit 1)
	@test -n "$(SONAR_HOST_URL)" || (echo "ERROR: define SONAR_HOST_URL en .env (copiar desde .env.example)"; exit 1)
	find . -path ./.venv -prune -o -iname "__pycache__" -print0 2>/dev/null | xargs -0 rm -rf
	SONAR_HOST_URL=$(SONAR_HOST_URL) SONAR_TOKEN=$(SONAR_TOKEN) REQUESTS_CA_BUNDLE=$(REQUESTS_CA_BUNDLE) uv run pysonar

## Cobertura + análisis SonarQube en un solo paso
sonar-check: test-cov sonar

## Limpiar imágenes locales (local + tag :latest del registry — el tag de versión no, cambia en cada build)
clean:
	docker rmi $(IMAGE_NAME):$(IMAGE_TAG) 2>/dev/null || true
	docker rmi $(REGISTRY_IMAGE):latest 2>/dev/null || true
