#!/usr/bin/env bash
# =============================================================================
# registry-garbage-collect.sh
# Recolecta (borra de disco) las capas de imagen Docker en registry.404labo.net
# que ya no están referenciadas por ningún manifest/tag — mejora 8 de
# docs/22-mejoras-futuras.md ("Registry — limpieza y garbage collection").
#
# Reescrito (2026-09-01) para el registry como stack Swarm
# (docker-swarm/stacks/registry/, sin `constraints` de nodo desde el
# 2026-08-31, datos en NFS `/mnt/nfs-data/registry/`) -- la versión
# original usaba `docker compose stop/run/start` contra un
# `docker-compose.yml` por nodo que ya no existe para este servicio
# ("no such service: registry" es exactamente ese fallo). Encontrado real
# al intentar ejecutarlo, no solo al leer el código.
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
# Cómo funciona ahora: `docker service scale registry_registry=0` (deja el
# servicio a 0 réplicas, cluster-wide, sin importar en qué nodo estuviera
# corriendo la tarea), se espera a que la tarea pare de verdad, y se corre
# un contenedor suelto (`docker run --rm`) con la MISMA imagen, montando
# directamente el volumen real de datos (`/mnt/nfs-data/registry/data`),
# para ejecutar `bin/registry garbage-collect` sin que el servicio Swarm
# esté sirviendo tráfico a la vez. Sin necesidad de REGISTRY_HTTP_SECRET
# ni de ningún otro env var del stack -- garbage-collect es una operación
# de mantenimiento offline sobre el storage backend, no sirve HTTP.
#
# Requiere ejecutarse en un nodo con /mnt/nfs-data montado (los 5 managers
# Swarm salvo pi-dns, que está fuera del clúster a propósito) -- no hace
# falta que sea el mismo nodo donde estuviera corriendo la tarea real, el
# volumen es el mismo NFS remoto se mire desde donde se mire.
#
# Uso (en el propio nodo, vía SSH — igual que backup-postgres.sh/
# backup-vaultwarden.sh):
#   bash registry-garbage-collect.sh [--dry-run|--apply]
# Por defecto: --dry-run
#
# Ejemplos:
#   bash registry-garbage-collect.sh              # dry-run, revisa qué se borraría
#   bash registry-garbage-collect.sh --apply      # borra de verdad
# =============================================================================
set -euo pipefail

MODE="${1:---dry-run}"

if [ "${MODE}" != "--dry-run" ] && [ "${MODE}" != "--apply" ]; then
  echo "[ERROR] Uso: registry-garbage-collect.sh [--dry-run|--apply]"
  exit 1
fi

SERVICE="registry_registry"
IMAGE="registry:2.8.3"
DATA_DIR="/mnt/nfs-data/registry/data"
CONFIG_PATH="/etc/docker/registry/config.yml"

if [ ! -d "${DATA_DIR}" ]; then
  echo "[ERROR] No existe ${DATA_DIR} — ¿este nodo tiene montado /mnt/nfs-data? (pi-dns no lo tiene, a propósito)"
  exit 1
fi

if ! docker service inspect "${SERVICE}" >/dev/null 2>&1; then
  echo "[ERROR] No existe el servicio Swarm '${SERVICE}' — ¿el stack 'registry' está desplegado?"
  exit 1
fi

# El registry queda parado mientras corre el GC (garbage-collect no admite
# pushes concurrentes) — este trap garantiza que se reescala a 1 réplica
# SIEMPRE al salir del script, incluso si el propio garbage-collect falla
# a medias.
trap 'echo "[INFO] Reescalando ${SERVICE} a 1 réplica..."; docker service scale "${SERVICE}=1" >/dev/null 2>&1 || true' EXIT

echo "[INFO] Escalando '${SERVICE}' a 0 réplicas (el registry queda inaccesible mientras dure el GC)..."
docker service scale "${SERVICE}=0" >/dev/null

echo "[INFO] Esperando a que la tarea pare de verdad (hasta 60s)..."
RUNNING=1
for _ in $(seq 1 30); do
  RUNNING=$(docker service ps "${SERVICE}" --filter "desired-state=running" --format '{{.CurrentState}}' 2>/dev/null | grep -c '^Running' || true)
  [ "${RUNNING}" -eq 0 ] && break
  sleep 2
done
if [ "${RUNNING}" -ne 0 ]; then
  echo "[ERROR] '${SERVICE}' sigue con una tarea corriendo tras 60s — abortando sin tocar el storage."
  exit 1
fi

if [ "${MODE}" = "--dry-run" ]; then
  echo "[INFO] DRY-RUN — no se borra nada, solo se lista qué se borraría:"
  echo ""
  docker run --rm -v "${DATA_DIR}:/var/lib/registry" "${IMAGE}" bin/registry garbage-collect "${CONFIG_PATH}" --dry-run
  echo ""
  echo "[INFO] Dry-run completado. Para aplicar de verdad:"
  echo "         bash registry-garbage-collect.sh --apply"
else
  echo "[INFO] Ejecutando garbage collection REAL — borra capas huérfanas de disco:"
  echo ""
  docker run --rm -v "${DATA_DIR}:/var/lib/registry" "${IMAGE}" bin/registry garbage-collect "${CONFIG_PATH}"
  echo ""
  echo "[OK] Garbage collection completado."
fi
