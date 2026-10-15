#!/usr/bin/env bash
# =============================================================================
# init-swarm.sh
# Bootstrap del Docker Swarm del clúster (mejora 33, docs/31-docker-swarm.md).
# Orquesta desde el puesto de trabajo por SSH, mismo patrón que
# shared/scripts/deploy-infisical-cli.sh — no se ejecuta a mano en cada nodo.
#
# Uso:
#   bash init-swarm.sh init         # docker swarm init en retaco, en solitario
#   bash init-swarm.sh join-all     # une pinchi/miugarita al Swarm
#   bash init-swarm.sh status       # docker node ls, contra retaco
#
# ⚠️ "join-all" NO se ejecuta hasta validar el PoC de un solo nodo
# (docker-swarm/poc/synthetic-db/) — ver docs/31-docker-swarm.md, Fase 0.
# ⚠️ Actualizado el 2026-10-08 (retirada de las Raspberry Pi, docs/31): el
# Swarm actual son 3 minipcs, bootstrap en `retaco` (no `pinchi`, como en el
# diseño original de 5 managers). Tras la reconstrucción del 2026-09-29
# `retaco` es el único manager real y pinchi/miugarita entraron como WORKER --
# este script une como manager (token de manager), que es el diseño objetivo
# pero NO se ha probado desde la reconstrucción; con 3 managers el quórum
# aguanta la caída de 1 (no de 2). Para el estado real, `docker node ls`.
# =============================================================================
set -euo pipefail

# retaco es el manager de bootstrap — el resto se unen a él, nunca al revés.
BOOTSTRAP_USER="admin"
BOOTSTRAP_IP="192.168.10.7"

declare -A SWARM_NODES=(
  [pinchi]="admin@192.168.10.8"
  [miugarita]="admin@192.168.10.9"
)
# pi-dns y ryzen quedan fuera del swarm por diseño (mejoras 37/39); pi-obs, pi-sonar
# y pi-utils salieron el 2026-10-08 -- no aparecen aquí.

ACTION="${1:-}"

case "${ACTION}" in

  init)
    echo "[INFO] docker swarm init en retaco (${BOOTSTRAP_IP}), nodo único."
    ssh "${BOOTSTRAP_USER}@${BOOTSTRAP_IP}" \
      "docker swarm init --advertise-addr ${BOOTSTRAP_IP}"
    echo "[OK] Swarm iniciado. retaco es manager en solitario."
    ;;

  join-all)
    echo "[INFO] Obteniendo el token de manager desde retaco..."
    TOKEN=$(ssh "${BOOTSTRAP_USER}@${BOOTSTRAP_IP}" "docker swarm join-token -q manager")
    if [ -z "${TOKEN}" ]; then
      echo "[ERROR] No se pudo obtener el join-token. ¿Está retaco ya inicializado como swarm (init)?"
      exit 1
    fi
    for node in "${!SWARM_NODES[@]}"; do
      target="${SWARM_NODES[$node]}"
      echo "[INFO] Uniendo ${node} (${target}) como manager..."
      ssh "${target}" \
        "docker swarm join --token ${TOKEN} ${BOOTSTRAP_IP}:2377"
      echo "[OK] ${node} unido."
    done
    echo ""
    echo "[OK] pinchi y miugarita unidos como managers. Verifica con: bash init-swarm.sh status"
    ;;

  status)
    ssh "${BOOTSTRAP_USER}@${BOOTSTRAP_IP}" "docker node ls"
    ;;

  *)
    echo "[ERROR] Acción desconocida: '${ACTION}'"
    echo "        Uso: init-swarm.sh init | join-all | status"
    exit 1
    ;;
esac
