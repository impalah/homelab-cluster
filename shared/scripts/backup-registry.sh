#!/usr/bin/env bash
# =============================================================================
# backup-registry.sh
# Backup completo de /srv/homelab/<nodo>/registry/{data,auth} — mejora 8 de
# docs/22-mejoras-futuras.md ("Registry — limpieza y garbage collection").
#
# Mismo patrón que backup-vaultwarden.sh: parar el contenedor unos segundos
# durante el empaquetado, en vez de copiar en caliente (el registry escribe
# blobs mientras recibe pushes; un tar en caliente podría capturar un blob a
# medio escribir). Incluye también "auth/" (el htpasswd) — sin él, restaurar
# solo "data/" deja un registry al que nadie puede hacer login.
#
# ⚠️ Preparado pero SIN EJECUCIÓN todavía (decisión explícita al implementar
# esta mejora) — las imágenes son reconstruibles desde el código fuente
# (services/, o el repo externo de cada imagen), así que no es una pérdida
# de datos irrecuperable si el nodo falla antes de la primera ejecución real.
# Ejecutar cuando se decida incorporar el registry a la rotación de copias
# de seguridad (mejora 1 de docs/22-mejoras-futuras.md).
#
# Uso: bash backup-registry.sh [nodo] [contenedor]
# Por defecto: nodo=retaco, contenedor=registry
# =============================================================================
set -euo pipefail

NODE="${1:-retaco}"
CONTAINER="${2:-registry}"
REGISTRY_DIR="/srv/homelab/${NODE}/registry"
BACKUP_DIR="/srv/homelab/backups/${NODE}"
DATE=$(date +%Y%m%d-%H%M)
BACKUP_FILE="${BACKUP_DIR}/registry_${DATE}.tar.gz"

if [ ! -d "${REGISTRY_DIR}/data" ]; then
  echo "[ERROR] No existe ${REGISTRY_DIR}/data — ¿nodo correcto?"
  exit 1
fi

mkdir -p "${BACKUP_DIR}"

echo "[INFO] Deteniendo '${CONTAINER}' brevemente para un backup consistente..."
docker stop "${CONTAINER}" >/dev/null

echo "[INFO] Empaquetando ${REGISTRY_DIR}/{data,auth}..."
tar -czf "${BACKUP_FILE}" -C "${REGISTRY_DIR}" data auth

echo "[INFO] Reiniciando '${CONTAINER}'..."
docker start "${CONTAINER}" >/dev/null

SIZE=$(du -sh "${BACKUP_FILE}" | cut -f1)
echo "[OK] Backup completado: ${BACKUP_FILE} (${SIZE})"

echo ""
echo "[INFO] Backups recientes:"
ls -lh "${BACKUP_DIR}"/registry_*.tar.gz 2>/dev/null | tail -5 || echo "(no hay backups previos)"
