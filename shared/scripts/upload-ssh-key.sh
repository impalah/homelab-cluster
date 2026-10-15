#!/usr/bin/env bash
# =============================================================================
# upload-ssh-key.sh <nodo> [directorio-de-claves]
# Sube (crea o sobrescribe) en Infisical la clave SSH de un nodo: secretos
# PRIVATE_KEY, PUBLIC_KEY y FINGERPRINT en el proyecto `ssh-access`,
# carpeta /<nodo>, entorno prod (docs/38-acceso-ssh-nodos.md, secciones 5.2 y 5.8).
#
# Lee la clave de <dir>/<nodo>-id_ed25519 (por defecto ~/claves-temporales) y la
# pasa al CLI como `@fichero`, sin imprimirla ni dejarla en el
# historial. `secrets set` crea o sobrescribe, así que sirve también para rotar
# sin borrar nada. Requiere `infisical login` ANTES, en una terminal interactiva
# (el login no funciona sin TTY).
#
#   infisical login --domain https://infisical.404labo.net
#   shared/scripts/upload-ssh-key.sh retaco
# =============================================================================
set -euo pipefail

PROJECT_ID="eb2ce068-d5c7-4822-b6bf-ded3c7aad60e"   # proyecto Infisical `ssh-access`
ENV_SLUG="prod"
NODE="${1:-}"
DIR="${2:-$HOME/claves-temporales}"

if [ -z "${NODE}" ]; then
  echo "[ERROR] Uso: upload-ssh-key.sh <nodo> [directorio-de-claves]" >&2; exit 1
fi
PRIV="${DIR}/${NODE}-id_ed25519"
[ -f "${PRIV}" ] && [ -f "${PRIV}.pub" ] || { echo "[ERROR] Faltan ${PRIV}[.pub]" >&2; exit 1; }

FP="$(ssh-keygen -lf "${PRIV}.pub" | cut -d' ' -f2)"
PUB="$(cat "${PRIV}.pub")"
echo "[INFO] Subiendo ${NODE} (${FP}) a /${NODE} en Infisical (${ENV_SLUG})..."

# El CLI lee el valor de PRIVATE_KEY desde un fichero con la sintaxis @<ruta>.
infisical secrets set \
  "PRIVATE_KEY=@${PRIV}" \
  "PUBLIC_KEY=${PUB}" \
  "FINGERPRINT=${FP}" \
  --projectId="${PROJECT_ID}" --env="${ENV_SLUG}" --path="/${NODE}" >/dev/null

echo "[OK] Subida. Comprueba que coincide con el nodo:"
echo "     infisical secrets get FINGERPRINT --plain --projectId=${PROJECT_ID} --env=${ENV_SLUG} --path=/${NODE}"
echo "     (debe ser ${FP})"
