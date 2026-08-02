#!/usr/bin/env bash
# =============================================================================
# toggle-direct-access.sh
# Activa o desactiva el acceso DIRECTO por IP:puerto a los servicios HTTP de
# un nodo que también están expuestos vía nginx en pi-dns (ollama, whisper,
# n8n, etc.) — en "off", esos puertos solo aceptan conexiones desde pi-dns
# (192.168.1.170); el resto de la LAN tiene que pasar siempre por
# https://<servicio>.home.arpa, igual que hoy hace cualquiera que ya use el
# hostname en vez de la IP.
#
# Requiere haber ejecutado antes setup-firewall.sh en el nodo. Ver el
# razonamiento completo (por qué "ufw deny <puerto>" NO basta con Docker) en
# docs/17-firewall-acceso-directo.md.
#
# Uso: bash toggle-direct-access.sh <nodo|all> <on|off|status>
#   on     — acceso directo abierto a toda la LAN (estado actual/por defecto)
#   off    — solo pi-dns puede alcanzar esos puertos directamente
#   status — muestra el estado actual de cada puerto, sin cambiar nada
#
# Nodos válidos: ryzen | retaco | pi-obs | pi-sonar | pi-utils | all
# (pi-dns no tiene puertos gestionados aquí — es el propio origen permitido)
# =============================================================================
set -euo pipefail

PI_DNS_IP="192.168.1.170"

NODE="${1:-}"
MODE="${2:-}"

if [ -z "${NODE}" ] || [ -z "${MODE}" ]; then
  echo "[ERROR] Uso: toggle-direct-access.sh <nodo|all> <on|off|status>"
  echo "        Nodos válidos: ryzen | retaco | pi-obs | pi-sonar | pi-utils | all"
  exit 1
fi

if [[ ! "${MODE}" =~ ^(on|off|status)$ ]]; then
  echo "[ERROR] Modo inválido: '${MODE}'. Usa 'on', 'off' o 'status'."
  exit 1
fi

# nombre -> "usuario@ip" ("local" si este script corre en ese mismo nodo)
declare -A TARGETS=(
  [ryzen]="local"
  [retaco]="u-data@192.168.1.174"
  [pi-obs]="u-obs@192.168.1.171"
  [pi-sonar]="u-sonar@192.168.1.172"
  [pi-utils]="u-utils@192.168.1.173"
)

# Puertos HTTP publicados por nodo que TAMBIÉN tienen ruta en nginx — solo
# estos se gestionan aquí. Puertos de infraestructura (node-exporter,
# cadvisor, portainer-agent, postgres-main) quedan FUERA a propósito: no
# pasan por nginx, así que "solo pi-dns" los dejaría inalcanzables para
# quien de verdad los necesita (Prometheus, Portainer, postgres-exporter,
# SonarQube) — ver docs/17-firewall-acceso-directo.md.
declare -A NODE_PORTS=(
  [ryzen]="8080 11434 9800 8010 8188"      # open-webui ollama whisper vllm comfyui
  [retaco]="5678 6333 5000"                 # n8n-main qdrant registry
  [pi-obs]="3000 9090"                      # grafana prometheus
  [pi-sonar]="9000"                         # sonarqube
  [pi-utils]="1200 8001 5679 9000 8222"     # rsshub markitdown n8n-aux portainer vaultwarden
)

toggle_node() {
  local name="$1"
  local target="${TARGETS[$name]:-}"
  local ports="${NODE_PORTS[$name]:-}"

  if [ -z "${target}" ]; then
    echo "[ERROR] Nodo desconocido: '${name}'"
    return 1
  fi
  if [ -z "${ports}" ]; then
    echo "[INFO] '${name}' no tiene puertos gestionados por este script."
    return 0
  fi

  echo ""
  echo "=== ${name} ==="

  local cmd="
set -uo pipefail
if ! sudo iptables -L DOCKER-USER >/dev/null 2>&1; then
  echo '[ERROR] No existe la cadena DOCKER-USER -- ¿Docker está instalado y arrancado?'
  exit 1
fi
for PORT in ${ports}; do
  has_allow=0
  has_drop=0
  if sudo iptables -C DOCKER-USER -p tcp --dport \"\${PORT}\" -s ${PI_DNS_IP} -j ACCEPT 2>/dev/null; then
    has_allow=1
  fi
  if sudo iptables -C DOCKER-USER -p tcp --dport \"\${PORT}\" -j DROP 2>/dev/null; then
    has_drop=1
  fi

  if [ '${MODE}' = 'status' ]; then
    if [ \"\${has_drop}\" = 1 ]; then
      echo \"  [CERRADO] puerto \${PORT} -- solo pi-dns\"
    else
      echo \"  [ABIERTO] puerto \${PORT} -- toda la LAN\"
    fi
  elif [ '${MODE}' = 'off' ]; then
    if [ \"\${has_allow}\" = 0 ]; then
      sudo iptables -I DOCKER-USER 1 -p tcp --dport \"\${PORT}\" -s ${PI_DNS_IP} -j ACCEPT
    fi
    if [ \"\${has_drop}\" = 0 ]; then
      sudo iptables -A DOCKER-USER -p tcp --dport \"\${PORT}\" -j DROP
    fi
    echo \"  [CERRADO] puerto \${PORT} -- ahora solo pi-dns\"
  elif [ '${MODE}' = 'on' ]; then
    if [ \"\${has_allow}\" = 1 ]; then
      sudo iptables -D DOCKER-USER -p tcp --dport \"\${PORT}\" -s ${PI_DNS_IP} -j ACCEPT
    fi
    if [ \"\${has_drop}\" = 1 ]; then
      sudo iptables -D DOCKER-USER -p tcp --dport \"\${PORT}\" -j DROP
    fi
    echo \"  [ABIERTO] puerto \${PORT} -- ahora toda la LAN\"
  fi
done
if [ '${MODE}' != 'status' ] && command -v netfilter-persistent >/dev/null 2>&1; then
  sudo netfilter-persistent save >/dev/null 2>&1
fi
"

  if [ "${target}" = "local" ]; then
    bash -c "${cmd}"
  else
    ssh -o BatchMode=yes -o ConnectTimeout=8 "${target}" "${cmd}"
  fi
}

if [ "${NODE}" = "all" ]; then
  for n in ryzen retaco pi-obs pi-sonar pi-utils; do
    toggle_node "${n}"
  done
else
  toggle_node "${NODE}"
fi
