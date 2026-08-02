#!/usr/bin/env bash
# =============================================================================
# backup-postgres.sh
# Realiza un volcado pg_dump de una instancia PostgreSQL en Docker.
# Uso: bash backup-postgres.sh <nodo> <contenedor> <base-de-datos>
# Ejemplo:
#   bash backup-postgres.sh retaco postgres-main n8n
#   bash backup-postgres.sh retaco postgres-main sonarqube
# =============================================================================
set -euo pipefail

NODE="${1:-}"
CONTAINER="${2:-}"
DATABASE="${3:-}"

if [ -z "${NODE}" ] || [ -z "${CONTAINER}" ] || [ -z "${DATABASE}" ]; then
  echo "[ERROR] Uso: backup-postgres.sh <nodo> <contenedor> <base-de-datos>"
  exit 1
fi

BACKUP_DIR="/srv/homelab/backups/${NODE}"
DATE=$(date +%Y%m%d-%H%M)
BACKUP_FILE="${BACKUP_DIR}/${CONTAINER}_${DATABASE}_${DATE}.sql.gz"

# Determinar usuario postgres según el contenedor
case "${CONTAINER}" in
  postgres-main)
    # postgres-main es multi-tenant (n8n, sonarqube, y cualquier otra creada
    # con create-postgres-db.sh) — cada base tiene su propio rol aislado sin
    # acceso a las demás, así que un rol de aplicación concreto no podría
    # volcar ninguna base que no sea la suya. Se usa el superusuario admin
    # del servidor (bypasea todos los permisos), leído del .env del nodo.
    PG_USER=$(grep -m1 '^POSTGRES_ADMIN_USER=' "/srv/homelab/${NODE}/.env" 2>/dev/null | cut -d= -f2-)
    PG_USER="${PG_USER:-dbadmin}"
    ;;
  sonarqube-db)
    PG_USER="sonarqube"
    ;;
  *)
    PG_USER="postgres"
    ;;
esac

mkdir -p "${BACKUP_DIR}"

echo "[INFO] Iniciando backup de '${DATABASE}' en contenedor '${CONTAINER}'..."
echo "[INFO] Destino: ${BACKUP_FILE}"

docker exec "${CONTAINER}" \
  pg_dump -U "${PG_USER}" -d "${DATABASE}" --no-owner --no-acl \
  | gzip > "${BACKUP_FILE}"

SIZE=$(du -sh "${BACKUP_FILE}" | cut -f1)
echo "[OK] Backup completado: ${BACKUP_FILE} (${SIZE})"

# Listar los últimos 5 backups de este contenedor
echo ""
echo "[INFO] Backups recientes de ${CONTAINER}:"
ls -lh "${BACKUP_DIR}/${CONTAINER}_${DATABASE}_"*.sql.gz 2>/dev/null \
  | tail -5 \
  || echo "(no hay backups previos)"
