#!/usr/bin/env bash
# =============================================================================
# deploy-infisical-cli.sh
# Descarga el binario oficial (release de GitHub, sin paquete de sistema ni
# repositorio apt/yum añadido) del CLI de Infisical y lo despliega en
# /srv/homelab/<nodo>/infisical-cli/infisical — NO en /usr/local/bin del
# sistema operativo. Los servicios migrados lo montan por bind-mount
# (:ro) y lo invocan desde `entrypoint:` en el docker-compose.yml de cada
# nodo — ver docs/adr/0001-infisical-inyeccion-bind-mount-vs-imagen-derivada.md
# y docs/26-infisical-secretos.md.
#
# A propósito NO se ejecuta contra "all" salvo que se pida explícitamente:
# el binario solo hace falta en el nodo que aloja un servicio ya migrado a
# Infisical, no en los 6 de golpe (ver ADR 0001, motivo completo).
#
# Uso: bash deploy-infisical-cli.sh <nodo|all> [version]
# Nodos válidos: ryzen | retaco | pi-dns | pi-obs | pi-sonar | pi-utils | all
# version: por defecto la fijada más abajo (VERSION) — comprobar antes si
# conviene una más reciente en https://github.com/Infisical/cli/releases
#
# Tras desplegar un binario NUEVO en un nodo que ya tenía contenedores
# montándolo, hace falta RECREARLOS (no solo reiniciarlos) para que dejen de
# mirar al inodo antiguo: docker compose up -d --force-recreate <servicio>
# (mismo problema de inodo que los bind mounts de un solo fichero,
# docs/01-topologia.md).
#
# Ejecutar desde un equipo con acceso SSH a todos los nodos (p. ej. ryzen/mole).
# =============================================================================
set -euo pipefail

# Version del CLI a desplegar — confirmada en vivo contra
# https://github.com/Infisical/cli/releases al escribir este script. Revisar
# si conviene una más reciente antes de ejecutar en un despliegue nuevo.
VERSION="${2:-0.43.121}"

NODE="${1:-}"

if [ -z "${NODE}" ]; then
  echo "[ERROR] Uso: deploy-infisical-cli.sh <nodo|all> [version]"
  echo "        Nodos válidos: ryzen | retaco | pi-dns | pi-obs | pi-sonar | pi-utils | all"
  exit 1
fi

# nombre -> "usuario@ip" ("local" para el propio equipo donde corre este script)
declare -A TARGETS=(
  [ryzen]="local"
  [retaco]="u-data@192.168.1.174"
  [pi-dns]="u-dns@192.168.1.170"
  [pi-obs]="u-obs@192.168.1.171"
  [pi-sonar]="u-sonar@192.168.1.172"
  [pi-utils]="u-utils@192.168.1.173"
)

# Topología fija y conocida (docs/01-topologia.md) — no hace falta
# autodetectar arquitectura por nodo.
declare -A ARCH=(
  [ryzen]="amd64"
  [retaco]="amd64"
  [pi-dns]="arm64"
  [pi-obs]="arm64"
  [pi-sonar]="arm64"
  [pi-utils]="arm64"
)

deploy_node() {
  local name="$1"
  local target="${TARGETS[$name]}"
  local arch="${ARCH[$name]}"
  local url="https://github.com/Infisical/cli/releases/download/v${VERSION}/cli_${VERSION}_linux_${arch}.tar.gz"
  local dest_dir="/srv/homelab/${name}/infisical-cli"

  echo ""
  echo "=== ${name} (${arch}) — infisical v${VERSION} ==="

  # Descarga y extrae en local (en la máquina donde corre este script), y
  # solo entonces aterriza en el nodo destino — mismo patrón /tmp + sudo cp
  # que el resto del repo (docs/01-topologia.md, "Desplegar un fichero
  # cambiado a un nodo"), evita el problema de inodo de rsync/scp directo.
  local tmp_tgz
  tmp_tgz="$(mktemp)"
  curl -fsSL -o "${tmp_tgz}" "${url}"
  local tmp_dir
  tmp_dir="$(mktemp -d)"
  tar -xzf "${tmp_tgz}" -C "${tmp_dir}" infisical
  rm -f "${tmp_tgz}"
  chmod +x "${tmp_dir}/infisical"

  if [ "${target}" = "local" ]; then
    mkdir -p "${dest_dir}"
    cp "${tmp_dir}/infisical" "${dest_dir}/infisical"
  else
    scp "${tmp_dir}/infisical" "${target}:/tmp/infisical"
    ssh "${target}" "sudo mkdir -p '${dest_dir}' && sudo cp /tmp/infisical '${dest_dir}/infisical' && sudo chmod +x '${dest_dir}/infisical' && rm -f /tmp/infisical"
  fi
  rm -rf "${tmp_dir}"

  echo "[OK] ${name}: ${dest_dir}/infisical"
}

if [ "${NODE}" = "all" ]; then
  for n in ryzen retaco pi-obs pi-sonar pi-utils pi-dns; do
    deploy_node "${n}"
  done
elif [ -n "${TARGETS[${NODE}]+x}" ]; then
  deploy_node "${NODE}"
else
  echo "[ERROR] Nodo desconocido: '${NODE}'"
  echo "        Nodos válidos: ryzen | retaco | pi-dns | pi-obs | pi-sonar | pi-utils | all"
  exit 1
fi

echo ""
echo "[INFO] Binario desplegado. Si algún contenedor ya lo montaba por bind-mount de una versión anterior,"
echo "       recréalo (no solo reinicies) para que recoja el nuevo inodo: docker compose up -d --force-recreate <servicio>."
