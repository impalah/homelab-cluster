#!/usr/bin/env bash
# =============================================================================
# update-os.sh
# Actualización COMPLETA de paquetes APT bajo demanda (no solo seguridad,
# a diferencia de unattended-upgrades que corre solo automáticamente).
# No reinicia nada — solo avisa si algún nodo necesita reinicio después.
#
# Uso: bash update-os.sh <nodo|all>
# Nodos válidos: ryzen | retaco | pi-dns | pi-obs | pi-sonar | pi-utils | all
#
# Ejecutar desde un equipo con acceso SSH a todos los nodos (p. ej. ryzen/mole).
# =============================================================================
set -euo pipefail

NODE="${1:-}"

if [ -z "${NODE}" ]; then
  echo "[ERROR] Uso: update-os.sh <nodo|all>"
  echo "        Nodos válidos: ryzen | retaco | pi-dns | pi-obs | pi-sonar | pi-utils | all"
  exit 1
fi

# nombre -> "usuario@ip" ("local" para el propio equipo donde corre este script)
declare -A TARGETS=(
  [ryzen]="local"
  [retaco]="u-data@192.168.1.174"
  [pi-dns]="u-dns@192.168.1.170"
  [pi-obs]="u-obs@192.168.1.171"
  [pi-sonar]="u-sonar@192.168.1.172"
  [pi-utils]="u-utils@192.168.1.173"
)

update_node() {
  local name="$1"
  local target="${TARGETS[$name]}"
  echo ""
  echo "=== ${name} ==="

  local cmd='
    sudo apt-get update -qq &&
    sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -y &&
    sudo apt-get autoremove -y &&
    if [ -f /var/run/reboot-required ]; then
      echo "[REBOOT-REQUIRED] ${HOSTNAME}: $(cat /var/run/reboot-required.pkgs 2>/dev/null | tr "\n" " ")"
    else
      echo "[OK] ${HOSTNAME}: sin reinicio pendiente"
    fi
  '

  if [ "${target}" = "local" ]; then
    bash -c "${cmd}"
  else
    ssh "${target}" "${cmd}"
  fi
}

if [ "${NODE}" = "all" ]; then
  # pi-dns el último: si algo fallara a mitad del bucle, preferible que el
  # DNS del clúster sea lo último tocado, no lo primero.
  for n in ryzen retaco pi-obs pi-sonar pi-utils pi-dns; do
    update_node "${n}"
  done
elif [ -n "${TARGETS[${NODE}]+x}" ]; then
  update_node "${NODE}"
else
  echo "[ERROR] Nodo desconocido: '${NODE}'"
  echo "        Nodos válidos: ryzen | retaco | pi-dns | pi-obs | pi-sonar | pi-utils | all"
  exit 1
fi

echo ""
echo "[INFO] Revisa las líneas [REBOOT-REQUIRED] de arriba — el reinicio es siempre manual, este script nunca reinicia nada."
echo "[INFO] pi-dns en particular: coordina el reinicio con cuidado (es el único punto de fallo del DNS de toda la LAN) — ver docs/13-troubleshooting.md."
