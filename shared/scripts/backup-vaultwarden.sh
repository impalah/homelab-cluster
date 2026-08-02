#!/usr/bin/env bash
# =============================================================================
# backup-vaultwarden.sh
# Backup completo y consistente del directorio de datos de Vaultwarden
# (base de datos SQLite, adjuntos, claves RSA de sesión).
#
# Vaultwarden usa SQLite en modo WAL: copiar solo db.sqlite3 en caliente
# puede dejar fuera transacciones aún no volcadas desde db.sqlite3-wal y
# producir una base de datos corrupta. La imagen tampoco trae el cliente
# `sqlite3` para hacer un backup en caliente (`.backup`) desde dentro. La
# forma segura sin herramientas adicionales es parar el contenedor unos
# segundos durante el empaquetado — para una base de un único hogar, el
# corte es imperceptible, y es la base de datos más sensible del clúster:
# aquí prima la seguridad de los datos sobre el mínimo downtime.
#
# Uso: bash backup-vaultwarden.sh [nodo] [contenedor]
# Por defecto: nodo=pi-utils, contenedor=vaultwarden
# =============================================================================
set -euo pipefail

NODE="${1:-pi-utils}"
CONTAINER="${2:-vaultwarden}"
DATA_DIR="/srv/homelab/${NODE}/vaultwarden/data"
BACKUP_DIR="/srv/homelab/backups/${NODE}"
DATE=$(date +%Y%m%d-%H%M)
BACKUP_FILE="${BACKUP_DIR}/vaultwarden_${DATE}.tar.gz"

mkdir -p "${BACKUP_DIR}"

echo "[INFO] Deteniendo '${CONTAINER}' brevemente para un backup consistente..."
docker stop "${CONTAINER}" >/dev/null

echo "[INFO] Empaquetando ${DATA_DIR}..."
tar -czf "${BACKUP_FILE}" -C "${DATA_DIR}" .

echo "[INFO] Reiniciando '${CONTAINER}'..."
docker start "${CONTAINER}" >/dev/null

SIZE=$(du -sh "${BACKUP_FILE}" | cut -f1)
echo "[OK] Backup completado: ${BACKUP_FILE} (${SIZE})"

echo ""
echo "[INFO] Backups recientes:"
ls -lh "${BACKUP_DIR}"/vaultwarden_*.tar.gz 2>/dev/null | tail -5 || echo "(no hay backups previos)"
