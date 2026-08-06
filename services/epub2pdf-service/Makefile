# Carga .env si existe (copiar antes desde .env.example) como variables de
# Make ($(SONAR_TOKEN), etc.) — a propósito SIN "export" global: un "export"
# a secas inyectaría también EPUB2PDF_INPUT_PATH/etc. en el entorno de
# "make test", pisando los defaults que ejercitan los propios tests
# (test_config.py comprueba los valores por defecto de Settings()). Cada
# target que necesite algo de .env lo pasa explícito en su propio comando
# (ver "sonar"/"build" más abajo), nunca por export global — mismo patrón
# que apikey-service/markitdown-service.
-include .env

# Bundle de certificados que valida la CA interna del clúster (ver "sonar" más
# abajo) — se puede sobreescribir desde .env si hace falta, pero funciona sin
# tocar nada en cualquier Debian/Ubuntu con la CA instalada (docs/15-ca-interna.md).
REQUESTS_CA_BUNDLE ?= /etc/ssl/certs/ca-certificates.crt

# Parte a subir con "make bump-version" — patch por defecto, sobreescribible:
# make bump-version PART=minor
PART ?= patch

.PHONY: build run test test-cov test-health test-convert lint format typecheck sonar sonar-check bump-version clean

SERVICE_NAME := epub2pdf-service
IMAGE_NAME   := homelab/$(SERVICE_NAME)
IMAGE_TAG    := latest
PORT         := 8003

# --- Registry privado del clúster (docs/05-instalacion-retaco.md, sección 5.3) ---
# REGISTRY_USER/REGISTRY_PASSWORD deben venir de .env (copiar desde
# .env.example) — nunca hardcodeados aquí. "?=" permite sobreescribirlos
# desde fuera si hiciera falta, pero el valor real vive solo en .env.
REGISTRY_URI       ?= registry.home.arpa
REGISTRY_USER      ?=
REGISTRY_PASSWORD  ?=
REGISTRY_IMAGE     := $(REGISTRY_URI)/$(SERVICE_NAME)

# Solo amd64, con "docker build" normal (no buildx multi-plataforma) —
# mismo criterio que whisper-service: este servicio corre solo en retaco
# (x86, docs/05-instalacion-retaco.md), no hay ningún nodo arm64 que vaya
# a consumir esta imagen, así que generar arm64 sería trabajo sin uso real.
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

## Arrancar contenedor de pruebas local en modo API (puerto 8003)
run:
	docker run --rm -it \
		-p $(PORT):$(PORT) \
		-e EPUB2PDF_LOG_LEVEL=DEBUG \
		$(IMAGE_NAME):$(IMAGE_TAG)

## Tests unitarios (pytest + cobertura, obligatorio >80% — ver pyproject.toml)
test:
	uv run pytest

## Igual que test, pero además genera coverage.xml (formato Cobertura, lo consume SonarQube)
test-cov:
	uv run pytest --cov-report=xml

## Test de healthcheck contra un contenedor ya arrancado (make run, en otra terminal)
test-health:
	curl -sf http://localhost:$(PORT)/health | python3 -m json.tool

## Test de conversión con un EPUB de muestra (contenedor en modo API ya arrancado)
test-convert:
	@if [ -z "$(FILE)" ]; then echo "Uso: make test-convert FILE=/path/al/libro.epub OUT=/path/salida"; exit 1; fi
	@OUT=$${OUT:-/tmp/epub2pdf-test-output} && mkdir -p "$$OUT" && \
	curl -X POST http://localhost:$(PORT)/convert \
		-H "Content-Type: application/json" \
		-d "{\"input_path\": \"$(FILE)\", \"output_path\": \"$$OUT\"}" | python3 -m json.tool

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
