#!/usr/bin/env bash
# =============================================================================
# setup-swarm-firewall.sh
# Restringe el tráfico de control de Docker Swarm (TCP 2377 gestión, TCP+UDP
# 7946 gossip, UDP 4789 VXLAN overlay) a solo los 5 nodos del swarm.
#
# Estos puertos los escucha `dockerd` directamente en el host, filtrados por
# la cadena INPUT normal -- un mecanismo distinto al de
# shared/scripts/setup-firewall.sh / toggle-direct-access.sh, que gestionan
# DOCKER-USER (tráfico DNAT de puertos publicados por contenedores).
#
# Auditoría en vivo (2026-08-24): la política INPUT en los 5 nodos es ACCEPT
# sin ninguna regla -- estos puertos NO están bloqueados hoy, están abiertos
# a toda la LAN por defecto. Este script no "abre" nada: restringe la
# exposición de estos 3 puertos a solo los otros nodos del swarm, en vez de
# dejarlos alcanzables desde cualquier IP de la LAN.
#
# Requiere iptables-persistent ya instalado (shared/scripts/setup-firewall.sh)
# -- lo confirma antes de aplicar nada.
#
# Uso: bash setup-swarm-firewall.sh apply|status
# =============================================================================
set -euo pipefail

declare -A SWARM_NODES=(
  [retaco]="u-data@192.168.1.174"
  [pi-obs]="u-obs@192.168.1.171"
  [pi-sonar]="u-sonar@192.168.1.172"
  [pi-utils]="u-utils@192.168.1.173"
  [pinchi]="u-forge@192.168.1.175"
)

declare -A SWARM_IPS=(
  [retaco]="192.168.1.174"
  [pi-obs]="192.168.1.171"
  [pi-sonar]="192.168.1.172"
  [pi-utils]="192.168.1.173"
  [pinchi]="192.168.1.175"
)

ACTION="${1:-}"

apply_node() {
  local name="$1"
  local target="${SWARM_NODES[$name]}"
  echo ""
  echo "=== ${name} ==="

  # IPs de los OTROS 4 nodos del swarm (todas menos la propia)
  local peer_ips=()
  for peer in "${!SWARM_IPS[@]}"; do
    if [ "${peer}" != "${name}" ]; then
      peer_ips+=("${SWARM_IPS[$peer]}")
    fi
  done

  local remote_cmds="set -euo pipefail
if ! dpkg -s iptables-persistent >/dev/null 2>&1; then
  echo '[ERROR] iptables-persistent no está instalado -- ejecuta antes shared/scripts/setup-firewall.sh ${name}'
  exit 1
fi
"
  for ip in "${peer_ips[@]}"; do
    remote_cmds+="
sudo iptables -C INPUT -p tcp -s ${ip} --dport 2377 -j ACCEPT 2>/dev/null || sudo iptables -I INPUT -p tcp -s ${ip} --dport 2377 -j ACCEPT
sudo iptables -C INPUT -p tcp -s ${ip} --dport 7946 -j ACCEPT 2>/dev/null || sudo iptables -I INPUT -p tcp -s ${ip} --dport 7946 -j ACCEPT
sudo iptables -C INPUT -p udp -s ${ip} --dport 7946 -j ACCEPT 2>/dev/null || sudo iptables -I INPUT -p udp -s ${ip} --dport 7946 -j ACCEPT
sudo iptables -C INPUT -p udp -s ${ip} --dport 4789 -j ACCEPT 2>/dev/null || sudo iptables -I INPUT -p udp -s ${ip} --dport 4789 -j ACCEPT
"
  done
  remote_cmds+="
sudo iptables -C INPUT -p tcp --dport 2377 -j DROP 2>/dev/null || sudo iptables -A INPUT -p tcp --dport 2377 -j DROP
sudo iptables -C INPUT -p tcp --dport 7946 -j DROP 2>/dev/null || sudo iptables -A INPUT -p tcp --dport 7946 -j DROP
sudo iptables -C INPUT -p udp --dport 7946 -j DROP 2>/dev/null || sudo iptables -A INPUT -p udp --dport 7946 -j DROP
sudo iptables -C INPUT -p udp --dport 4789 -j DROP 2>/dev/null || sudo iptables -A INPUT -p udp --dport 4789 -j DROP
sudo netfilter-persistent save
echo '[OK] Reglas de control de Swarm aplicadas y persistidas'
"

  ssh -o BatchMode=yes -o ConnectTimeout=8 "${target}" "${remote_cmds}"
}

status_node() {
  local name="$1"
  local target="${SWARM_NODES[$name]}"
  echo ""
  echo "=== ${name} ==="
  ssh -o BatchMode=yes -o ConnectTimeout=8 "${target}" \
    "sudo iptables -L INPUT -n --line-numbers | grep -E '2377|7946|4789' || echo '(sin reglas de Swarm todavía)'"
}

case "${ACTION}" in
  apply)
    for n in "${!SWARM_NODES[@]}"; do
      apply_node "${n}"
    done
    ;;
  status)
    for n in "${!SWARM_NODES[@]}"; do
      status_node "${n}"
    done
    ;;
  *)
    echo "[ERROR] Uso: setup-swarm-firewall.sh apply|status"
    exit 1
    ;;
esac
