#!/usr/bin/env bash
# =============================================================================
# wake-mole.sh
# Envía un magic packet de Wake-on-LAN a "mole" (ryzen, 192.168.10.10) desde
# otro nodo del clúster, para encenderla remotamente cuando está apagada o
# hibernada. Ver el detalle completo (requisitos, cómo se comprobó que la
# NIC/kernel lo soportan, limitaciones de la BIOS) en docs/19-wake-on-lan.md.
#
# Uso: bash wake-mole.sh [nodo]
#   nodo — desde qué nodo del clúster se envía el paquete (por defecto pi-dns2)
#          Válidos: pi-dns2 (alias pi-utils) | pi-dns | pi-obs | pi-sonar | retaco | pinchi | miugarita
#
# El envío funciona desde cualquier nodo de la misma LAN (192.168.10.0/24) —
# el magic packet es un broadcast de capa 2/UDP, no importa el origen exacto
# mientras esté en el mismo segmento. pi-dns2 (antes pi-utils, mejora 55) es el valor
# por defecto solo por convención: es un nodo siempre encendido y fuera del Swarm.
# =============================================================================
set -euo pipefail

MOLE_MAC="50:eb:f6:97:31:a1"
BROADCAST="192.168.10.255"

NODE="${1:-pi-dns2}"

declare -A TARGETS=(
  [retaco]="admin@192.168.10.7"
  [pi-dns]="admin@192.168.10.2"
  [pi-obs]="admin@192.168.10.4"
  [pi-sonar]="admin@192.168.10.5"
  [pi-dns2]="admin@192.168.10.3"
  [pi-utils]="admin@192.168.10.3"   # alias del nombre antiguo
  [pinchi]="admin@192.168.10.8"
  [miugarita]="admin@192.168.10.9"
)

target="${TARGETS[$NODE]:-}"
if [ -z "${target}" ]; then
  echo "[ERROR] Nodo desconocido: '${NODE}'"
  echo "        Nodos válidos: pi-dns2 | pi-dns | pi-obs | pi-sonar | retaco | pinchi | miugarita"
  exit 1
fi

send_packet() {
  if ! command -v wakeonlan >/dev/null 2>&1; then
    echo "[INFO] Instalando wakeonlan..."
    sudo apt-get update -qq && sudo apt-get install -y -qq wakeonlan
  fi
  wakeonlan -i "${BROADCAST}" "${MOLE_MAC}"
}

echo "[INFO] Enviando magic packet a mole (${MOLE_MAC}) desde ${NODE}..."

# Si este script ya se está ejecutando EN el propio nodo destino (p. ej.
# desplegado en /srv/homelab/shared/scripts/ y lanzado por ssh directo a ese
# nodo — el caso real cuando mole está apagada y no hay otro sitio desde
# donde disparar el ssh anidado), se envía en local sin saltar por ssh.
if [ "$(hostname)" = "${NODE}" ]; then
  send_packet
else
  ssh -o BatchMode=yes -o ConnectTimeout=8 "${target}" "$(declare -f send_packet); MOLE_MAC=${MOLE_MAC} BROADCAST=${BROADCAST} send_packet"
fi

echo "[OK] Paquete enviado. Comprueba en unos segundos/minutos si mole responde:"
echo "     ping -c 3 192.168.10.10"
