#!/usr/bin/env bash
# =============================================================================
# check-health.sh
# Verifica el estado de los servicios de un nodo del clúster.
# Uso: bash check-health.sh <nodo>
# Nodos válidos: ryzen | retaco | pi-dns | pi-obs | pi-sonar | pi-utils
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
  echo "=== ryzen (192.168.1.150) ==="
  check_docker_service ollama
  check_docker_service open-webui
  check_docker_service whisper-service
  check_docker_service node-exporter
  check_docker_service cadvisor
  check_docker_service portainer-agent
  check_docker_service watchtower
  check_http "ollama API"         "http://192.168.1.150:11434/api/tags"
  check_http "whisper health"     "http://192.168.1.150:9800/health"
  check_http "open-webui"         "http://192.168.1.150:8080"
  check_http "node-exporter"      "http://192.168.1.150:9100/metrics"
}

check_retaco() {
  echo "=== retaco (192.168.1.174) ==="
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
  check_http "qdrant collections" "http://192.168.1.174:6333/collections" 200 "api-key: ${qdrant_key}"
  check_http "n8n-main"           "http://192.168.1.174:5678/healthz"
  check_http "node-exporter"      "http://192.168.1.174:9100/metrics"
}

check_pi_dns() {
  echo "=== pi-dns (192.168.1.170) ==="
  check_docker_service pihole
  check_docker_service unbound
  check_docker_service nginx
  check_docker_service node-exporter
  check_docker_service cadvisor
  check_docker_service portainer-agent
  check_docker_service watchtower
  check_http "pihole admin (directo)" "http://127.0.0.1:8053/admin"
  check_http "nginx pihole"       "https://pihole.home.arpa/admin/"
  check_http "nginx openwebui"    "https://openwebui.home.arpa"
  check_http "nginx grafana"      "https://grafana.home.arpa"
  check_http "nginx n8n"          "https://n8n.home.arpa"
  check_http "nginx portainer"    "https://portainer.home.arpa"
  check_http "node-exporter"      "http://192.168.1.170:9100/metrics"
  # DNS check
  if command -v dig &>/dev/null; then
    local result
    result=$(dig +short openwebui.home.arpa @192.168.1.170 2>/dev/null | head -1)
    if [ -n "${result}" ]; then
      ok "DNS home.arpa → ${result}"
    else
      fail "DNS home.arpa no resuelve"
    fi
  fi
}

check_pi_obs() {
  echo "=== pi-obs (192.168.1.171) ==="
  check_docker_service otel-collector
  check_docker_service prometheus
  check_docker_service grafana
  check_docker_service loki
  check_docker_service tempo
  check_docker_service node-exporter
  check_docker_service cadvisor
  check_docker_service postgres-exporter
  check_docker_service portainer-agent
  check_docker_service watchtower
  check_http "prometheus"         "http://192.168.1.171:9090/-/healthy"
  check_http "grafana"            "http://192.168.1.171:3000/api/health"
  # loki, tempo y node-exporter en pi-obs están enlazados a 127.0.0.1 a
  # propósito (no los necesita nadie fuera de este nodo, ver docs/06 sección
  # 8) — comprobarlos por la IP de LAN falla siempre, incluso ejecutando
  # este script en el propio pi-obs. Este script se ejecuta localmente en
  # cada nodo (ssh + bash check-health.sh <nodo>), así que 127.0.0.1 es
  # correcto aquí.
  check_http "loki"               "http://127.0.0.1:3100/ready"
  check_http "tempo"              "http://127.0.0.1:3200/ready"
  check_http "node-exporter"      "http://127.0.0.1:9100/metrics"
}

check_pi_sonar() {
  echo "=== pi-sonar (192.168.1.172) ==="
  check_docker_service sonarqube
  check_docker_service node-exporter
  check_docker_service cadvisor
  check_docker_service portainer-agent
  check_docker_service watchtower
  check_http "sonarqube status"   "http://192.168.1.172:9000/api/system/status"
  check_http "node-exporter"      "http://192.168.1.172:9100/metrics"
}

check_pi_utils() {
  echo "=== pi-utils (192.168.1.173) ==="
  check_docker_service rsshub
  check_docker_service markitdown-service
  check_docker_service n8n-aux
  check_docker_service node-exporter
  check_docker_service cadvisor
  check_docker_service portainer
  check_docker_service portainer-agent
  check_docker_service watchtower
  check_docker_service vaultwarden
  check_http "rsshub"             "http://192.168.1.173:1200"
  check_http "markitdown health"  "http://192.168.1.173:8001/health"
  check_http "n8n-aux"            "http://192.168.1.173:5679/healthz"
  check_http "node-exporter"      "http://192.168.1.173:9100/metrics"
  check_http "portainer"          "http://192.168.1.173:9000/api/system/status"
  check_http "vaultwarden"        "http://192.168.1.173:8222/alive"
}

case "${NODE}" in
  ryzen)    check_ryzen ;;
  retaco)   check_retaco ;;
  pi-dns)   check_pi_dns ;;
  pi-obs)   check_pi_obs ;;
  pi-sonar) check_pi_sonar ;;
  pi-utils) check_pi_utils ;;
  all)
    check_ryzen;    echo ""
    check_retaco;   echo ""
    check_pi_dns;   echo ""
    check_pi_obs;   echo ""
    check_pi_sonar; echo ""
    check_pi_utils
    ;;
  *)
    echo "[ERROR] Nodo desconocido: '${NODE}'"
    echo "        Nodos válidos: ryzen | retaco | pi-dns | pi-obs | pi-sonar | pi-utils | all"
    exit 1
    ;;
esac
