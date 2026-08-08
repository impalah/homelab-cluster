#!/usr/bin/env bash
# =============================================================================
# generate-valkey-cert.sh
# Genera (o regenera) el certificado TLS de Valkey (retaco), firmado por la
# CA interna del clúster (generate-ca.sh) — clave y certificado PROPIOS,
# no comparte los de nginx (home-arpa.key nunca sale de este directorio;
# la clave de Valkey es nueva y solo la usa Valkey).
#
# Se ejecuta en pi-dns porque es donde vive ca.key — nunca sale de aquí.
# El resultado (valkey.crt, valkey.key) se copia después a retaco con el
# patrón habitual de despliegue (rsync a /tmp + sudo cp), ver
# docs/25-valkey-cache.md.
#
# Uso:
#   bash generate-valkey-cert.sh                # válido 3650 días (10 años)
#   CERT_DAYS=825 bash generate-valkey-cert.sh   # validez personalizada
# =============================================================================
set -euo pipefail

CA_DIR="/srv/homelab/pi-dns/nginx/ca"
OUT_DIR="/srv/homelab/pi-dns/nginx/certs"
DAYS="${CERT_DAYS:-3650}"

if [ ! -f "${CA_DIR}/ca.key" ] || [ ! -f "${CA_DIR}/ca.crt" ]; then
  echo "[ERROR] No existe la CA interna en ${CA_DIR}/."
  echo "        Generarla primero, una sola vez: bash generate-ca.sh"
  exit 1
fi

mkdir -p "${OUT_DIR}"

# 1. Clave privada + CSR propios de Valkey (sin firmar todavía)
openssl req -nodes -newkey rsa:2048 \
  -keyout "${OUT_DIR}/valkey.key" \
  -out "${OUT_DIR}/valkey.csr" \
  -subj "/CN=valkey.home.arpa"

# 2. Firmar el CSR con la CA interna — mismo criterio que generate-cert.sh
# (basicConstraints=CA:FALSE, extendedKeyUsage=serverAuth explícitos).
openssl x509 -req \
  -in "${OUT_DIR}/valkey.csr" \
  -CA "${CA_DIR}/ca.crt" -CAkey "${CA_DIR}/ca.key" -CAcreateserial \
  -out "${OUT_DIR}/valkey.crt" \
  -days "${DAYS}" \
  -extfile <(printf "basicConstraints=CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\nsubjectAltName=DNS:valkey.home.arpa\n")

rm -f "${OUT_DIR}/valkey.csr"

chmod 644 "${OUT_DIR}/valkey.crt"
chmod 600 "${OUT_DIR}/valkey.key"

EXPIRY=$(openssl x509 -enddate -noout -in "${OUT_DIR}/valkey.crt" | cut -d= -f2)

echo "[OK] Certificado de Valkey generado en ${OUT_DIR}/ (firmado por la CA interna)"
echo "     Válido ${DAYS} días — caduca: ${EXPIRY}"
echo ""
echo "[INFO] Copiar a retaco:"
echo "  rsync -av ${OUT_DIR}/valkey.crt ${OUT_DIR}/valkey.key ${CA_DIR}/ca.crt u-data@192.168.1.174:/tmp/"
echo "  ssh u-data@192.168.1.174 \"sudo mkdir -p /srv/homelab/retaco/valkey/tls && sudo mv /tmp/valkey.crt /tmp/valkey.key /tmp/ca.crt /srv/homelab/retaco/valkey/tls/ && sudo chmod 644 /srv/homelab/retaco/valkey/tls/*.crt && sudo chmod 644 /srv/homelab/retaco/valkey/tls/valkey.key\""
echo "[INFO] Luego: docker compose up -d valkey (recrea con TLS activado)"
