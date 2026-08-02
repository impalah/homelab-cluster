# Carga .env si existe (copiar antes desde .env.example) como variables de
# Make ($(SONAR_TOKEN), etc.) — a propósito SIN "export" global: un "export"
# a secas inyectaría también APIKEY_DATABASE_URL/APIKEY_ADMIN_TOKEN en el
# entorno de "make test", pisando el aislamiento SQLite que usan los tests
# (conftest.py usa os.environ.setdefault(), que no gana si la variable ya
# viene puesta desde fuera) — pasó de verdad la primera vez que se probó.
# Cada target que necesite algo de .env lo pasa explícito en su propio
# comando (ver "sonar"/"build" más abajo), nunca por export global.
-include .env

# Bundle de certificados que valida la CA interna del clúster (ver "sonar" más
# abajo) — se puede sobreescribir desde .env si hace falta, pero funciona sin
# tocar nada en cualquier Debian/Ubuntu con la CA instalada (docs/15-ca-interna.md).
REQUESTS_CA_BUNDLE ?= /etc/ssl/certs/ca-certificates.crt

# Parte a subir con "make bump-version" — patch por defecto, sobreescribible:
# make bump-version PART=minor
PART ?= patch

.PHONY: build run test test-cov test-health lint format typecheck sonar sonar-check bump-version clean

SERVICE_NAME := apikey-service
IMAGE_NAME   := homelab/$(SERVICE_NAME)
IMAGE_TAG    := latest
PORT         := 8090

# --- Registry privado del clúster (docs/05-instalacion-retaco.md, sección 5.3) ---
# REGISTRY_USER/REGISTRY_PASSWORD deben venir de .env (copiar desde
# .env.example) — nunca hardcodeados aquí. "?=" permite sobreescribirlos
# desde fuera si hiciera falta, pero el valor real vive solo en .env.
REGISTRY_URI       ?= registry.home.arpa
REGISTRY_USER      ?=
REGISTRY_PASSWORD  ?=
REGISTRY_IMAGE     := $(REGISTRY_URI)/$(SERVICE_NAME)

# Este servicio corre en pi-dns (Raspberry Pi, arm64) — la imagen tiene que
# ser multi-arch. amd64 nativo + arm64 emulado con QEMU (docker buildx, no
# el "docker build" clásico, que no soporta multi-plataforma). Requiere
# "docker run --privileged --rm tonistiigi/binfmt --install all" una vez por
# máquina de build, y un builder con driver "docker-container"
# (docker buildx create --driver docker-container --use).
PLATFORMS ?= linux/amd64,linux/arm64

## Construir imagen multi-arch, etiquetarla (versión de pyproject.toml + "latest") y subirla al registry
build:
	@test -n "$(REGISTRY_USER)" || (echo "ERROR: define REGISTRY_USER en .env (copiar desde .env.example)"; exit 1)
	@test -n "$(REGISTRY_PASSWORD)" || (echo "ERROR: define REGISTRY_PASSWORD en .env (copiar desde .env.example)"; exit 1)
	@VERSION=$$(uvx --from=toml-cli toml get --toml-path=pyproject.toml project.version) && \
	echo "[INFO] Construyendo $(SERVICE_NAME) versión $$VERSION para $(PLATFORMS)" && \
	echo "$(REGISTRY_PASSWORD)" | docker login $(REGISTRY_URI) -u "$(REGISTRY_USER)" --password-stdin && \
	docker build -t $(IMAGE_NAME):$(IMAGE_TAG) . && \
	docker buildx build \
		--platform $(PLATFORMS) \
		-t $(REGISTRY_IMAGE):$$VERSION \
		-t $(REGISTRY_IMAGE):latest \
		--push \
		. && \
	echo "[OK] Subido multi-arch ($(PLATFORMS)): $(REGISTRY_IMAGE):$$VERSION y $(REGISTRY_IMAGE):latest"

## Sube la versión en pyproject.toml (patch por defecto — make bump-version PART=minor|major)
bump-version:
	@v=$$(uvx --from=toml-cli toml get --toml-path=pyproject.toml project.version) && \
	echo "[INFO] Versión actual: $$v" && \
	uvx --from bump2version bumpversion --allow-dirty --current-version "$$v" $(PART) pyproject.toml && \
	echo "[OK] Versión subida ($(PART))"

## Arrancar contenedor de pruebas local (lee .env — copiar antes desde .env.example)
run:
	docker run --rm -it \
		-p $(PORT):$(PORT) \
		--env-file .env \
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
# cae a escanear de más) — se limpian antes __pycache__/el sqlite de test a
# mano para no llenar el análisis de avisos de "Invalid character... UTF-8"
# sobre bytecode/binarios que no son código real.
# REQUESTS_CA_BUNDLE: pysonar usa "requests", que valida TLS contra el bundle
# de certifi, no contra el almacén de certificados del sistema — sin esto,
# "https://sonarqube.home.arpa" falla con CERTIFICATE_VERIFY_FAILED aunque
# curl lo acepte sin problema.
sonar:
	@test -n "$(SONAR_TOKEN)" || (echo "ERROR: define SONAR_TOKEN en .env (copiar desde .env.example)"; exit 1)
	@test -n "$(SONAR_HOST_URL)" || (echo "ERROR: define SONAR_HOST_URL en .env (copiar desde .env.example)"; exit 1)
	find . -path ./.venv -prune -o -iname "__pycache__" -print0 2>/dev/null | xargs -0 rm -rf
	rm -f tests/test_apikeys.db
	SONAR_HOST_URL=$(SONAR_HOST_URL) SONAR_TOKEN=$(SONAR_TOKEN) REQUESTS_CA_BUNDLE=$(REQUESTS_CA_BUNDLE) uv run pysonar

## Cobertura + análisis SonarQube en un solo paso
sonar-check: test-cov sonar

## Limpiar imágenes locales (local + tag :latest del registry — el tag de versión no, cambia en cada build)
clean:
	docker rmi $(IMAGE_NAME):$(IMAGE_TAG) 2>/dev/null || true
	docker rmi $(REGISTRY_IMAGE):latest 2>/dev/null || true
