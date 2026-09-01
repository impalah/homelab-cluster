#!/usr/bin/env bash
# =============================================================================
# check-os-updates.sh
# Vigilancia del estado de parcheo del sistema operativo (mejora 36,
# docs/22-mejoras-futuras.md) -- a diferencia de check-image-updates.sh
# (centralizado en pi-obs, vía SSH a los demás nodos), este script está
# pensado para correr LOCALMENTE en cada nodo por cron (mismo criterio ya
# apuntado en la propia mejora: más simple que cada nodo escriba su propio
# fichero .prom que centralizar por SSH para algo que ya corre en cada uno
# vía unattended-upgrades, docs/16-mantenimiento-actualizaciones.md).
#
# Escribe dos métricas Prometheus (textfile collector) en
# /srv/homelab/node-exporter-textfile/os-updates.prom:
#   - node_apt_security_updates_pending: nº de paquetes con actualización de
#     seguridad pendiente (mismo patrón `-security` que el Origins-Pattern de
#     unattended-upgrades, shared/config/apt/51-homelab-unattended.conf).
#   - node_reboot_required: 1 si /var/run/reboot-required existe, 0 si no.
#
# Sin label "node" en las propias métricas a propósito -- Prometheus ya lo
# añade vía `static_configs.labels` en cada job `node-exporter-<nodo>`
# (pi-obs/config/prometheus.yml), a diferencia de check-image-updates.sh
# (un solo fichero centralizado para los 6 nodos, ahí sí hace falta el label
# explícito). Añadirlo aquí también solo produciría un choque renombrado a
# "exported_node" sin aportar nada.
#
# Cron por nodo, a la hora que ya usa unattended-upgrades como referencia
# (después de que corra el timer diario, para que el número refleje el
# estado ya actualizado, no un pico transitorio a mitad de instalar):
#   15 7 * * * bash /srv/homelab/shared/scripts/check-os-updates.sh
#
# Uso: bash check-os-updates.sh
# =============================================================================
set -euo pipefail

OUT_DIR="/srv/homelab/node-exporter-textfile"
OUT_FILE="${OUT_DIR}/os-updates.prom"
TMP_FILE=$(mktemp)

if [ ! -d "${OUT_DIR}" ]; then
  echo "[ERROR] No existe ${OUT_DIR} -- ¿node-exporter de este nodo tiene montado el textfile collector? (mejora 36)"
  exit 1
fi

SECURITY_PENDING=$(apt list --upgradable 2>/dev/null | grep -c -- '-security' || true)

if [ -f /var/run/reboot-required ]; then
  REBOOT_REQUIRED=1
else
  REBOOT_REQUIRED=0
fi

{
  echo "# HELP node_apt_security_updates_pending Número de paquetes con actualización de seguridad pendiente (apt list --upgradable, filtrado a -security)."
  echo "# TYPE node_apt_security_updates_pending gauge"
  echo "node_apt_security_updates_pending ${SECURITY_PENDING}"
  echo "# HELP node_reboot_required 1 si /var/run/reboot-required existe (reinicio pendiente, p. ej. tras un parche de kernel), 0 si no."
  echo "# TYPE node_reboot_required gauge"
  echo "node_reboot_required ${REBOOT_REQUIRED}"
} > "${TMP_FILE}"

chmod 644 "${TMP_FILE}"
mv "${TMP_FILE}" "${OUT_FILE}"

echo "[OK] ${OUT_FILE}: ${SECURITY_PENDING} actualizaciones de seguridad pendientes, reboot_required=${REBOOT_REQUIRED}"
