#!/usr/bin/env bash
# =============================================================================
# fix-dns-resolver.sh
# Comprueba, en cada nodo, que la resolución de *.home.arpa funciona de
# verdad — es decir, que systemd-resolved está usando pi-dns
# (192.168.1.170) y no cae al DNS secundario del netplan (1.1.1.1). Si no
# funciona, reinicia systemd-resolved en ese nodo (mismo fix aplicado a
# mano en pi-sonar cuando SonarQube no podía resolver postgresql.home.arpa
# tras un encendido físico — ver docs/13-troubleshooting.md,
# docs/20-apagado-y-encendido-cluster.md).
#
# Prueba FUNCIONAL, no de introspección de `resolvectl status`: resuelve
# un hostname *.home.arpa real y compara la IP devuelta con la esperada.
# 1.1.1.1 (el DNS secundario) no conoce ningún registro home.arpa, así que
# una respuesta correcta solo puede venir de pi-dns — sin ambigüedad,
# a diferencia de intentar leer el campo "Current DNS Server" de
# `resolvectl status`, que ni siquiera aparece en modo "stub" (el habitual
# en estos nodos) y dio falsos positivos de fallo en la primera versión de
# este script.
#
# Uso: bash fix-dns-resolver.sh <nodo|all>
#
# Nodos válidos: pi-dns | pi-obs | pi-sonar | pi-utils | retaco | all
# (ryzen/mole no se incluye — se ejecuta este script localmente ahí, no
# tiene sentido comprobarse a sí mismo por SSH)
# =============================================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

NODE="${1:-}"
if [ -z "${NODE}" ]; then
  echo "[ERROR] Uso: fix-dns-resolver.sh <nodo|all>"
  echo "        Nodos válidos: pi-dns | pi-obs | pi-sonar | pi-utils | retaco | all"
  exit 1
fi

declare -A TARGETS=(
  [pi-dns]="u-dns@192.168.1.170"
  [pi-obs]="u-obs@192.168.1.171"
  [pi-sonar]="u-sonar@192.168.1.172"
  [pi-utils]="u-utils@192.168.1.173"
  [retaco]="u-data@192.168.1.174"
)

# Hostname *.home.arpa a resolver como prueba en cada nodo, y la IP
# esperada — evitando que un nodo resuelva su propio hostname (que en
# Ubuntu suele responder vía /etc/hosts con 127.0.1.1, sin pasar por DNS
# de verdad, dando un falso "OK").
declare -A TEST_QUERY=(
  [pi-dns]="retaco.home.arpa"
  [pi-obs]="pi-dns.home.arpa"
  [pi-sonar]="pi-dns.home.arpa"
  [pi-utils]="pi-dns.home.arpa"
  [retaco]="pi-dns.home.arpa"
)
declare -A TEST_EXPECTED=(
  [pi-dns]="192.168.1.174"
  [pi-obs]="192.168.1.170"
  [pi-sonar]="192.168.1.170"
  [pi-utils]="192.168.1.170"
  [retaco]="192.168.1.170"
)

check_node() {
  local name="$1"
  local target="${TARGETS[$name]:-}"
  local query="${TEST_QUERY[$name]:-}"
  local expected="${TEST_EXPECTED[$name]:-}"

  if [ -z "${target}" ]; then
    echo "[ERROR] Nodo desconocido: '${name}'"
    return 1
  fi

  local remote_script="
answer=\$(resolvectl query ${query} 2>/dev/null | awk '/^${query}:/ {print \$2}')
if [ \"\${answer}\" = \"${expected}\" ]; then
  echo \"OK \${answer}\"
else
  echo \"DNS incorrecto (respuesta: '\${answer:-vacía}', esperada ${expected}), reiniciando systemd-resolved...\" >&2
  sudo systemctl restart systemd-resolved
  sleep 2
  answer_after=\$(resolvectl query ${query} 2>/dev/null | awk '/^${query}:/ {print \$2}')
  if [ \"\${answer_after}\" = \"${expected}\" ]; then
    echo \"FIXED \${answer:-vacía}->\${answer_after}\"
  else
    echo \"STILLFAIL \${answer_after:-vacía}\"
  fi
fi
"

  local result
  result=$(ssh -o BatchMode=yes -o ConnectTimeout=8 "${target}" "${remote_script}" 2>/dev/null) || {
    echo -e "  ${RED}[ERROR]${NC} ${name} — no se pudo conectar por SSH"
    return 1
  }

  local status="${result%% *}"
  local value="${result#* }"

  case "${status}" in
    OK)        echo -e "  ${GREEN}[OK]${NC}    ${name} — ${query} → ${value}" ;;
    FIXED)     echo -e "  ${YELLOW}[FIXED]${NC} ${name} — estaba mal (${value%%->*}), reiniciado systemd-resolved, ahora resuelve: ${value##*->}" ;;
    STILLFAIL) echo -e "  ${RED}[FAIL]${NC}  ${name} — sigue sin resolver ${query} correctamente tras reiniciar systemd-resolved (obtenido: ${value}) — revisar a mano" ;;
    *)         echo -e "  ${RED}[FAIL]${NC}  ${name} — salida inesperada: ${result}" ;;
  esac
}

if [ "${NODE}" = "all" ]; then
  for n in pi-dns pi-obs pi-sonar pi-utils retaco; do
    check_node "${n}"
  done
else
  check_node "${NODE}"
fi
