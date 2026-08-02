#!/usr/bin/env bash
# =============================================================================
# prepare-host.sh
# Crea los directorios de datos del nodo indicado y ajusta permisos.
# Uso: sudo bash prepare-host.sh <nodo>
# Nodos válidos: ryzen | retaco | pi-dns | pi-obs | pi-sonar | pi-utils
#
# ⚠️ Pensado para la PRIMERA vez que se prepara un nodo (directorios vacíos).
# Volver a ejecutarlo en un nodo que ya tiene datos reales es seguro SOLO
# para los servicios que ya tienen su propio "chown -R <uid>:<uid>" explícito
# más abajo (pisa al genérico) — cualquier otro directorio de datos con un
# propietario distinto al usuario que despliega quedará roto por el chown
# genérico, aunque el contenedor siga "corriendo" (los descriptores de
# fichero ya abiertos siguen funcionando; los nuevos, no). Si añades un
# servicio nuevo a un nodo existente, añade también su chown específico
# aquí si corre con un UID distinto al del usuario que despliega — ver
# docs/13-troubleshooting.md, sección "prepare-host.sh en un nodo ya poblado".
# =============================================================================
set -euo pipefail

NODE="${1:-}"

if [ -z "${NODE}" ]; then
  echo "[ERROR] Debes indicar el nodo. Uso: prepare-host.sh <nodo>"
  echo "        Nodos válidos: ryzen | retaco | pi-dns | pi-obs | pi-sonar | pi-utils"
  exit 1
fi

BASE="/srv/homelab"
DEPLOY_USER="${SUDO_USER:-$(whoami)}"

create_dir() {
  local dir="$1"
  mkdir -p "${dir}"
  echo "[DIR] ${dir}"
}

echo "[INFO] Preparando directorios para nodo: ${NODE}"

