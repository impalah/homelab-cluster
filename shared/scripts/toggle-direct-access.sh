#!/usr/bin/env bash
# =============================================================================
# toggle-direct-access.sh
# Activa o desactiva el acceso DIRECTO por IP:puerto a los servicios HTTP de
# un nodo que también están expuestos vía Traefik (docker-swarm/stacks/
# traefik/) — en "off", esos puertos solo aceptan conexiones desde los nodos
# del Swarm; el resto de la LAN tiene que pasar siempre por
# https://<servicio>.404labo.net, igual que hoy hace cualquiera que ya use
# el hostname en vez de la IP.
#
# Mejora 41 (cierre, 2026-08-28) -- REESCRITO: hasta ahora el único origen
# permitido en "off" era pi-dns (192.168.1.170), porque nginx ahí era el
# único que proxificaba estos puertos. Con nginx decomisionado, quien
# proxifica de verdad es Traefik, en `mode: global` sobre los 5 nodos
# manager del Swarm (retaco/pi-obs/pi-sonar/pi-utils/pinchi) -- la petición
# real que llega a cada backend puede originarse en CUALQUIERA de esos 5,
# no en pi-dns (que ya no tiene ningún rol de proxy). Dejar el allowlist
# viejo tal cual habría roto el propio tráfico legítimo de Traefik en modo
# "off" -- bug real encontrado (sin llegar a desplegarse, verificado antes:
# ningún nodo tenía reglas DROP activas) al revisar este script durante el
# cierre de la mejora 41.
#
# Requiere haber ejecutado antes setup-firewall.sh en el nodo. Ver el
# razonamiento completo (por qué "ufw deny <puerto>" NO basta con Docker) en
# docs/17-firewall-acceso-directo.md.
#
# Uso: bash toggle-direct-access.sh <nodo|all> <on|off|status>
#   on     — acceso directo abierto a toda la LAN (estado actual/por defecto)
#   off    — solo los nodos del Swarm pueden alcanzar esos puertos directamente
#   status — muestra el estado actual de cada puerto, sin cambiar nada
#
# Nodos válidos: ryzen | retaco | pi-obs | pi-sonar | pi-utils | pinchi | all
# (pi-dns queda fuera -- ya no proxifica nada, no necesita ser origen
# permitido)
#
# ⚠️ Revisión de constraints/`mode: host` → `ingress` (2026-08-31, ver mejora
# 43/46 en docs/22-mejoras-futuras.md): a día de hoy, NINGÚN servicio del
# clúster publica su puerto en `mode: host` -- todos son `mode: ingress`
# (incluidos los que siguen con `constraints` de nodo fijo, como
# `sonarqube`). Eso significa que, en teoría, la routing mesh de Swarm
# publica cada puerto gestionado aquí en LOS 5 MANAGERS, no solo en el nodo
# donde `NODE_PORTS` lo agrupa -- la segmentación por nodo de este script
# podría no estar cerrando el acceso directo desde los otros 4 managers a
# un puerto "asignado" a uno solo. **No verificado en vivo** si
# `DOCKER-USER` intercepta también el tráfico reenviado por la routing mesh
# en los nodos que NO ejecutan la tarea real -- pendiente de comprobar
# antes de asumir que `off` cierra el acceso directo de verdad en los 5
# sitios. Ver mejora 46, `docs/22-mejoras-futuras.md`.
# =============================================================================
set -euo pipefail

# Los 5 nodos manager del Swarm -- cualquiera puede ser el que de verdad
# origina la petición proxificada por Traefik (mode: global), ver cabecera.
SWARM_NODE_IPS="192.168.1.171 192.168.1.172 192.168.1.173 192.168.1.174 192.168.1.175"

NODE="${1:-}"
MODE="${2:-}"

if [ -z "${NODE}" ] || [ -z "${MODE}" ]; then
  echo "[ERROR] Uso: toggle-direct-access.sh <nodo|all> <on|off|status>"
  echo "        Nodos válidos: ryzen | retaco | pi-obs | pi-sonar | pi-utils | pinchi | all"
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
  [pinchi]="u-forge@192.168.1.175"
)

