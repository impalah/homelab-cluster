#!/usr/bin/env bash
# =============================================================================
# check-health.sh
# Verifica el estado de los servicios de un nodo del clúster.
# Uso: bash check-health.sh <nodo>
# Nodos válidos: ryzen | retaco | pi-dns | pi-obs | pi-sonar | pi-utils | pinchi | miugarita
# Si se omite el nodo, verifica todos los nodos (requiere SSH).
# =============================================================================
set -euo pipefail

NODE="${1:-all}"
TIMEOUT=5

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "  ${GREEN}[OK]${NC}    $1"; }
fail() { echo -e "  ${RED}[FAIL]${NC}  $1"; }
warn() { echo -e "  ${YELLOW}[WARN]${NC}  $1"; }

check_http() {
  local name="$1"
  local url="$2"
  local expected="${3:-200}"
  local header="${4:-}"

  local status
  if [ -n "${header}" ]; then
    status=$(curl -sk -o /dev/null -w "%{http_code}" --max-time "${TIMEOUT}" -H "${header}" "${url}" 2>/dev/null || echo "000")
  else
    status=$(curl -sk -o /dev/null -w "%{http_code}" --max-time "${TIMEOUT}" "${url}" 2>/dev/null || echo "000")
  fi

  if [ "${status}" = "${expected}" ] || [ "${status}" = "200" ] || [ "${status}" = "301" ] || [ "${status}" = "302" ] || [ "${status}" = "308" ]; then
    ok "${name} → ${url} (HTTP ${status})"
  else
    fail "${name} → ${url} (HTTP ${status})"
  fi
}

check_docker_service() {
  local service="$1"
  local state
  # OJO: "{{.State.Health.Status}}" a secas falla (con error) cuando el
  # contenedor no tiene healthcheck definido, y ese fallo imprime una línea
  # vacía en stdout ANTES de fallar — el "|| echo absent" de respaldo acaba
  # concatenado con esa línea vacía ("\nabsent"), que no hace match con
  # ningún caso del case de abajo y no imprime nada, ni OK ni FAIL. El "if"
  # dentro de la propia plantilla evita el error (y la línea vacía) del todo.
  state=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}absent{{end}}' "${service}" 2>/dev/null || echo "absent")

  case "${state}" in
    healthy)   ok "${service} (healthy)" ;;
    starting)  warn "${service} (starting...)" ;;
    unhealthy) fail "${service} (unhealthy)" ;;
    absent)
      # Servicio sin healthcheck: verificar solo que esté running
      local running
      running=$(docker inspect --format='{{.State.Running}}' "${service}" 2>/dev/null || echo "false")
      if [ "${running}" = "true" ]; then
        ok "${service} (running, no healthcheck)"
      else
        fail "${service} (not running)"
      fi
      ;;
    *) fail "${service} (estado desconocido: '${state}')" ;;
  esac
}

check_ryzen() {
  echo "=== ryzen (192.168.10.10) ==="
  check_docker_service ollama
  check_docker_service open-webui
  check_docker_service whisper-service
  check_docker_service node-exporter
  check_docker_service cadvisor
  check_docker_service portainer-agent
  check_docker_service watchtower
  check_http "ollama API"         "http://192.168.10.10:11434/api/tags"
  check_http "whisper health"     "http://192.168.10.10:9800/health"
  check_http "open-webui"         "http://192.168.10.10:8080"
  check_http "node-exporter"      "http://192.168.10.10:9100/metrics"
}

check_retaco() {
  echo "=== retaco (192.168.10.7) ==="
  check_docker_service postgres-main
  check_docker_service n8n-main
  check_docker_service qdrant
  check_docker_service node-exporter
  check_docker_service cadvisor
  check_docker_service portainer-agent
  check_docker_service watchtower
  # Qdrant exige API key (QDRANT_API_KEY) desde que se aseguró el acceso —
  # sin ella responde 401, correctamente. La leemos del .env local si existe.
  local qdrant_key=""
  if [ -f /srv/homelab/retaco/.env ]; then
    qdrant_key=$(grep -m1 '^QDRANT_API_KEY=' /srv/homelab/retaco/.env | cut -d= -f2-)
  fi
  check_http "qdrant collections" "http://192.168.10.7:6333/collections" 200 "api-key: ${qdrant_key}"
  check_http "n8n-main"           "http://192.168.10.7:5678/healthz"
  check_http "node-exporter"      "http://192.168.10.7:9100/metrics"
}

check_pi_dns() {
  echo "=== pi-dns (192.168.10.2) ==="
  check_docker_service pihole
  check_docker_service unbound
  check_docker_service node-exporter
  check_docker_service cadvisor
  check_docker_service portainer-agent
  check_docker_service watchtower
  # nginx retirado (mejora 41, cierre 2026-08-28) -- Traefik en el Swarm
  # sirve ahora todo el tráfico HTTP(S) real, bajo 404labo.net. Panel de
  # Pi-hole publicado directo en la LAN, sin proxy delante.
  check_http "pihole admin (LAN)" "http://192.168.10.2:8053/admin"
  check_http "node-exporter"      "http://192.168.10.2:9100/metrics"
  # DNS check
  if command -v dig &>/dev/null; then
    local result
    result=$(dig +short grafana.404labo.net @192.168.10.2 2>/dev/null | head -1)
    if [ -n "${result}" ]; then
      ok "DNS 404labo.net → ${result}"
    else
      fail "DNS 404labo.net no resuelve"
    fi
  fi
}

