#!/usr/bin/env bash
# =============================================================================
# restore-postgres.sh
# Restaura un volcado pg_dump en una instancia PostgreSQL en Docker.
# Uso: bash restore-postgres.sh <nodo> <contenedor> <base-de-datos> <archivo.sql.gz>
# Ejemplo:
#   bash restore-postgres.sh retaco postgres-main sonarqube \
#     /srv/homelab/backups/retaco/postgres-main_sonarqube_20260601-0300.sql.gz
# =============================================================================
set -euo pipefail

NODE="${1:-}"
CONTAINER="${2:-}"
DATABASE="${3:-}"
BACKUP_FILE="${4:-}"

if [ -z "${NODE}" ] || [ -z "${CONTAINER}" ] || [ -z "${DATABASE}" ] || [ -z "${BACKUP_FILE}" ]; then
  echo "[ERROR] Uso: restore-postgres.sh <nodo> <contenedor> <base-de-datos> <archivo.sql.gz>"
  exit 1
fi

if [ ! -f "${BACKUP_FILE}" ]; then
  echo "[ERROR] Archivo de backup no encontrado: ${BACKUP_FILE}"
  exit 1
fi

# Determinar usuario postgres según el contenedor (PG_USER: quién ejecuta
# los comandos DROP/CREATE/restore; DB_OWNER: quién debe quedar como
# propietario de la base recreada — no siempre son el mismo rol).
case "${CONTAINER}" in
  postgres-main)
    # postgres-main es multi-tenant (n8n, sonarqube, y cualquier otra creada
    # con create-postgres-db.sh) — se necesita el superusuario admin del
    # servidor para poder DROP/CREATE cualquier base, no el rol aislado de
    # una app concreta. Por convención de este repo, el rol propietario de
    # cada base se llama igual que la propia base (ver create-postgres-db.sh).
    PG_USER=$(grep -m1 '^POSTGRES_ADMIN_USER=' "/srv/homelab/${NODE}/.env" 2>/dev/null | cut -d= -f2-)
    PG_USER="${PG_USER:-dbadmin}"
    DB_OWNER="${DATABASE}"
    ;;
  sonarqube-db)
    PG_USER="sonarqube"
    DB_OWNER="${PG_USER}"
    ;;
  *)
    PG_USER="postgres"
    DB_OWNER="${PG_USER}"
    ;;
esac

echo "[WARN] Esta operación SOBREESCRIBIRÁ la base de datos '${DATABASE}' en '${CONTAINER}'."
echo "[WARN] Asegúrate de haber detenido los servicios que dependen de esta base de datos."
echo ""
read -p "¿Continuar? (escribe 'si' para confirmar): " CONFIRM

if [ "${CONFIRM}" != "si" ]; then
  echo "[INFO] Restauración cancelada."
  exit 0
fi

echo "[INFO] Restaurando '${DATABASE}' desde: ${BACKUP_FILE}"

# Eliminar conexiones activas y recrear la base de datos
docker exec "${CONTAINER}" \
  psql -U "${PG_USER}" -d postgres \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${DATABASE}' AND pid <> pg_backend_pid();"

docker exec "${CONTAINER}" \
  psql -U "${PG_USER}" -d postgres \
  -c "DROP DATABASE IF EXISTS ${DATABASE};"

docker exec "${CONTAINER}" \
  psql -U "${PG_USER}" -d postgres \
  -c "CREATE DATABASE ${DATABASE} OWNER ${DB_OWNER};"

echo "[INFO] Cargando datos..."
gunzip -c "${BACKUP_FILE}" \
  | docker exec -i "${CONTAINER}" \
    psql -U "${PG_USER}" -d "${DATABASE}" --quiet

echo ""
echo "[OK] Base de datos '${DATABASE}' restaurada correctamente en '${CONTAINER}'."
echo "[INFO] Recuerda reiniciar los servicios dependientes."
