#!/usr/bin/env bash
# =============================================================================
# init-swarm.sh
# Bootstrap del Docker Swarm del clúster (mejora 33, docs/31-docker-swarm.md).
# Orquesta desde el puesto de trabajo por SSH, mismo patrón que
# shared/scripts/deploy-infisical-cli.sh — no se ejecuta a mano en cada nodo.
#
# Uso:
#   bash init-swarm.sh init         # docker swarm init en pinchi, en solitario
#   bash init-swarm.sh join-all     # une retaco/pi-obs/pi-sonar/pi-utils como managers
#   bash init-swarm.sh status       # docker node ls, contra pinchi
#
# ⚠️ "join-all" NO se ejecuta hasta validar el PoC de un solo nodo
# (docker-swarm/poc/synthetic-db/) — ver docs/31-docker-swarm.md, Fase 0.
# Todos los nodos del swarm son manager (decisión tomada: máxima tolerancia a
# caídas, 2 pueden fallar sin perder quórum de escritura) — no hay "worker".
# =============================================================================
set -euo pipefail

# pinchi es el primer manager (bootstrap) — el resto se unen a él, nunca al revés.
BOOTSTRAP_USER="u-forge"
BOOTSTRAP_IP="192.168.1.175"

declare -A SWARM_NODES=(
  [retaco]="u-data@192.168.1.174"
  [pi-obs]="u-obs@192.168.1.171"
  [pi-sonar]="u-sonar@192.168.1.172"
  [pi-utils]="u-utils@192.168.1.173"
)
# pi-dns y ryzen quedan fuera del swarm por diseño (mejoras 37/39) — no aparecen aquí.

ACTION="${1:-}"

case "${ACTION}" in

  init)
    echo "[INFO] docker swarm init en pinchi (${BOOTSTRAP_IP}), nodo único."
    ssh "${BOOTSTRAP_USER}@${BOOTSTRAP_IP}" \
      "docker swarm init --advertise-addr ${BOOTSTRAP_IP}"
    echo "[OK] Swarm iniciado. pinchi es manager en solitario."
    ;;

  join-all)
    echo "[INFO] Obteniendo el token de manager desde pinchi..."
    TOKEN=$(ssh "${BOOTSTRAP_USER}@${BOOTSTRAP_IP}" "docker swarm join-token -q manager")
    if [ -z "${TOKEN}" ]; then
      echo "[ERROR] No se pudo obtener el join-token. ¿Está pinchi ya inicializado como swarm (init)?"
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
    echo "[OK] Los 5 nodos son managers. Verifica con: bash init-swarm.sh status"
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
