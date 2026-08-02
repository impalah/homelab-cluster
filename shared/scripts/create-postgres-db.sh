#!/usr/bin/env bash
# =============================================================================
# create-postgres-db.sh
# Crea una base de datos NUEVA con su propio usuario, aislada del resto
# (sin acceso a otras bases de datos del mismo servidor PostgreSQL, ni al
# revés) — pensado para añadir proyectos propios a postgres-main (retaco)
# sin tocar contenedores, volúmenes ni el resto de bases de datos.
#
# Uso:
#   bash create-postgres-db.sh <contenedor> <usuario-admin> <nueva-db> <nuevo-usuario> [password]
#
# Ejemplo:
#   bash create-postgres-db.sh postgres-main dbadmin lam lmsadmin
#   (sin password: se genera uno aleatorio y se muestra al final)
#
# Requiere: el contenedor <contenedor> corriendo y accesible con docker exec.
# =============================================================================
set -euo pipefail

CONTAINER="${1:?Uso: create-postgres-db.sh <contenedor> <usuario-admin> <nueva-db> <nuevo-usuario> [password]}"
ADMIN_USER="${2:?Falta el usuario administrador (superusuario)}"
DB_NAME="${3:?Falta el nombre de la nueva base de datos}"
DB_USER="${4:?Falta el nombre del nuevo usuario}"
DB_PASSWORD="${5:-$(openssl rand -base64 18)}"

echo "[INFO] Creando base de datos '${DB_NAME}' con usuario '${DB_USER}' en '${CONTAINER}'..."

docker exec -i "${CONTAINER}" psql -v ON_ERROR_STOP=1 -U "${ADMIN_USER}" -d postgres <<-EOSQL
    CREATE ROLE "${DB_USER}" WITH LOGIN PASSWORD '${DB_PASSWORD}';
    CREATE DATABASE "${DB_NAME}" OWNER "${DB_USER}";
    REVOKE ALL ON DATABASE "${DB_NAME}" FROM PUBLIC;
    GRANT ALL PRIVILEGES ON DATABASE "${DB_NAME}" TO "${DB_USER}";
EOSQL

echo ""
echo "[OK] Base de datos '${DB_NAME}' creada — aislada, sin acceso a ninguna otra BD del servidor."
echo "     Usuario:    ${DB_USER}"
echo "     Contraseña: ${DB_PASSWORD}"
echo "     DSN (desde otro contenedor en la misma red Docker):"
echo "       postgresql://${DB_USER}:${DB_PASSWORD}@${CONTAINER}:5432/${DB_NAME}"
echo "     DSN (cross-host, desde otro nodo del clúster — usar la IP del nodo, no el nombre del contenedor):"
echo "       postgresql://${DB_USER}:${DB_PASSWORD}@<ip-del-nodo>:5432/${DB_NAME}"
echo ""
echo "     Guarda la contraseña ahora — no se vuelve a mostrar."
