#!/usr/bin/env bash
# =============================================================================
# backup-registry.sh
# Backup completo de /mnt/nfs-data/registry/{data,auth} — mejora 8 de
# docs/22-mejoras-futuras.md ("Registry — limpieza y garbage collection").
#
# Reescrito (2026-09-01) para el registry como stack Swarm
# (docker-swarm/stacks/registry/, sin `constraints` de nodo desde el
# 2026-08-31, datos en NFS) -- la versión original asumía un contenedor
# Compose clásico local (`docker stop/start registry`) y una ruta por nodo
# (`/srv/homelab/<nodo>/registry/`) que ya no existen para este servicio,
# mismo motivo que el fix de registry-garbage-collect.sh.
#
# Mismo patrón que backup-vaultwarden.sh: parar el servicio unos segundos
# durante el empaquetado, en vez de copiar en caliente (el registry escribe
# blobs mientras recibe pushes; un tar en caliente podría capturar un blob a
# medio escribir). Incluye también "auth/" (el htpasswd) — sin él, restaurar
# solo "data/" deja un registry al que nadie puede hacer login.
#
# Requiere ejecutarse en un nodo con /mnt/nfs-data montado (los 5 managers
# Swarm salvo pi-dns) -- no hace falta que sea el mismo nodo donde estuviera
# corriendo la tarea real.
#
# BACKUP_DIR ya no es "/srv/homelab/backups/<nodo>" como en
# backup-postgres.sh/backup-vaultwarden.sh -- esos servicios siguen
# pinnados a un `node.hostname` fijo (retaco/pinchi respectivamente), así
# que ese nodo es determinista; registry no tiene constraint desde el
# 2026-08-31 y puede ejecutarse este script desde cualquiera de los 5
# managers, así que un directorio por nodo dispersaría los backups sin
# motivo -- "/srv/homelab/backups/registry/" es fijo, sin importar desde
# dónde se ejecute.
#
# ⚠️ Preparado pero SIN EJECUCIÓN todavía (decisión explícita al implementar
# esta mejora) — las imágenes son reconstruibles desde el código fuente
# (services/, o el repo externo de cada imagen), así que no es una pérdida
# de datos irrecuperable si el nodo falla antes de la primera ejecución real.
# Ejecutar cuando se decida incorporar el registry a la rotación de copias
# de seguridad (mejora 1 de docs/22-mejoras-futuras.md).
#
# Uso: bash backup-registry.sh
# =============================================================================
set -euo pipefail

SERVICE="registry_registry"
REGISTRY_DIR="/mnt/nfs-data/registry"
BACKUP_DIR="/srv/homelab/backups/registry"
DATE=$(date +%Y%m%d-%H%M)
BACKUP_FILE="${BACKUP_DIR}/registry_${DATE}.tar.gz"

if [ ! -d "${REGISTRY_DIR}/data" ]; then
  echo "[ERROR] No existe ${REGISTRY_DIR}/data — ¿este nodo tiene montado /mnt/nfs-data?"
  exit 1
fi

if ! docker service inspect "${SERVICE}" >/dev/null 2>&1; then
  echo "[ERROR] No existe el servicio Swarm '${SERVICE}' — ¿el stack 'registry' está desplegado?"
  exit 1
fi

mkdir -p "${BACKUP_DIR}"

trap 'echo "[INFO] Reescalando ${SERVICE} a 1 réplica..."; docker service scale "${SERVICE}=1" >/dev/null 2>&1 || true' EXIT

echo "[INFO] Escalando '${SERVICE}' a 0 réplicas brevemente para un backup consistente..."
docker service scale "${SERVICE}=0" >/dev/null

echo "[INFO] Esperando a que la tarea pare de verdad (hasta 60s)..."
RUNNING=1
for _ in $(seq 1 30); do
  RUNNING=$(docker service ps "${SERVICE}" --filter "desired-state=running" --format '{{.CurrentState}}' 2>/dev/null | grep -c '^Running' || true)
  [ "${RUNNING}" -eq 0 ] && break
  sleep 2
done
if [ "${RUNNING}" -ne 0 ]; then
  echo "[ERROR] '${SERVICE}' sigue con una tarea corriendo tras 60s — abortando sin empaquetar nada."
  exit 1
fi

echo "[INFO] Empaquetando ${REGISTRY_DIR}/{data,auth}..."
tar -czf "${BACKUP_FILE}" -C "${REGISTRY_DIR}" data auth

SIZE=$(du -sh "${BACKUP_FILE}" | cut -f1)
echo "[OK] Backup completado: ${BACKUP_FILE} (${SIZE})"

echo ""
echo "[INFO] Backups recientes:"
ls -lh "${BACKUP_DIR}"/registry_*.tar.gz 2>/dev/null | tail -5 || echo "(no hay backups previos)"
