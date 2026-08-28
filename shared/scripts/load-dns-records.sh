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
#
# Requiere: curl, jq (sudo apt install -y jq)
#
# PIHOLE_URL por defecto es IP:puerto directo (192.168.1.170:8053, panel de
# Pi-hole publicado en la LAN sin proxy desde el cierre de la mejora 41) --
# a propósito no un hostname: este script es lo que carga los registros que
# harían falta para resolver uno, así que depender de un hostname aquí sería
# circular. Reachable desde cualquier punto de la LAN, no hace falta túnel
# SSH salvo que se ejecute desde fuera de ella.
# =============================================================================
set -euo pipefail

PIHOLE_URL="${PIHOLE_URL:-http://192.168.1.170:8053}"
PIHOLE_PASSWORD="${PIHOLE_PASSWORD:?Debes exportar PIHOLE_PASSWORD}"

# Mantener sincronizado con shared/dns/dns-records.md
# Mejora 41 (cerrada 2026-08-28): home.arpa retirado por completo -- solo
# quedan registros *.404labo.net. PIHOLE_URL ya no puede ser un hostname
# .home.arpa/.404labo.net (dependería de la propia resolución que este
# script está a punto de (re)cargar) -- IP:puerto directo de Pi-hole, sin
# nginx delante (decomisionado en el mismo cierre).
HOSTS='[
  "192.168.1.150 ryzen.404labo.net",
  "192.168.1.174 retaco.404labo.net",
  "192.168.1.174 postgresql.404labo.net",
  "192.168.1.174 valkey.404labo.net",
  "192.168.1.180 ketekasko.404labo.net",
  "192.168.1.170 pi-dns.404labo.net",
  "192.168.1.171 pi-obs.404labo.net",
  "192.168.1.172 pi-sonar.404labo.net",
  "192.168.1.173 pi-utils.404labo.net",
  "192.168.1.175 pinchi.404labo.net",
  "192.168.1.175 home.404labo.net",
  "192.168.1.175 capataz-api.404labo.net",
  "192.168.1.175 openwebui.404labo.net",
  "192.168.1.175 n8n.404labo.net",
  "192.168.1.175 ollama.404labo.net",
  "192.168.1.175 vllm.404labo.net",
  "192.168.1.175 comfyui.404labo.net",
  "192.168.1.175 qdrant.404labo.net",
  "192.168.1.175 whisper.404labo.net",
  "192.168.1.175 grafana.404labo.net",
  "192.168.1.175 prometheus.404labo.net",
  "192.168.1.175 sonarqube.404labo.net",
  "192.168.1.175 bifrost.404labo.net",
  "192.168.1.175 rsshub.404labo.net",
  "192.168.1.175 crawl4ai.scraper.404labo.net",
  "192.168.1.175 n8n-aux.404labo.net",
  "192.168.1.175 portainer.404labo.net",
  "192.168.1.175 vaultwarden.404labo.net",
  "192.168.1.175 registry.404labo.net",
  "192.168.1.175 epub2pdf.404labo.net",
  "192.168.1.175 pdf2chunks.404labo.net",
  "192.168.1.175 open-terminal.404labo.net",
  "192.168.1.175 infisical.404labo.net",
  "192.168.1.175 authentik.404labo.net",
  "192.168.1.175 markitdown.404labo.net"
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
