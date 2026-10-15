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
# PIHOLE_URL por defecto es IP:puerto directo (192.168.10.2:8053, panel de
# Pi-hole publicado en la LAN sin proxy desde el cierre de la mejora 41) --
# a propósito no un hostname: este script es lo que carga los registros que
# harían falta para resolver uno, así que depender de un hostname aquí sería
# circular. Reachable desde cualquier punto de la LAN, no hace falta túnel
# SSH salvo que se ejecute desde fuera de ella.
#
# IPs actualizadas (2026-09-28): migración de red a un router Cudy R700, LAN
# nueva 192.168.10.0/24 con reservas DHCP por MAC (ver docs/22-mejoras-
# futuras.md, mejora 50/53 y el propio historial de esta sesión) -- las IPs
# 192.168.1.17x quedaron obsoletas. De paso, añadido `forgejo.404labo.net`
# (mejora 7): faltaba en este script aunque ya estaba en
# shared/dns/dns-records.md desde 2026-09-03 -- drift real entre ambos
# ficheros, no relacionado con la migración de red.
#
# ⚠️ Todos los hostnames servidos por Traefik apuntan HOY a `retaco`
# (192.168.10.7), no a `pinchi` (la convención habitual, ver README.md) --
# recuperación de emergencia del Raft tras la migración: `pi-obs`/`pi-sonar`/
# `pi-utils`/`pinchi` tuvieron que reengancharse como WORKERS, no managers
# (bug real de Docker, `force-new-cluster --advertise-addr` no corrige la
# dirección que un nodo tiene guardada de sí mismo en el registro de
# membresía Raft -- confirmado contra `moby/moby`/`docker/for-linux#523`).
# Traefik tiene `constraints: node.role == manager`, así que con un único
# manager real (`retaco`) es el único nodo donde puede vivir. Volver a
# `pinchi` por convención en cuanto los 4 nodos recuperen su rol de manager
# (requiere una reconstrucción limpia del clúster, no solo un force-new-
# cluster más -- ver el propio historial de esta sesión).
# =============================================================================
set -euo pipefail

PIHOLE_URL="${PIHOLE_URL:-http://192.168.10.2:8053}"
PIHOLE_PASSWORD="${PIHOLE_PASSWORD:?Debes exportar PIHOLE_PASSWORD}"

# Mantener sincronizado con shared/dns/dns-records.md
# Mejora 41 (cerrada 2026-08-28): 404labo.net retirado por completo -- solo
# quedan registros *.404labo.net. PIHOLE_URL ya no puede ser un hostname
# .404labo.net/.404labo.net (dependería de la propia resolución que este
# script está a punto de (re)cargar) -- IP:puerto directo de Pi-hole, sin
# nginx delante (decomisionado en el mismo cierre).
HOSTS='[
  "192.168.10.10 ryzen.404labo.net",
  "192.168.10.7 retaco.404labo.net",
  "192.168.10.7 postgresql.404labo.net",
  "192.168.10.7 valkey.404labo.net",
  "192.168.10.6 ketekasko.404labo.net",
  "192.168.10.2 pi-dns.404labo.net",
  "192.168.10.4 pi-obs.404labo.net",
  "192.168.10.5 pi-sonar.404labo.net",
  "192.168.10.3 pi-utils.404labo.net",
  "192.168.10.8 pinchi.404labo.net",
  "192.168.10.9 miugarita.404labo.net",
  "192.168.10.9 observability.404labo.net",
  "192.168.10.7 home.404labo.net",
  "192.168.10.7 capataz-api.404labo.net",
  "192.168.10.7 openwebui.404labo.net",
  "192.168.10.7 n8n.404labo.net",
  "192.168.10.7 ollama.404labo.net",
  "192.168.10.7 vllm.404labo.net",
  "192.168.10.7 comfyui.404labo.net",
  "192.168.10.7 qdrant.404labo.net",
  "192.168.10.7 whisper.404labo.net",
  "192.168.10.7 grafana.404labo.net",
  "192.168.10.7 prometheus.404labo.net",
  "192.168.10.7 sonarqube.404labo.net",
  "192.168.10.7 bifrost.404labo.net",
  "192.168.10.7 rsshub.404labo.net",
  "192.168.10.7 crawl4ai.scraper.404labo.net",
  "192.168.10.7 n8n-aux.404labo.net",
  "192.168.10.7 portainer.404labo.net",
  "192.168.10.7 vaultwarden.404labo.net",
  "192.168.10.7 registry.404labo.net",
  "192.168.10.7 epub2pdf.404labo.net",
  "192.168.10.7 pdf2chunks.404labo.net",
  "192.168.10.7 open-terminal.404labo.net",
  "192.168.10.7 infisical.404labo.net",
  "192.168.10.7 authentik.404labo.net",
  "192.168.10.7 markitdown.404labo.net",
  "192.168.10.7 ntfy.404labo.net",
  "192.168.10.7 forgejo.404labo.net",
  "192.168.10.7 komodo.404labo.net"
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
