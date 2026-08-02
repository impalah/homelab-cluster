#!/usr/bin/env bash
# =============================================================================
# update-stack.sh
# Actualiza las imágenes Docker y recrea los contenedores de un nodo.
# Uso: bash update-stack.sh <nodo> [fichero-compose]
# Nodos válidos: ryzen | retaco | pi-dns | pi-obs | pi-sonar | pi-utils
#
# [fichero-compose] es opcional, por defecto "docker-compose.yml". Solo hace
# falta indicarlo en ryzen, que tiene dos stacks independientes:
#   bash update-stack.sh ryzen                                # stack de IA
#   bash update-stack.sh ryzen docker-compose.observability.yml  # observabilidad
# =============================================================================
set -euo pipefail

NODE="${1:-}"
COMPOSE_FILENAME="${2:-docker-compose.yml}"

if [ -z "${NODE}" ]; then
  echo "[ERROR] Debes indicar el nodo. Uso: update-stack.sh <nodo> [fichero-compose]"
  exit 1
fi

COMPOSE_FILE="/srv/homelab/${NODE}/${COMPOSE_FILENAME}"

if [ ! -f "${COMPOSE_FILE}" ]; then
  echo "[ERROR] No se encuentra: ${COMPOSE_FILE}"
  exit 1
fi

echo "[INFO] Actualizando stack del nodo: ${NODE}"
echo "[INFO] Compose file: ${COMPOSE_FILE}"

cd "/srv/homelab/${NODE}"

echo ""
echo "[STEP 1/3] Descargando imágenes actualizadas..."
docker compose -f "${COMPOSE_FILENAME}" pull

echo ""
echo "[STEP 2/3] Recreando contenedores..."
docker compose -f "${COMPOSE_FILENAME}" up -d --remove-orphans

echo ""
echo "[STEP 3/3] Limpiando imágenes huérfanas..."
docker image prune -f

echo ""
echo "[OK] Stack '${NODE}' (${COMPOSE_FILENAME}) actualizado."
docker compose -f "${COMPOSE_FILENAME}" ps
