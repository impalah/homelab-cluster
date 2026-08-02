#!/usr/bin/env bash
# =============================================================================
# setup-firewall.sh
# Prepara un nodo para poder usar toggle-direct-access.sh: instala
# iptables-persistent (para que las reglas añadidas en la cadena
# DOCKER-USER sobrevivan a un reinicio).
# Idempotente -- seguro de re-ejecutar en un nodo ya preparado.
#
# NO instala/gestiona ufw a propósito, tras comprobarlo en vivo en los 6
# nodos: los paquetes "ufw" e "iptables-persistent" se PISAN entre sí en
# Ubuntu/Debian (instalar uno desinstala el otro -- confirmado, no es
# teórico). Como ufw no filtra los puertos publicados por Docker de todos
# modos (ver docs/17-firewall-acceso-directo.md), y lo que sí necesitamos
# de verdad es que las reglas de DOCKER-USER sobrevivan a un reinicio,
# iptables-persistent es el paquete que importa aquí -- se deja ufw fuera
# en vez de perseguir una coexistencia que el propio empaquetado no permite.
#
# Uso: bash setup-firewall.sh <nodo|all>
# Nodos válidos: ryzen | retaco | pi-obs | pi-sonar | pi-utils | all
# =============================================================================
set -euo pipefail

NODE="${1:-}"
if [ -z "${NODE}" ]; then
  echo "[ERROR] Uso: setup-firewall.sh <nodo|all>"
  echo "        Nodos válidos: ryzen | retaco | pi-obs | pi-sonar | pi-utils | all"
  exit 1
fi

# nombre -> "usuario@ip" ("local" si este script corre en ese mismo nodo)
declare -A TARGETS=(
  [ryzen]="local"
  [retaco]="u-data@192.168.1.174"
  [pi-obs]="u-obs@192.168.1.171"
  [pi-sonar]="u-sonar@192.168.1.172"
  [pi-utils]="u-utils@192.168.1.173"
)

REMOTE_SCRIPT='
set -euo pipefail

if dpkg -s ufw >/dev/null 2>&1 && [ "$(dpkg -s ufw | grep -c "Status: install ok installed")" = "1" ]; then
  echo "[INFO] Purgando ufw -- pisa el paquete iptables-persistent que sí necesitamos (confirmado en este mismo clúster, ver docs/22)..."
  sudo ufw --force disable >/dev/null 2>&1 || true
  sudo DEBIAN_FRONTEND=noninteractive apt-get remove --purge -y ufw >/dev/null
fi

echo "[INFO] Instalando iptables-persistent (persiste reglas DOCKER-USER tras reboot)..."
if ! dpkg -s iptables-persistent >/dev/null 2>&1 || [ "$(dpkg -s iptables-persistent | grep -c "Status: install ok installed")" = "0" ]; then
  echo iptables-persistent iptables-persistent/autosave_v4 boolean true | sudo debconf-set-selections
  echo iptables-persistent iptables-persistent/autosave_v6 boolean true | sudo debconf-set-selections
  sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y iptables-persistent
else
  echo "[OK] iptables-persistent ya estaba instalado"
fi

if sudo iptables -L DOCKER-USER >/dev/null 2>&1; then
  echo "[OK] Cadena DOCKER-USER presente -- listo para toggle-direct-access.sh"
else
  echo "[WARN] La cadena DOCKER-USER no existe todavía -- ¿está Docker instalado y arrancado en este nodo?"
fi
'

setup_node() {
  local name="$1"
  local target="${TARGETS[$name]:-}"
  if [ -z "${target}" ]; then
    echo "[ERROR] Nodo desconocido: '${name}'"
    return 1
  fi
  echo ""
  echo "=== ${name} ==="
  if [ "${target}" = "local" ]; then
    bash -c "${REMOTE_SCRIPT}"
  else
    ssh -o BatchMode=yes -o ConnectTimeout=8 "${target}" "${REMOTE_SCRIPT}"
  fi
}

if [ "${NODE}" = "all" ]; then
  for n in ryzen retaco pi-obs pi-sonar pi-utils; do
    setup_node "${n}"
  done
else
  setup_node "${NODE}"
fi
