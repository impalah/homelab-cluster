#!/usr/bin/env bash
# =============================================================================
# fix-dns-resolver.sh
# Comprueba, en cada nodo, que la resolución de *.404labo.net funciona de
# verdad — es decir, que systemd-resolved está usando pi-dns
# (192.168.1.170) y no cae al DNS secundario del netplan (1.1.1.1). Si no
# funciona, reinicia systemd-resolved en ese nodo (mismo fix aplicado a
# mano en pi-sonar cuando SonarQube no podía resolver postgresql.404labo.net
# tras un encendido físico — ver docs/13-troubleshooting.md,
# docs/20-apagado-y-encendido-cluster.md).
#
# Prueba FUNCIONAL, no de introspección de `resolvectl status`: resuelve
# un hostname *.404labo.net real (getent, es decir, por la misma ruta que
# usa cualquier proceso del nodo — incluido el daemon de Docker al hacer
# pull de registry.404labo.net) y compara la IP devuelta con la esperada.
# 1.1.1.1 (el DNS secundario) no conoce ningún registro 404labo.net, así que
# una respuesta correcta solo puede venir de pi-dns — sin ambigüedad.
#
# pi-dns es la excepción: ahí systemd-resolved está deshabilitado a propósito
# (Pi-hole ocupa el puerto 53 y /etc/resolv.conf apunta a 127.0.0.1 — ver
# pi-dns/README.md), así que en pi-dns solo se COMPRUEBA; nunca se reinicia
# systemd-resolved (arrancarlo ahí es justo lo que no hay que hacer). Si pi-dns
# falla, lo que hay que revisar son los contenedores pihole/unbound.
#
# Un nodo inaccesible por SSH (apagado, colgado) se informa y se sigue con el
# resto; el código de salida es 1 si algún nodo falló o no se pudo comprobar.
#
# Uso: bash fix-dns-resolver.sh <nodo|all>
#
# Nodos válidos: pi-dns | pi-obs | pi-sonar | pi-utils | retaco | pinchi | all
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
  echo "        Nodos válidos: pi-dns | pi-obs | pi-sonar | pi-utils | retaco | pinchi | all"
  exit 1
fi

declare -A TARGETS=(
  [pi-dns]="u-dns@192.168.1.170"
  [pi-obs]="u-obs@192.168.1.171"
  [pi-sonar]="u-sonar@192.168.1.172"
  [pi-utils]="u-utils@192.168.1.173"
  [retaco]="u-data@192.168.1.174"
  [pinchi]="u-forge@192.168.1.175"
)

# Hostname *.404labo.net a resolver como prueba en cada nodo, y la IP
# esperada — evitando que un nodo resuelva su propio hostname (que en
# Ubuntu suele responder vía /etc/hosts con 127.0.1.1, sin pasar por DNS
# de verdad, dando un falso "OK").
declare -A TEST_QUERY=(
  [pi-dns]="retaco.404labo.net"
  [pi-obs]="pi-dns.404labo.net"
  [pi-sonar]="pi-dns.404labo.net"
  [pi-utils]="pi-dns.404labo.net"
  [retaco]="pi-dns.404labo.net"
  [pinchi]="pi-dns.404labo.net"
)
declare -A TEST_EXPECTED=(
  [pi-dns]="192.168.1.174"
  [pi-obs]="192.168.1.170"
  [pi-sonar]="192.168.1.170"
  [pi-utils]="192.168.1.170"
  [retaco]="192.168.1.170"
  [pinchi]="192.168.1.170"
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

  # En pi-dns no se reinicia nada (ver cabecera): solo se informa.
  local fix_cmd="sudo systemctl restart systemd-resolved"
  if [ "${name}" = "pi-dns" ]; then
    fix_cmd="false"
  fi

  local remote_script="
resolve() { getent ahostsv4 ${query} 2>/dev/null | awk 'NR==1 {print \$1}'; }
answer=\$(resolve)
if [ \"\${answer}\" = \"${expected}\" ]; then
  echo \"OK \${answer}\"
elif ${fix_cmd}; then
  sleep 2
  answer_after=\$(resolve)
  if [ \"\${answer_after}\" = \"${expected}\" ]; then
    echo \"FIXED \${answer:-vacía}->\${answer_after}\"
  else
    echo \"STILLFAIL \${answer_after:-vacía}\"
  fi
else
  echo \"NOFIX \${answer:-vacía}\"
fi
"

  local result
  result=$(ssh -o BatchMode=yes -o ConnectTimeout=8 "${target}" "${remote_script}" 2>/dev/null) || {
    echo -e "  ${RED}[ERROR]${NC} ${name} — no se pudo conectar por SSH (¿nodo apagado?)"
    return 1
  }

  local status="${result%% *}"
  local value="${result#* }"

  case "${status}" in
    OK)        echo -e "  ${GREEN}[OK]${NC}    ${name} — ${query} → ${value}" ;;
    FIXED)     echo -e "  ${YELLOW}[FIXED]${NC} ${name} — estaba mal (${value%%->*}), reiniciado systemd-resolved, ahora resuelve: ${value##*->}" ;;
    STILLFAIL) echo -e "  ${RED}[FAIL]${NC}  ${name} — sigue sin resolver ${query} correctamente tras reiniciar systemd-resolved (obtenido: ${value}) — revisar a mano"; return 1 ;;
    NOFIX)     echo -e "  ${RED}[FAIL]${NC}  ${name} — no resuelve ${query} (obtenido: ${value}); en pi-dns no se toca systemd-resolved — revisar los contenedores pihole/unbound"; return 1 ;;
    *)         echo -e "  ${RED}[FAIL]${NC}  ${name} — salida inesperada: ${result}"; return 1 ;;
  esac
}

if [ "${NODE}" = "all" ]; then
  rc=0
  for n in pi-dns pi-obs pi-sonar pi-utils retaco pinchi; do
    check_node "${n}" || rc=1
  done
  exit "${rc}"
else
  check_node "${NODE}"
fi
