#!/usr/bin/env bash
# =============================================================================
# install-docker-ubuntu.sh
# Instala Docker Engine y Docker Compose Plugin en Ubuntu (22.04 / 24.04)
# Uso: sudo bash install-docker-ubuntu.sh
# =============================================================================
set -euo pipefail

DOCKER_GPG_KEY="/usr/share/keyrings/docker-archive-keyring.gpg"
DOCKER_SOURCES="/etc/apt/sources.list.d/docker.list"

echo "[INFO] Instalando dependencias previas..."
apt-get update -qq
apt-get install -y --no-install-recommends \
  ca-certificates \
  curl \
  gnupg \
  lsb-release

echo "[INFO] Añadiendo clave GPG oficial de Docker..."
install -m 0755 -d /usr/share/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | gpg --dearmor -o "${DOCKER_GPG_KEY}"
chmod a+r "${DOCKER_GPG_KEY}"

echo "[INFO] Añadiendo repositorio Docker..."
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=${DOCKER_GPG_KEY}] \
  https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" \
  | tee "${DOCKER_SOURCES}" > /dev/null

echo "[INFO] Instalando Docker Engine..."
apt-get update -qq
apt-get install -y \
  docker-ce \
  docker-ce-cli \
  containerd.io \
  docker-buildx-plugin \
  docker-compose-plugin

echo "[INFO] Habilitando y arrancando Docker..."
systemctl enable docker
systemctl start docker

echo "[INFO] Añadiendo usuario actual al grupo docker..."
CURRENT_USER="${SUDO_USER:-$(whoami)}"
if [ "${CURRENT_USER}" != "root" ]; then
  usermod -aG docker "${CURRENT_USER}"
  echo "[INFO] Usuario '${CURRENT_USER}' añadido al grupo docker."
  echo "[WARN] Cierra la sesión y vuelve a entrar para aplicar el cambio de grupo."
fi

echo ""
echo "[OK] Docker instalado correctamente."
docker --version
docker compose version