# pi-obs / pi-sonar / pi-utils: desde 2026-10-08 ya NO son miembros del Swarm ni
# alojan servicios (retirada de las Raspberry Pi, docs/31-docker-swarm.md) --
# siguen encendidas solo como clientes del SAI. Lo único que tiene sentido
# comprobar aquí es `nut-upsmon` (si cae, ese nodo no se apaga solo en un corte
# de luz) y que NO quede nada del Swarm.
check_pi_sin_servicios() {
  local nombre="$1" ip="$2"
  echo "=== ${nombre} (${ip}) -- sin servicios, solo cliente del SAI ==="
  check_docker_service nut-upsmon
  local swarm
  swarm=$(docker info --format '{{.Swarm.LocalNodeState}}' 2>/dev/null || echo "?")
  if [ "${swarm}" = "inactive" ]; then ok "fuera del Swarm"; else warn "estado Swarm: ${swarm} (se esperaba 'inactive')"; fi
}
check_pi_obs()   { check_pi_sin_servicios pi-obs   192.168.10.4; }
check_pi_sonar() { check_pi_sin_servicios pi-sonar 192.168.10.5; }
check_pi_utils() { check_pi_sin_servicios pi-utils 192.168.10.3; }

# miugarita (2026-10-08): aloja la observabilidad (stack `pi-obs`, nombre
# conservado a propósito), SonarQube y valkey. Los contenedores de Swarm se
# llaman `<stack>_<servicio>.<n>.<id>`, así que se buscan por prefijo.
check_miugarita() {
  echo "=== miugarita (192.168.10.9) ==="
  local c
  for c in pi-obs_loki pi-obs_tempo pi-obs_prometheus pi-obs_grafana pi-obs_otel-collector pi-obs_postgres-exporter pi-obs_nut-exporter sonarqube_sonarqube valkey_valkey common_node-exporter common_cadvisor; do
    local name
    name=$(docker ps --format '{{.Names}}' --filter "name=^${c}\\." | head -1)
    if [ -n "${name}" ]; then check_docker_service "${name}"; else warn "${c} no está en este nodo (el Swarm puede haberlo movido)"; fi
  done
  check_http "loki"               "http://observability.404labo.net:3100/ready"
  check_http "prometheus"         "http://observability.404labo.net:9090/-/healthy"
  check_http "grafana"            "http://observability.404labo.net:3000/api/health"
  check_http "sonarqube status"   "http://192.168.10.9:19000/api/system/status"
  check_http "node-exporter"      "http://192.168.10.9:9100/metrics"
}

# pinchi (2026-08-31): destino de portainer-server/vaultwarden tras la
# revisión de constraints (mejora 43) -- movidos aquí desde pi-utils por
# fiabilidad de disco (NVMe real vs. microSD). Los `check_http` de abajo
# funcionarían igual apuntando a la IP de CUALQUIER manager (todos los
# servicios del clúster están en `mode: ingress`, la routing mesh reenvía
# la petición al nodo real da igual por dónde entre) -- se usa la IP de
# pinchi aquí por ser la más directa/representativa de dónde vive el
# servicio hoy, no porque sea la única que funcione.
check_pinchi() {
  echo "=== pinchi (192.168.10.8) ==="
  check_docker_service portainer-server
  check_docker_service vaultwarden
  check_docker_service node-exporter
  check_docker_service cadvisor
  check_docker_service portainer-agent
  check_docker_service watchtower
  check_http "node-exporter"      "http://192.168.10.8:9100/metrics"
  check_http "portainer"          "http://192.168.10.8:19001/api/system/status"
  check_http "vaultwarden"        "http://192.168.10.8:8222/alive"
}

case "${NODE}" in
  ryzen)    check_ryzen ;;
  retaco)   check_retaco ;;
  pi-dns)   check_pi_dns ;;
  pi-obs)   check_pi_obs ;;
  pi-sonar) check_pi_sonar ;;
  pi-utils) check_pi_utils ;;
  pinchi)   check_pinchi ;;
  miugarita) check_miugarita ;;
  all)
    check_ryzen;    echo ""
    check_retaco;   echo ""
    check_pi_dns;   echo ""
    check_pi_obs;   echo ""
    check_pi_sonar; echo ""
    check_pi_utils; echo ""
    check_pinchi;   echo ""
    check_miugarita
    ;;
  *)
    echo "[ERROR] Nodo desconocido: '${NODE}'"
    echo "        Nodos válidos: ryzen | retaco | pi-dns | pi-obs | pi-sonar | pi-utils | pinchi | miugarita | all"
    exit 1
    ;;
esac
