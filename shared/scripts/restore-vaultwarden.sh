#!/usr/bin/env bash
# =============================================================================
# restore-vaultwarden.sh
# Restaura un backup de Vaultwarden generado por backup-vaultwarden.sh.
# SOBREESCRIBE por completo los datos actuales (base de datos, adjuntos,
# claves de sesión) — pide confirmación explícita antes de tocar nada.
#
# Uso: bash restore-vaultwarden.sh <fichero.tar.gz> [nodo] [contenedor]
# Por defecto: nodo=pi-utils, contenedor=vaultwarden
# =============================================================================
set -euo pipefail

BACKUP_FILE="${1:?Uso: restore-vaultwarden.sh <fichero.tar.gz> [nodo] [contenedor]}"
NODE="${2:-pi-utils}"
CONTAINER="${3:-vaultwarden}"
DATA_DIR="/srv/homelab/${NODE}/vaultwarden/data"

if [ ! -f "${BACKUP_FILE}" ]; then
  echo "[ERROR] No existe el fichero: ${BACKUP_FILE}"
  exit 1
fi

echo "[AVISO] Esto sobreescribe TODOS los datos actuales de Vaultwarden en '${NODE}'"
echo "        (usuarios, cajas fuertes, adjuntos) con el contenido de:"
echo "        ${BACKUP_FILE}"
read -rp "Escribe RESTAURAR para confirmar: " CONFIRM
if [ "${CONFIRM}" != "RESTAURAR" ]; then
  echo "Cancelado, no se ha tocado nada."
  exit 1
fi

echo "[INFO] Deteniendo '${CONTAINER}'..."
docker stop "${CONTAINER}" >/dev/null

echo "[INFO] Vaciando ${DATA_DIR} y restaurando el backup..."
find "${DATA_DIR}" -mindepth 1 -delete
tar -xzf "${BACKUP_FILE}" -C "${DATA_DIR}"

echo "[INFO] Arrancando '${CONTAINER}'..."
docker start "${CONTAINER}" >/dev/null

echo "[OK] Restauración completada desde ${BACKUP_FILE}."
