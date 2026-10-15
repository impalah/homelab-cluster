#!/usr/bin/env bash
# =============================================================================
# ssh-node.sh <nodo> [comando...]
# Conecta por SSH a un nodo como `admin` (docs/38-acceso-ssh-nodos.md, mejora 52).
#
# Carga la clave privada del nodo desde Infisical (proyecto `ssh-access`,
# carpeta /<nodo>, secreto PRIVATE_KEY) directamente en un ssh-agent, EN
# MEMORIA -- nunca la escribe en disco -- y abre la sesión. Sin argumentos de
# comando abre una shell; con comando, lo ejecuta y vuelve.
#
#   ssh-node.sh retaco
#   ssh-node.sh pinchi docker node ls
#
# Requisitos: `infisical` CLI con sesión iniciada (`infisical login --domain https://infisical.404labo.net`, sesión
# personal del operador) y acceso a infisical.404labo.net.
#
# Emergencia (Infisical caído -- vive en retaco): INFISICAL_FALLBACK_DIR=<dir>
# usa la clave local `<dir>/<nodo>-id_ed25519` si existe (p. ej. restaurada
# desde el respaldo de Vaultwarden). Por defecto ~/claves-temporales.
#
# Variables opcionales:
#   SSH_NODE_DRY_RUN=1   solo imprime qué haría (usuario@IP y origen de la clave)
# =============================================================================
set -euo pipefail

PROJECT_ID="eb2ce068-d5c7-4822-b6bf-ded3c7aad60e"   # proyecto Infisical `ssh-access`
INFISICAL_ENV="prod"
USER_NAME="admin"
FALLBACK_DIR="${INFISICAL_FALLBACK_DIR:-$HOME/claves-temporales}"

declare -A NODE_IPS=(
  [pi-dns]="192.168.10.2"
  [pi-utils]="192.168.10.3"
  [pi-obs]="192.168.10.4"
  [pi-sonar]="192.168.10.5"
  [retaco]="192.168.10.7"
  [pinchi]="192.168.10.8"
  [miugarita]="192.168.10.9"
  [ryzen]="192.168.10.10"
)

NODE="${1:-}"
if [ -z "${NODE}" ] || [ -z "${NODE_IPS[$NODE]:-}" ]; then
  echo "[ERROR] Uso: ssh-node.sh <nodo> [comando...]" >&2
  echo "        Nodos: $(printf '%s ' "${!NODE_IPS[@]}" | tr ' ' '\n' | sort | tr '\n' ' ')" >&2
  exit 1
fi
shift
IP="${NODE_IPS[$NODE]}"

# ryzen es normalmente el puesto desde el que se ejecuta esto, pero se trata
# igual que el resto (Ansible/Capataz entran por la misma vía). Si está
# apagado (Wake-on-LAN, docs/19), despertarlo antes con wake-mole.sh.

LOCAL_KEY="${FALLBACK_DIR}/${NODE}-id_ed25519"

if [ "${SSH_NODE_DRY_RUN:-0}" = "1" ]; then
  echo "ssh ${USER_NAME}@${IP}  (nodo ${NODE})"
  echo "clave: Infisical ${PROJECT_ID} env=${INFISICAL_ENV} path=/${NODE} PRIVATE_KEY"
  [ -f "${LOCAL_KEY}" ] && echo "respaldo local presente: ${LOCAL_KEY}" || echo "respaldo local: no"
  exit 0
fi

# ssh-agent propio y efímero de esta ejecución (solo contiene la clave de este
# nodo -- evita "too many authentication failures" con agentes ya cargados --
# y muere al salir, junto con la clave en memoria).
eval "$(ssh-agent -s)" >/dev/null
trap 'ssh-agent -k >/dev/null 2>&1 || true' EXIT

# `timeout` + stdin cerrado: sin sesión, `infisical` pediría un login interactivo
# y se quedaría colgado -- así falla en segundos y se cae al respaldo local.
if timeout 20 infisical secrets get PRIVATE_KEY --plain \
     --projectId="${PROJECT_ID}" --env="${INFISICAL_ENV}" --path="/${NODE}" </dev/null 2>/dev/null \
   | ssh-add - >/dev/null 2>&1; then
  :
elif [ -f "${LOCAL_KEY}" ]; then
  echo "[WARN] Infisical no disponible o sin sesión -- usando la clave local ${LOCAL_KEY}" >&2
  ssh-add "${LOCAL_KEY}" >/dev/null
else
  echo "[ERROR] No se pudo obtener la clave de ${NODE} desde Infisical (¿'infisical login'?) y no hay respaldo local en ${LOCAL_KEY}" >&2
  exit 1
fi

# Sin exec: hace falta que el trap limpie el agente al salir.
ssh -o IdentitiesOnly=no -o StrictHostKeyChecking=accept-new "${USER_NAME}@${IP}" "$@"
