#!/usr/bin/env bash
# =============================================================================
# generate-cert.sh
# Genera (o regenera) el certificado de *.home.arpa que usa nginx, FIRMADO
# por la CA interna del clúster (generate-ca.sh) — ya no autofirmado.
#
# Al estar firmado por la CA, cualquier dispositivo que confíe en ella
# (instalación única, ver docs/15-ca-interna.md) confía automáticamente en
# este certificado, y en cualquiera que se genere en el futuro con la misma
# CA — sin tener que volver a instalar nada por cada regeneración.
#
# Validez larga (10 años por defecto) a propósito: es un certificado de uso
# puramente interno, sin CA pública que lo emita ni navegadores externos que
# deban confiar en él fuera de la LAN, así que no hay ninguna ventaja de
# seguridad real en forzar renovaciones cortas.
#
# Uso:
#   bash generate-cert.sh                # válido 3650 días (10 años)
#   CERT_DAYS=825 bash generate-cert.sh   # validez personalizada
#
# Requiere que la CA ya exista (bash generate-ca.sh, una sola vez).
# Tras regenerar, recargar nginx para que recoja el certificado nuevo:
#   docker exec nginx nginx -s reload
# =============================================================================
set -euo pipefail

CA_DIR="/srv/homelab/pi-dns/nginx/ca"
CERT_DIR="/srv/homelab/pi-dns/nginx/certs"
DAYS="${CERT_DAYS:-3650}"

if [ ! -f "${CA_DIR}/ca.key" ] || [ ! -f "${CA_DIR}/ca.crt" ]; then
  echo "[ERROR] No existe la CA interna en ${CA_DIR}/."
  echo "        Generarla primero, una sola vez: bash generate-ca.sh"
  exit 1
fi

# Mantener sincronizado con cualquier hostname *.home.arpa nuevo del clúster
DOMAINS=(
  pi-dns.home.arpa
  index.home.arpa
  pihole.home.arpa
  openwebui.home.arpa
  n8n.home.arpa
  ollama.home.arpa
  qdrant.home.arpa
  whisper.home.arpa
  grafana.home.arpa
  prometheus.home.arpa
  sonarqube.home.arpa
  rsshub.home.arpa
  markitdown.home.arpa
  n8n-aux.home.arpa
  portainer.home.arpa
  vaultwarden.home.arpa
  registry.home.arpa
  vllm.home.arpa
  comfyui.home.arpa
  crawl4ai.scraper.home.arpa
)

mkdir -p "${CERT_DIR}"

SAN=""
for d in "${DOMAINS[@]}"; do
  SAN="${SAN}DNS:${d},"
done
SAN="${SAN%,}"

# 1. Clave privada + CSR del certificado de servicio (sin firmar todavía)
openssl req -nodes -newkey rsa:2048 \
  -keyout "${CERT_DIR}/home-arpa.key" \
  -out "${CERT_DIR}/home-arpa.csr" \
  -subj "/CN=home.arpa"

# 2. Firmar el CSR con la CA interna. basicConstraints=CA:FALSE explícito y
# extendedKeyUsage=serverAuth evitan un problema conocido: sin EKU
# serverAuth, macOS/Safari (y Chrome reciente en algunos casos) rechazan el
# certificado como servidor TLS aunque la CA sea de confianza.
openssl x509 -req \
  -in "${CERT_DIR}/home-arpa.csr" \
  -CA "${CA_DIR}/ca.crt" -CAkey "${CA_DIR}/ca.key" -CAcreateserial \
  -out "${CERT_DIR}/home-arpa.crt" \
  -days "${DAYS}" \
  -extfile <(printf "basicConstraints=CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\nsubjectAltName=%s\n" "${SAN}")

rm -f "${CERT_DIR}/home-arpa.csr"

chmod 644 "${CERT_DIR}/home-arpa.crt"
chmod 600 "${CERT_DIR}/home-arpa.key"

EXPIRY=$(openssl x509 -enddate -noout -in "${CERT_DIR}/home-arpa.crt" | cut -d= -f2)

echo "[OK] Certificado generado en ${CERT_DIR}/ (firmado por la CA interna)"
echo "     Válido ${DAYS} días — caduca: ${EXPIRY}"
echo "[INFO] Recuerda recargar nginx: docker exec nginx nginx -s reload"
