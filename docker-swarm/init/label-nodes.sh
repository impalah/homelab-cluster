#!/usr/bin/env bash
# =============================================================================
# label-nodes.sh
# Aplica los node labels de rol del swarm (docs/31-docker-swarm.md) — se
# ejecuta UNA vez, después de que los 3 nodos ya están en el Swarm
# (init-swarm.sh join-all). `docker node update` solo funciona desde un
# manager, así que se ejecuta por SSH contra retaco (el bootstrap desde el
# 2026-09-29, ver docs/31-docker-swarm.md).
#
# role=stateful   -> retaco, pinchi, miugarita (16 GB RAM / 500 GB SSD) —
#                     destino por defecto de los servicios con estado NUEVOS
#                     (mejora 33). Desde la retirada de las Raspberry Pi del
#                     Swarm (2026-10-08) todos los nodos son stateful.
# role=stateless  -> ninguno hoy (antes: pi-obs, pi-sonar, pi-utils).
# Además `common-stack=enabled` en los 3 (node-exporter/cadvisor, stack common).
#
# Los servicios con estado que necesitan un nodo concreto (Postgres, Qdrant,
# Infisical, SonarQube, observabilidad...) se pinnan con `node.hostname==<nodo>`
# en su propio stack, sin depender de este label. El label solo gobierna
# dónde aterriza algo nuevo por defecto.
#
# ⚠️ Los nombres de nodo usados aquí (retaco, pinchi, pi-obs...) asumen que
# `docker node ls` los reporta igual que el hostname del sistema — confirmar
# con `bash init-swarm.sh status` antes de ejecutar esto si hay alguna duda.
# =============================================================================
set -euo pipefail

BOOTSTRAP_USER="admin"
BOOTSTRAP_IP="192.168.10.7"

STATEFUL_NODES=("retaco" "pinchi" "miugarita")
STATELESS_NODES=()

label_node() {
  local node="$1"
  local value="$2"
  echo "[INFO] ${node} -> role=${value}"
  ssh "${BOOTSTRAP_USER}@${BOOTSTRAP_IP}" "docker node update --label-add role=${value} ${node}"
}

for n in "${STATEFUL_NODES[@]}"; do
  label_node "${n}" "stateful"
  ssh "${BOOTSTRAP_USER}@${BOOTSTRAP_IP}" "docker node update --label-add common-stack=enabled ${n}"
done

for n in ${STATELESS_NODES[@]+"${STATELESS_NODES[@]}"}; do
  label_node "${n}" "stateless"
done

echo ""
echo "[OK] Labels aplicados. Verifica con:"
echo "     ssh ${BOOTSTRAP_USER}@${BOOTSTRAP_IP} \"docker node ls -q | xargs docker node inspect --format '{{.Description.Hostname}}: {{.Spec.Labels}}'\""