case "${NODE}" in

  ryzen)
    create_dir "${BASE}/ryzen/ollama/models"
    create_dir "${BASE}/ryzen/open-webui/data"
    create_dir "${BASE}/ryzen/whisper/models"
    create_dir "${BASE}/ryzen/whisper/cache"
    create_dir "${BASE}/ryzen/vllm/models"
    create_dir "${BASE}/ryzen/comfyui/models"
    create_dir "${BASE}/ryzen/comfyui/input"
    create_dir "${BASE}/ryzen/comfyui/output"
    create_dir "${BASE}/ryzen/comfyui/user"
    create_dir "${BASE}/ryzen/comfyui/custom_nodes"
    create_dir "${BASE}/backups/ryzen"
    chown -R "${DEPLOY_USER}:${DEPLOY_USER}" "${BASE}/ryzen" "${BASE}/backups/ryzen"
    ;;

  retaco)
    create_dir "${BASE}/retaco/postgres/data"
    create_dir "${BASE}/retaco/postgres/init"
    create_dir "${BASE}/retaco/n8n/data"
    create_dir "${BASE}/retaco/qdrant/storage"
    create_dir "${BASE}/retaco/qdrant/snapshots"
    create_dir "${BASE}/backups/retaco"
    chown -R "${DEPLOY_USER}:${DEPLOY_USER}" "${BASE}/retaco" "${BASE}/backups/retaco"
    # n8n necesita UID 1000 (pisa el chown genérico de arriba solo para esta carpeta)
    chown -R 1000:1000 "${BASE}/retaco/n8n/"
    # postgres (imagen postgres:16-alpine) corre internamente como UID 70 —
    # pisa el chown genérico de arriba solo para esta carpeta. IMPORTANTE:
    # si postgres-main ya tiene datos reales (no es la primera vez que se
    # ejecuta este script en este nodo), este chown -R recursivo es
    # necesario precisamente porque el genérico de la línea de arriba ya
    # rompió su propiedad — ver docs/13-troubleshooting.md, sección
    # "prepare-host.sh en un nodo ya poblado".
    chown -R 70:70 "${BASE}/retaco/postgres/data"
    ;;

  pi-dns)
    create_dir "${BASE}/pi-dns/pihole/etc-pihole"
    create_dir "${BASE}/pi-dns/pihole/etc-dnsmasq.d"
    create_dir "${BASE}/pi-dns/unbound/config"
    create_dir "${BASE}/pi-dns/nginx/conf"
    create_dir "${BASE}/pi-dns/nginx/certs"
    create_dir "${BASE}/pi-dns/nginx/ca"
    create_dir "${BASE}/pi-dns/nginx/html"
    create_dir "${BASE}/backups/pi-dns"
    chown -R "${DEPLOY_USER}:${DEPLOY_USER}" "${BASE}/pi-dns" "${BASE}/backups/pi-dns"
    ;;

  pi-obs)
    create_dir "${BASE}/pi-obs/prometheus/data"
    create_dir "${BASE}/pi-obs/grafana/data"
    create_dir "${BASE}/pi-obs/loki/data"
    create_dir "${BASE}/pi-obs/loki/wal"
    create_dir "${BASE}/pi-obs/tempo/data"
    create_dir "${BASE}/pi-obs/otel/config"
    create_dir "${BASE}/pi-obs/node-exporter-textfile"
    create_dir "${BASE}/backups/pi-obs"
    chown -R "${DEPLOY_USER}:${DEPLOY_USER}" "${BASE}/pi-obs" "${BASE}/backups/pi-obs"
    # Grafana UID 472. grafana/ solo contiene data/ (su config estática vive
    # aparte, en config/grafana/), así que se puede chown-ear entera sin problema.
    chown -R 472:472 "${BASE}/pi-obs/grafana/"
    # Prometheus UID 65534 y Loki UID 10001: chown SOLO de los subdirectorios
    # de datos, no del directorio padre. prometheus.yml/loki.yaml (estáticos,
    # copiados a mano por el usuario que despliega) conviven en ese mismo
    # directorio padre junto a data/ — si se chownea el padre entero, el
    # usuario deja de poder copiar ahí su propio fichero de configuración.
    chown -R 65534:65534 "${BASE}/pi-obs/prometheus/data"
    chown -R 10001:10001 "${BASE}/pi-obs/loki/data" "${BASE}/pi-obs/loki/wal"
    # tempo corre como root dentro del contenedor: no necesita chown especial
    ;;

  pi-sonar)
    create_dir "${BASE}/pi-sonar/sonarqube/data"
    create_dir "${BASE}/pi-sonar/sonarqube/extensions"
    create_dir "${BASE}/pi-sonar/sonarqube/logs"
    create_dir "${BASE}/pi-sonar/sonarqube/temp"
    create_dir "${BASE}/backups/pi-sonar"
    chown -R "${DEPLOY_USER}:${DEPLOY_USER}" "${BASE}/pi-sonar" "${BASE}/backups/pi-sonar"
    # SonarQube UID 1000 (pisa el chown genérico de arriba solo para esta carpeta)
    chown -R 1000:1000 "${BASE}/pi-sonar/sonarqube/"
    ;;

  pi-utils)
    create_dir "${BASE}/pi-utils/rsshub/data"
    create_dir "${BASE}/pi-utils/n8n-aux/data"
    create_dir "${BASE}/pi-utils/markitdown/cache"
    create_dir "${BASE}/pi-utils/portainer/data"
    create_dir "${BASE}/pi-utils/vaultwarden/data"
    create_dir "${BASE}/backups/pi-utils"
    chown -R "${DEPLOY_USER}:${DEPLOY_USER}" "${BASE}/pi-utils" "${BASE}/backups/pi-utils"
    # n8n-aux UID 1000 (pisa el chown genérico de arriba solo para esta carpeta)
    chown -R 1000:1000 "${BASE}/pi-utils/n8n-aux/"
    ;;

  *)
    echo "[ERROR] Nodo desconocido: '${NODE}'"
    echo "        Nodos válidos: ryzen | retaco | pi-dns | pi-obs | pi-sonar | pi-utils"
    exit 1
    ;;
esac

# Directorio de scripts compartidos
create_dir "${BASE}/shared/scripts"
create_dir "${BASE}/shared/env"
create_dir "${BASE}/shared/dns"
chown -R "${DEPLOY_USER}:${DEPLOY_USER}" "${BASE}/shared"

echo ""
echo "[OK] Directorios creados para nodo '${NODE}'."
echo "     Base: ${BASE}/${NODE}/"
