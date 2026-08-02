#!/usr/bin/env bash
# =============================================================================
# setup-unattended-upgrades.sh
# Instala/activa unattended-upgrades con la config estándar del clúster
# (solo parches de seguridad + ESM, sin reinicio automático) en el nodo local.
# Uso: sudo bash setup-unattended-upgrades.sh
# Pensado para ejecutarse EN cada nodo (vía ssh), no de forma remota.
# =============================================================================
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "[ERROR] Ejecutar con sudo."
  exit 1
fi

echo "[INFO] Instalando unattended-upgrades..."
apt-get update -qq
apt-get install -y unattended-upgrades apt-listchanges

echo "[INFO] Aplicando configuración del clúster (fichero aparte, no toca 50unattended-upgrades)..."
cp "$(dirname "$0")/../config/apt/51-homelab-unattended.conf" /etc/apt/apt.conf.d/51-homelab-unattended
cp "$(dirname "$0")/../config/apt/20auto-upgrades.conf" /etc/apt/apt.conf.d/20auto-upgrades

echo "[INFO] Habilitando temporizadores systemd..."
systemctl enable --now unattended-upgrades.service
systemctl enable --now apt-daily.timer apt-daily-upgrade.timer

echo ""
echo "[OK] unattended-upgrades activo — solo parches de seguridad/ESM, sin reinicio automático."
echo "[INFO] Verificar:"
echo "  systemctl status unattended-upgrades.service"
echo "  systemctl list-timers apt-daily.timer apt-daily-upgrade.timer"
echo "  cat /var/log/unattended-upgrades/unattended-upgrades.log"