# Puertos HTTP publicados por nodo que TAMBIÉN tienen ruta en nginx — solo
# estos se gestionan aquí. Puertos de infraestructura (node-exporter,
# cadvisor, portainer-agent, postgres-main) quedan FUERA a propósito: no
# pasan por nginx, así que "solo pi-dns" los dejaría inalcanzables para
# quien de verdad los necesita (Prometheus, Portainer, postgres-exporter,
# SonarQube) — ver docs/17-firewall-acceso-directo.md.
# ⚠️ Desde la revisión de constraints (2026-08-31, mejora 43), la mayoría de
# estos servicios YA NO están fijados a un nodo -- Swarm puede reprogramar
# la tarea a cualquiera de los 5 managers en cualquier momento. Los puertos
# se agrupan aquí por dónde estaba el servicio en el momento de escribir
# esto (o dónde tiene sentido revisarlo primero), no como garantía de dónde
# sigue estando ahora -- confirmar con `docker service ps <servicio>` antes
# de asumir que un puerto "pertenece" a un nodo concreto. `qdrant`,
# `postgres-main`, `sonarqube` y los servicios de `pi-obs` SÍ siguen con
# `constraints` real (ver docs/01-topologia.md, diagrama de colocación).
declare -A NODE_PORTS=(
  [ryzen]="8080 11434 9800 8010 8188"      # open-webui ollama whisper vllm comfyui
  [retaco]="5678 6333 5000 8003 8004"        # n8n-main qdrant(fijo) registry epub2pdf-service pdf2chunks-service
  [pi-obs]="3000 9090"                      # grafana prometheus
  [pi-sonar]="19000"                        # sonarqube (fijo -- 2026-08-31: 9000 -> 19000, ver mejora del choque de puerto con authentik/portainer)
  [pi-utils]="1200 8001 5679"               # rsshub markitdown n8n-aux
  [pinchi]="19001 8222"                     # portainer(2026-08-31: 9000->19001, movido de pi-utils a pinchi) vaultwarden(movido de pi-utils a pinchi)
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
  allow_count=0
  has_drop=0
  for SRC_IP in ${SWARM_NODE_IPS}; do
    if sudo iptables -C DOCKER-USER -p tcp --dport \"\${PORT}\" -s \"\${SRC_IP}\" -j ACCEPT 2>/dev/null; then
      allow_count=\$((allow_count + 1))
    fi
  done
  if sudo iptables -C DOCKER-USER -p tcp --dport \"\${PORT}\" -j DROP 2>/dev/null; then
    has_drop=1
  fi

  if [ '${MODE}' = 'status' ]; then
    if [ \"\${has_drop}\" = 1 ]; then
      echo \"  [CERRADO] puerto \${PORT} -- solo nodos del Swarm (\${allow_count}/5 reglas ACCEPT)\"
    else
      echo \"  [ABIERTO] puerto \${PORT} -- toda la LAN\"
    fi
  elif [ '${MODE}' = 'off' ]; then
    for SRC_IP in ${SWARM_NODE_IPS}; do
      if ! sudo iptables -C DOCKER-USER -p tcp --dport \"\${PORT}\" -s \"\${SRC_IP}\" -j ACCEPT 2>/dev/null; then
        sudo iptables -I DOCKER-USER 1 -p tcp --dport \"\${PORT}\" -s \"\${SRC_IP}\" -j ACCEPT
      fi
    done
    if [ \"\${has_drop}\" = 0 ]; then
      sudo iptables -A DOCKER-USER -p tcp --dport \"\${PORT}\" -j DROP
    fi
    echo \"  [CERRADO] puerto \${PORT} -- ahora solo nodos del Swarm\"
  elif [ '${MODE}' = 'on' ]; then
    for SRC_IP in ${SWARM_NODE_IPS}; do
      if sudo iptables -C DOCKER-USER -p tcp --dport \"\${PORT}\" -s \"\${SRC_IP}\" -j ACCEPT 2>/dev/null; then
        sudo iptables -D DOCKER-USER -p tcp --dport \"\${PORT}\" -s \"\${SRC_IP}\" -j ACCEPT
      fi
    done
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
  for n in ryzen retaco pi-obs pi-sonar pi-utils pinchi; do
    toggle_node "${n}"
  done
else
  toggle_node "${NODE}"
fi
