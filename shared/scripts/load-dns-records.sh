#!/usr/bin/env bash
# =============================================================================
# load-dns-records.sh
# Carga (o sustituye) la lista completa de registros DNS locales de Pi-hole
# a través de la API de Pi-hole v6, en vez de añadirlos uno a uno en
# Settings → DNS Records. Idempotente: cada ejecución sustituye la lista
# entera, así que también sirve para restaurar los registros tras un reset.
#
# Uso:
#   PIHOLE_PASSWORD=xxx bash load-dns-records.sh
#   PIHOLE_URL=http://localhost:8053 PIHOLE_PASSWORD=xxx bash load-dns-records.sh
#
# Requiere: curl, jq (sudo apt install -y jq)
#
# La primera vez, *.home.arpa todavía no resuelve en ningún sitio (ni en la
# propia Pi), así que hay que ejecutarlo apuntando a localhost/8053 desde la
# propia pi-dns, o a través del túnel SSH:
#   ssh -L 8053:127.0.0.1:8053 u-dns@192.168.1.170
#   PIHOLE_URL=http://localhost:8053 bash load-dns-records.sh
# =============================================================================
set -euo pipefail

PIHOLE_URL="${PIHOLE_URL:-https://pihole.home.arpa}"
PIHOLE_PASSWORD="${PIHOLE_PASSWORD:?Debes exportar PIHOLE_PASSWORD}"

# Mantener sincronizado con shared/dns/dns-records.md
HOSTS='[
  "192.168.1.150 ryzen.home.arpa",
  "192.168.1.174 retaco.home.arpa",
  "192.168.1.174 postgresql.home.arpa",
  "192.168.1.174 valkey.home.arpa",
  "192.168.1.180 ketekasko.home.arpa",
  "192.168.1.170 pi-dns.home.arpa",
  "192.168.1.171 pi-obs.home.arpa",
  "192.168.1.172 pi-sonar.home.arpa",
  "192.168.1.173 pi-utils.home.arpa",
  "192.168.1.170 pihole.home.arpa",
  "192.168.1.170 index.home.arpa",
  "192.168.1.170 capataz-api.home.arpa",
  "192.168.1.170 old.index.home.arpa",
  "192.168.1.170 openwebui.home.arpa",
  "192.168.1.170 n8n.home.arpa",
  "192.168.1.170 ollama.home.arpa",
  "192.168.1.170 vllm.home.arpa",
  "192.168.1.170 comfyui.home.arpa",
  "192.168.1.170 qdrant.home.arpa",
  "192.168.1.170 whisper.home.arpa",
  "192.168.1.170 grafana.home.arpa",
  "192.168.1.170 prometheus.home.arpa",
  "192.168.1.170 sonarqube.home.arpa",
  "192.168.1.170 bifrost.home.arpa",
  "192.168.1.170 rsshub.home.arpa",
  "192.168.1.170 markitdown.home.arpa",
  "192.168.1.170 crawl4ai.scraper.home.arpa",
  "192.168.1.170 n8n-aux.home.arpa",
  "192.168.1.170 portainer.home.arpa",
  "192.168.1.170 vaultwarden.home.arpa",
  "192.168.1.170 apikey.home.arpa",
  "192.168.1.170 registry.home.arpa",
  "192.168.1.170 epub2pdf.home.arpa",
  "192.168.1.170 pdf2chunks.home.arpa",
  "192.168.1.170 open-terminal.home.arpa",
  "192.168.1.170 infisical.home.arpa",
  "192.168.1.170 authentik.home.arpa",
  "192.168.1.170 home.404labo.net",
  "192.168.1.170 capataz-api.404labo.net"
]'

echo "[INFO] Autenticando en ${PIHOLE_URL}..."
SID=$(curl -sk -X POST "${PIHOLE_URL}/api/auth" \
  -H "Content-Type: application/json" \
  -d "{\"password\":\"${PIHOLE_PASSWORD}\"}" | jq -r '.session.sid')

if [ -z "${SID}" ] || [ "${SID}" = "null" ]; then
  echo "[ERROR] No se pudo autenticar (contraseña incorrecta o Pi-hole no responde)"
  exit 1
fi

echo "[INFO] Aplicando registros DNS locales..."
COUNT=$(curl -sk -X PATCH "${PIHOLE_URL}/api/config/dns" \
  -H "sid: ${SID}" -H "Content-Type: application/json" \
  -d "{\"config\":{\"dns\":{\"hosts\":${HOSTS}}}}" | jq '.config.dns.hosts | length')

echo "[OK] ${COUNT} registros aplicados."
