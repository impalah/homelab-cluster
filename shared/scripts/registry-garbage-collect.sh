#!/usr/bin/env bash
# =============================================================================
# registry-garbage-collect.sh
# Recolecta (borra de disco) las capas de imagen Docker en registry.home.arpa
# que ya no están referenciadas por ningún manifest/tag — mejora 8 de
# docs/22-mejoras-futuras.md ("Registry — limpieza y garbage collection").
#
# SOLO EJECUCIÓN MANUAL A PROPÓSITO — no hay cron ni systemd timer que lo
# dispare. Decisión explícita: el propio comando "garbage-collect" de la
# imagen registry:2 exige que el registry no reciba pushes mientras corre
# (o corrompe el índice), así que automatizarlo sin supervisión es
# arriesgado en un clúster con pocos pushes reales — mejor revisar la salida
# de "--dry-run" a mano cada vez. Ver docs/29-registry-mantenimiento.md.
#
# Por defecto corre en modo --dry-run (no borra nada, solo LISTA qué
# borraría) — hace falta pasar "--apply" explícitamente para borrar de
# verdad. Si antes quieres podar tags antiguos (mejor recuperación de
# espacio real), corre primero registry-prune-tags.sh — este script solo
# recolecta blobs ya huérfanos, no decide qué tags conservar.
#
# Uso (en el propio nodo, vía SSH — igual que backup-postgres.sh/
# backup-vaultwarden.sh):
#   bash registry-garbage-collect.sh [nodo] [contenedor] [--dry-run|--apply]
# Por defecto: nodo=retaco, contenedor=registry, modo=--dry-run
#
# Ejemplos:
#   bash registry-garbage-collect.sh                       # dry-run, revisa qué se borraría
#   bash registry-garbage-collect.sh retaco registry --apply   # borra de verdad
# =============================================================================
set -euo pipefail

NODE="${1:-retaco}"
CONTAINER="${2:-registry}"
MODE="${3:---dry-run}"

if [ "${MODE}" != "--dry-run" ] && [ "${MODE}" != "--apply" ]; then
  echo "[ERROR] Uso: registry-garbage-collect.sh [nodo] [contenedor] [--dry-run|--apply]"
  exit 1
fi

COMPOSE_DIR="/srv/homelab/${NODE}"
CONFIG_PATH="/etc/docker/registry/config.yml"

if [ ! -f "${COMPOSE_DIR}/docker-compose.yml" ]; then
  echo "[ERROR] No existe ${COMPOSE_DIR}/docker-compose.yml — ¿nodo correcto?"
  exit 1
fi

cd "${COMPOSE_DIR}"

# El registry queda parado mientras corre el GC (garbage-collect no admite
# pushes concurrentes) — este trap garantiza que se reinicia SIEMPRE al
# salir del script, incluso si el propio garbage-collect falla a medias.
trap 'echo "[INFO] Reiniciando ${CONTAINER}..."; docker compose start "${CONTAINER}" >/dev/null 2>&1 || true' EXIT

echo "[INFO] Deteniendo '${CONTAINER}' (el registry queda inaccesible mientras dure el GC)..."
docker compose stop "${CONTAINER}"

if [ "${MODE}" = "--dry-run" ]; then
  echo "[INFO] DRY-RUN — no se borra nada, solo se lista qué se borraría:"
  echo ""
  docker compose run --rm "${CONTAINER}" bin/registry garbage-collect "${CONFIG_PATH}" --dry-run
  echo ""
  echo "[INFO] Dry-run completado. Para aplicar de verdad:"
  echo "         bash registry-garbage-collect.sh ${NODE} ${CONTAINER} --apply"
else
  echo "[INFO] Ejecutando garbage collection REAL — borra capas huérfanas de disco:"
  echo ""
  docker compose run --rm "${CONTAINER}" bin/registry garbage-collect "${CONFIG_PATH}"
  echo ""
  echo "[OK] Garbage collection completado."
fi
