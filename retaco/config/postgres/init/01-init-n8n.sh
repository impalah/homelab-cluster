#!/bin/bash
# =============================================================================
# 01-init-n8n.sh
# Se ejecuta UNA SOLA VEZ, en el primer arranque de postgres-main (cuando
# PGDATA está vacío) — así lo hace el entrypoint oficial de la imagen postgres
# con todo lo que hay en /docker-entrypoint-initdb.d/.
#
# Crea la base de datos y el usuario propios de n8n, aislados: sin acceso a
# ninguna otra base de datos del servidor, ni al revés. $POSTGRES_USER (el
# admin) y las variables N8N_DB_* llegan del entorno del contenedor
# (docker-compose.yml).
# =============================================================================
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname "postgres" <<-EOSQL
    CREATE ROLE "${N8N_DB_USER}" WITH LOGIN PASSWORD '${N8N_DB_PASSWORD}';
    CREATE DATABASE "${N8N_DB_NAME}" OWNER "${N8N_DB_USER}";
    REVOKE ALL ON DATABASE "${N8N_DB_NAME}" FROM PUBLIC;
    GRANT ALL PRIVILEGES ON DATABASE "${N8N_DB_NAME}" TO "${N8N_DB_USER}";
EOSQL

echo "[init] Base de datos '${N8N_DB_NAME}' creada, propietario '${N8N_DB_USER}' (aislada del resto)."
