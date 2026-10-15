#!/usr/bin/env bash
# =============================================================================
# renew-letsencrypt.sh
# Renueva (solo si toca -- acme.sh no reemite si faltan >30 días para la
# caducidad) el certificado Let's Encrypt real de 404labo.net/*.404labo.net,
# vía reto DNS-01 automático contra Route53 (plugin dns_aws de acme.sh) --
# mejora 32 de docs/22-mejoras-futuras.md. Nunca HTTP-01: el clúster no
# expone el puerto 80 al público a propósito (docs/18-tailscale.md).
#
# Decisión de arquitectura (mejora 32/39): este renovador corre DESACOPLADO
# de Traefik, en pi-dns (único nodo siempre encendido fuera del swarm) --
# ninguna réplica `global` de Traefik gestiona su propio certificatesResolver
# ACME, todas leen el resultado ya escrito, vía el proveedor `file`
# (docker-swarm/stacks/traefik/dynamic/routes.yml). Mejora 41 (2026-08-28,
# cierre): el despliegue del cert nuevo hacia el Swarm secret de Traefik SÍ
# está automatizado ahora -- el --reloadcmd registrado en acme.sh (una vez,
# con --install-cert) es shared/scripts/deploy-traefik-cert.sh, que sube de
# versión el secret (inmutable, no se puede editar en sitio) y hace `docker
# service update` sobre traefik_traefik por SSH desde pi-dns a un nodo
# manager (retaco), con una clave dedicada de un solo propósito (admin@pi-dns ->
# admin@retaco). nginx en pi-dns quedó decomisionado en el mismo cierre --
# ya no hay ningún deploy hacia él.
#
# Credenciales AWS del usuario IAM (dns_aws): lo previsto es leerlas de Infisical
# (ver el aviso de 2026-10-08 más abajo, ahora hay un respaldo); originalmente:
# se leen de Infisical (Machine Identity 'acme-dns-renewer', Universal Auth,
# carpeta /acme-dns-renewer/ del proyecto "Homelab Cluster") vía el mismo
# wrapper de dos pasos que el resto de servicios migrados
# (docs/26-infisical-secretos.md) -- login + run. Las credenciales bootstrap
# de esa Machine Identity (client_id/client_secret/project_id) viven SOLO en
# pi-dns/.env (real, gitignored, nunca en este script ni en git).
#
# El CA (Let's Encrypt, no el ZeroSSL por defecto de acme.sh v3 desde la
# versión 3.x) y el destino de despliegue real (fullchain/key de nginx +
# reload) quedaron registrados UNA VEZ con:
#   acme.sh --issue --dns dns_aws -d 404labo.net -d '*.404labo.net' --server letsencrypt ...
#   acme.sh --install-cert -d 404labo.net --ecc --reloadcmd '...' ...
# Este script solo dispara "--cron" (renueva lo que toque, reutilizando esa
# config guardada) -- no repite esos flags.
#
# Pensado para ejecutarse EN pi-dns (cron diario, ver docs/16-mantenimiento-
# actualizaciones.md) -- necesita el binario de infisical y acme.sh ya
# desplegados ahí (shared/scripts/deploy-infisical-cli.sh pi-dns, e
# instalación manual de acme.sh, ver docs/22-mejoras-futuras.md mejora 32).
# =============================================================================
set -euo pipefail

PI_DNS_ENV=/srv/homelab/pi-dns/.env
ACME_BIN=/srv/homelab/pi-dns/acme.sh/acme.sh
INFISICAL_BIN=/srv/homelab/pi-dns/infisical-cli/infisical
CONFIG_HOME=/srv/homelab/pi-dns/acme.sh/data
CERT_HOME=/srv/homelab/pi-dns/acme.sh/certs

set -a
# shellcheck disable=SC1090
source "${PI_DNS_ENV}"
set +a
# Mejora 41 (cierre, 2026-08-28): infisical.404labo.net dejó de resolver --
# infisical.404labo.net tiene cert real de Let's Encrypt, de por sí confiado
# por el almacén de CAs estándar del sistema (a diferencia de los
# contenedores Go/Node sin almacén propio, ver apikey-service) -- no hace
# falta CA interna aquí.
export INFISICAL_DOMAIN=https://infisical.404labo.net/api

# Orden de preferencia para las credenciales AWS de dns_aws:
#  1. Infisical (Machine Identity 'acme-dns-renewer'), si está configurada y responde.
#  2. Las que acme.sh guardó él mismo en ${CONFIG_HOME}/account.conf
#     (SAVED_AWS_ACCESS_KEY_ID/SECRET), con modo 600 y propiedad de admin.
# Desde la reconstrucción de Infisical del 2026-09-29 la identidad y su carpeta
# /acme-dns-renewer/ ya no existen (el login daba "unable to authenticate" cada
# noche) -- la opción 2 se validó el 2026-10-08 con una emisión de prueba en el
# entorno staging de Let's Encrypt contra Route53, y mantiene la renovación viva
# hasta que se restaure la opción 1. Aviso en el log cada vez que se cae a la 2.
ACME_ARGS=(--cron --config-home "${CONFIG_HOME}" --cert-home "${CERT_HOME}")

if [ -n "${ACME_RENEWER_INFISICAL_CLIENT_ID:-}" ] && \
   TOKEN=$("${INFISICAL_BIN}" login --method=universal-auth \
     --client-id="${ACME_RENEWER_INFISICAL_CLIENT_ID}" \
     --client-secret="${ACME_RENEWER_INFISICAL_CLIENT_SECRET}" \
     --plain --silent 2>/dev/null) && [ -n "${TOKEN}" ]; then
  exec "${INFISICAL_BIN}" run --token="${TOKEN}" --projectId="${ACME_RENEWER_INFISICAL_PROJECT_ID}" \
    --env=prod --path=/acme-dns-renewer/ -- "${ACME_BIN}" "${ACME_ARGS[@]}"
fi

echo "[WARN] $(date -u +%FT%TZ) Infisical (acme-dns-renewer) no disponible -- usando las credenciales AWS guardadas por acme.sh en ${CONFIG_HOME}/account.conf" >&2
exec "${ACME_BIN}" "${ACME_ARGS[@]}"
