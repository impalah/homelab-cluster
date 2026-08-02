#!/usr/bin/env bash
# =============================================================================
# generate-ca.sh
# Genera la CA raíz interna del clúster — SOLO SE EJECUTA UNA VEZ. Instalar
# su certificado público (ca.crt) en cada dispositivo de la LAN es lo que
# hace que los navegadores dejen de avisar sobre "certificado no válido"
# para cualquier *.home.arpa, sin tener que aceptar una excepción manual
# por sitio ni volver a instalar nada cuando se regenere el certificado de
# servicio (generate-cert.sh) en el futuro.
#
# NO ejecutar de nuevo si ya existe una CA: la regenerarías con una clave
# distinta, y todos los dispositivos donde ya la instalaste dejarían de
# confiar en los certificados nuevos hasta reinstalarla en todos ellos.
#
# Uso: bash generate-ca.sh
# Ver instalación por dispositivo en: docs/15-ca-interna.md
# =============================================================================
set -euo pipefail

CA_DIR="/srv/homelab/pi-dns/nginx/ca"
DAYS="${CA_DAYS:-7300}"   # 20 años — debe cubrir sobradamente la validez del certificado de servicio (10 años)

if [ -f "${CA_DIR}/ca.key" ]; then
  echo "[ERROR] Ya existe una CA en ${CA_DIR}/ca.key — no se sobreescribe."
  echo "        Regenerarla invalidaría la confianza ya instalada en todos"
  echo "        los dispositivos. Si de verdad quieres empezar de cero,"
  echo "        borra ${CA_DIR}/ manualmente primero."
  exit 1
fi

mkdir -p "${CA_DIR}"

openssl req -x509 -nodes -newkey rsa:4096 \
  -keyout "${CA_DIR}/ca.key" \
  -out "${CA_DIR}/ca.crt" \
  -days "${DAYS}" \
  -subj "/CN=Homelab Cluster Root CA" \
  -addext "basicConstraints=critical,CA:TRUE" \
  -addext "keyUsage=critical,keyCertSign,cRLSign"

chmod 600 "${CA_DIR}/ca.key"
chmod 644 "${CA_DIR}/ca.crt"

EXPIRY=$(openssl x509 -enddate -noout -in "${CA_DIR}/ca.crt" | cut -d= -f2)

echo "[OK] CA generada en ${CA_DIR}/"
echo "     Válida ${DAYS} días — caduca: ${EXPIRY}"
echo ""
echo "[INFO] Siguiente paso: generar el certificado de servicio firmado por esta CA:"
echo "       bash generate-cert.sh"
echo "[INFO] Luego instalar ${CA_DIR}/ca.crt en cada dispositivo — ver docs/15-ca-interna.md"
