#!/usr/bin/env bash
# =============================================================================
# label-nodes.sh
# Aplica los node labels de rol del swarm (docs/31-docker-swarm.md) — se
# ejecuta UNA vez, después de que los 5 nodos ya son managers
# (init-swarm.sh join-all). `docker node update` solo funciona desde un
# manager, así que se ejecuta por SSH contra pinchi (el bootstrap).
#
# role=stateful   -> retaco, pinchi (16 GB RAM / 500 GB SSD) — destino por
#                     defecto de los servicios con estado NUEVOS (mejora 33).
# role=stateless  -> pi-obs, pi-sonar, pi-utils (Raspberry Pi).
#
# Los servicios con estado que YA existen hoy en pi-obs/pi-sonar (Loki,
# Prometheus, Grafana, SonarQube) no se mueven — se quedan pinnados a su nodo
# actual con `node.hostname==<nodo>` en su propio stack, sin depender de este
# label. El label solo gobierna dónde aterriza algo nuevo por defecto.
#
# ⚠️ Los nombres de nodo usados aquí (retaco, pinchi, pi-obs...) asumen que
# `docker node ls` los reporta igual que el hostname del sistema — confirmar
# con `bash init-swarm.sh status` antes de ejecutar esto si hay alguna duda.
# =============================================================================
set -euo pipefail

BOOTSTRAP_USER="u-forge"
BOOTSTRAP_IP="192.168.1.175"

STATEFUL_NODES=("retaco" "pinchi")
STATELESS_NODES=("pi-obs" "pi-sonar" "pi-utils")

label_node() {
  local node="$1"
  local value="$2"
  echo "[INFO] ${node} -> role=${value}"
  ssh "${BOOTSTRAP_USER}@${BOOTSTRAP_IP}" "docker node update --label-add role=${value} ${node}"
}

for n in "${STATEFUL_NODES[@]}"; do
  label_node "${n}" "stateful"
done

for n in "${STATELESS_NODES[@]}"; do
  label_node "${n}" "stateless"
done

echo ""
echo "[OK] Labels aplicados. Verifica con:"
echo "     ssh ${BOOTSTRAP_USER}@${BOOTSTRAP_IP} \"docker node ls -q | xargs docker node inspect --format '{{.Description.Hostname}}: {{.Spec.Labels}}'\""
