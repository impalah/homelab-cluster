#!/usr/bin/env bash
# =============================================================================
# wake-mole.sh
# Envía un magic packet de Wake-on-LAN a "mole" (ryzen, 192.168.1.150) desde
# otro nodo del clúster, para encenderla remotamente cuando está apagada o
# hibernada. Ver el detalle completo (requisitos, cómo se comprobó que la
# NIC/kernel lo soportan, limitaciones de la BIOS) en docs/19-wake-on-lan.md.
#
# Uso: bash wake-mole.sh [nodo]
#   nodo — desde qué nodo del clúster se envía el paquete (por defecto pi-utils)
#          Válidos: pi-utils | pi-dns | pi-obs | pi-sonar | retaco
#
# El envío funciona desde cualquier nodo de la misma LAN (192.168.1.0/24) —
# el magic packet es un broadcast de capa 2/UDP, no importa el origen exacto
# mientras esté en el mismo segmento. pi-utils es el valor por defecto solo
# por convención (nodo "de utilidades" del clúster).
# =============================================================================
set -euo pipefail

MOLE_MAC="50:eb:f6:97:31:a1"
BROADCAST="192.168.1.255"

NODE="${1:-pi-utils}"

declare -A TARGETS=(
  [retaco]="u-data@192.168.1.174"
  [pi-dns]="u-dns@192.168.1.170"
  [pi-obs]="u-obs@192.168.1.171"
  [pi-sonar]="u-sonar@192.168.1.172"
  [pi-utils]="u-utils@192.168.1.173"
)

target="${TARGETS[$NODE]:-}"
if [ -z "${target}" ]; then
  echo "[ERROR] Nodo desconocido: '${NODE}'"
  echo "        Nodos válidos: pi-utils | pi-dns | pi-obs | pi-sonar | retaco"
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
echo "     ping -c 3 192.168.1.150"
