#!/usr/bin/env bash
# =============================================================================
# dns-guard.sh
# Vigila la pila DNS de un nodo (Pi-hole + Unbound, `pi-dns` y, cuando exista,
# `pi-dns2`, mejora 55) y la recupera si Unbound no está en marcha. Escribe
# métricas para Prometheus (textfile collector).
#
# Por qué existe (docs/41-dns-pihole-unbound.md): en un arranque del host
# Docker a veces no consigue levantar `unbound` (`failed to set up container
# networking: Address already in use` sobre su IP fija) y NO lo reintenta, pese a
# `restart: unless-stopped`: Unbound se quedaba parado hasta el siguiente
# reinicio. Con Pi-hole apuntando solo a Unbound eso sería un DNS muerto; en su
# día se "arregló" poniendo 8.8.8.8 en Pi-hole, que además mandaba todas las
# consultas a Google. Este guardián hace de reintento que a Docker le falta.
#
# Qué hace, en orden, solo si Unbound NO está `running`:
#   1. `docker start unbound`
#   2. si sigue sin arrancar: desconectar y reconectar a la red con su IP fija
#      (libera un endpoint que se quedó colgado) y volver a arrancar
#   3. si aún no: `docker compose up -d unbound` con el compose del nodo
# Después comprueba que Unbound responde y que Pi-hole resuelve.
#
# Uso: dns-guard.sh        (pensado para cron, cada minuto, como admin)
#   * * * * * /usr/bin/bash /srv/homelab/shared/scripts/dns-guard.sh >> /var/log/homelab-dns-guard.log 2>&1
#
# Variables (todas opcionales; los valores por defecto son los de `pi-dns`):
#   DNS_UNBOUND_CONTAINER  nombre del contenedor de Unbound     [unbound]
#   DNS_PIHOLE_CONTAINER   nombre del contenedor de Pi-hole     [pihole]
#   DNS_NETWORK            red Docker con las IP fijas          [pi-dns-net]
#   DNS_UNBOUND_IP         IP fija de Unbound en esa red        [172.20.0.2]
#   DNS_COMPOSE_FILE       compose del nodo                     [/srv/homelab/$(hostname -s)/docker-compose.yml]
#   DNS_TEST_NAME          nombre usado para probar resolución  [example.com]
#
# Código de salida: 0 si todo está bien al terminar, 1 si no.
# =============================================================================
set -uo pipefail

UNBOUND="${DNS_UNBOUND_CONTAINER:-unbound}"
PIHOLE="${DNS_PIHOLE_CONTAINER:-pihole}"
NET="${DNS_NETWORK:-pi-dns-net}"
UNBOUND_IP="${DNS_UNBOUND_IP:-172.20.0.2}"
COMPOSE_FILE="${DNS_COMPOSE_FILE:-/srv/homelab/$(hostname -s)/docker-compose.yml}"
TEST_NAME="${DNS_TEST_NAME:-example.com}"
OUT_DIR="/srv/homelab/node-exporter-textfile"
OUT="${OUT_DIR}/dns-guard.prom"

log() { echo "[$(date -u +%FT%TZ)] dns-guard: $*"; }

# Un solo guardián a la vez (cron cada minuto + una ejecución a mano).
exec 9>"/tmp/dns-guard.$(id -un).lock" || exit 1
flock -n 9 || exit 0

unbound_state() { docker inspect -f '{{.State.Status}}' "${UNBOUND}" 2>/dev/null || echo "missing"; }

RECOVERED=0
if [ "$(unbound_state)" != "running" ]; then
  log "AVISO: ${UNBOUND} está en estado '$(unbound_state)' -- intentando recuperarlo"
  RECOVERED=1

  docker start "${UNBOUND}" >/dev/null 2>&1
  sleep 3

  if [ "$(unbound_state)" != "running" ]; then
    log "docker start no bastó; reconectando a ${NET} con ${UNBOUND_IP}"
    docker network disconnect -f "${NET}" "${UNBOUND}" >/dev/null 2>&1
    docker network connect --ip "${UNBOUND_IP}" "${NET}" "${UNBOUND}" >/dev/null 2>&1
    docker start "${UNBOUND}" >/dev/null 2>&1
    sleep 3
  fi

  if [ "$(unbound_state)" != "running" ] && [ -r "${COMPOSE_FILE}" ]; then
    log "aún parado; docker compose up -d ${UNBOUND} (${COMPOSE_FILE})"
    docker compose -f "${COMPOSE_FILE}" up -d --no-deps "${UNBOUND}" >/dev/null 2>&1
    sleep 3
  fi
fi

UNBOUND_UP=0
if [ "$(unbound_state)" = "running" ]; then
  # Healthcheck de Docker: dar hasta 30 s tras un arranque.
  for _ in $(seq 1 15); do
    h=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}healthy{{end}}' "${UNBOUND}" 2>/dev/null)
    [ "${h}" = "healthy" ] && break
    sleep 2
  done
  # Prueba funcional: ¿Unbound contesta de verdad?
  if docker exec "${PIHOLE}" dig +short +time=3 +tries=1 "@${UNBOUND_IP}" -p 5335 "${TEST_NAME}" 2>/dev/null | grep -q .; then
    UNBOUND_UP=1
  fi
fi

PIHOLE_OK=0
if docker exec "${PIHOLE}" dig +short +time=3 +tries=1 @127.0.0.1 "${TEST_NAME}" 2>/dev/null | grep -q .; then
  PIHOLE_OK=1
fi

if [ "${RECOVERED}" -eq 1 ]; then
  if [ "${UNBOUND_UP}" -eq 1 ]; then log "RECUPERADO: ${UNBOUND} responde de nuevo"; else log "ERROR: no se pudo recuperar ${UNBOUND}"; fi
fi
[ "${PIHOLE_OK}" -eq 1 ] || log "ERROR: Pi-hole no resuelve ${TEST_NAME}"

# Métricas (si el directorio del textfile collector existe y es escribible).
if [ -d "${OUT_DIR}" ] && [ -w "${OUT_DIR}" ]; then
  tmp=$(mktemp "${OUT}.XXXXXX")
  {
    echo "# HELP homelab_dns_unbound_up 1 si Unbound esta en marcha y responde."
    echo "# TYPE homelab_dns_unbound_up gauge"
    echo "homelab_dns_unbound_up ${UNBOUND_UP}"
    echo "# HELP homelab_dns_pihole_resolve_ok 1 si Pi-hole resuelve un nombre de prueba."
    echo "# TYPE homelab_dns_pihole_resolve_ok gauge"
    echo "homelab_dns_pihole_resolve_ok ${PIHOLE_OK}"
    echo "# HELP homelab_dns_guard_recovered_last_run 1 si en la ultima ejecucion hubo que levantar Unbound."
    echo "# TYPE homelab_dns_guard_recovered_last_run gauge"
    echo "homelab_dns_guard_recovered_last_run ${RECOVERED}"
    echo "# HELP homelab_dns_guard_last_run_timestamp_seconds Momento de la ultima ejecucion del guardian."
    echo "# TYPE homelab_dns_guard_last_run_timestamp_seconds gauge"
    echo "homelab_dns_guard_last_run_timestamp_seconds $(date +%s)"
  } > "${tmp}" && chmod 644 "${tmp}" && mv "${tmp}" "${OUT}"
fi

[ "${UNBOUND_UP}" -eq 1 ] && [ "${PIHOLE_OK}" -eq 1 ]
