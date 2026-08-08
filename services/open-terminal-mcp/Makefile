# -include .env, sin "export" global — mismo patrón que epub2pdf-service/
# pdf2chunks-service: solo REGISTRY_USER/REGISTRY_PASSWORD hacen falta aquí.
-include .env

.PHONY: build run clean

SERVICE_NAME := open-terminal-mcp
IMAGE_NAME   := homelab/$(SERVICE_NAME)
IMAGE_TAG    := latest
PORT         := 8005

# --- Registry privado del clúster (docs/05-instalacion-retaco.md, sección 5.3) ---
REGISTRY_URI       ?= registry.home.arpa
REGISTRY_USER      ?=
REGISTRY_PASSWORD  ?=
REGISTRY_IMAGE     := $(REGISTRY_URI)/$(SERVICE_NAME)

# No hay pyproject.toml propio que versionar — es una imagen fina que solo
# añade el extra [mcp] sobre ghcr.io/open-webui/open-terminal:slim (ver
# Dockerfile). Un único tag :latest basta; reconstruir sigue el slim oficial.
#
# Solo amd64 (docker build normal, sin buildx) — corre en retaco (x86), mismo
# criterio que epub2pdf-service/pdf2chunks-service/whisper-service.
build:
	@test -n "$(REGISTRY_USER)" || (echo "ERROR: define REGISTRY_USER en .env (copiar desde .env.example)"; exit 1)
	@test -n "$(REGISTRY_PASSWORD)" || (echo "ERROR: define REGISTRY_PASSWORD en .env (copiar desde .env.example)"; exit 1)
	echo "$(REGISTRY_PASSWORD)" | docker login $(REGISTRY_URI) -u "$(REGISTRY_USER)" --password-stdin && \
	docker build -t $(IMAGE_NAME):$(IMAGE_TAG) -t $(REGISTRY_IMAGE):$(IMAGE_TAG) . && \
	docker push $(REGISTRY_IMAGE):$(IMAGE_TAG) && \
	echo "[OK] Subido: $(REGISTRY_IMAGE):$(IMAGE_TAG)"

## Arrancar en local en modo MCP (streamable-http) para probar antes de desplegar
run:
	docker run --rm -it \
		-p $(PORT):8000 \
		-e OPEN_TERMINAL_API_KEY=dev-local-test \
		$(IMAGE_NAME):$(IMAGE_TAG) \
		mcp --transport streamable-http --host 0.0.0.0 --port 8000

clean:
	docker rmi $(IMAGE_NAME):$(IMAGE_TAG) 2>/dev/null || true
	docker rmi $(REGISTRY_IMAGE):$(IMAGE_TAG) 2>/dev/null || true
