#!/usr/bin/env bash
# =============================================================================
# deploy-infisical-cli.sh
# Descarga el binario oficial (release de GitHub, sin paquete de sistema ni
# repositorio apt/yum añadido) del CLI de Infisical y lo despliega en
# /srv/homelab/<nodo>/infisical-cli/infisical — NO en /usr/local/bin del
# sistema operativo. Los servicios PINNADOS a un nodo concreto lo montan por
# bind-mount (:ro) desde esa ruta e invocan desde `entrypoint:` en el
# docker-compose.yml de ese nodo — ver
# docs/adr/0001-infisical-inyeccion-bind-mount-vs-imagen-derivada.md y
# docs/26-infisical-secretos.md.
#
# Para servicios SIN `constraints` de nodo (pueden aterrizar en cualquiera de
# los 5 managers del Swarm), una ruta `/srv/homelab/<nodo>/...` no vale — un
# bind-mount no traduce entre arquitecturas, y `retaco`/`pinchi` (amd64) no
# tienen el mismo binario que `pi-obs`/`pi-sonar`/`pi-utils` (arm64). Para
# estos casos existe el modo `shared` (añadido 2026-08-31, primer consumidor:
# `authentik`): despliega en los 5 managers a
# `/srv/homelab/infisical/infisical-cli/<x86-64|aarch64>/infisical` +
# symlink `/srv/homelab/infisical/infisical-cli/infisical` apuntando al
# correcto según la arquitectura real de cada nodo — el docker-compose.yml
# del servicio monta siempre esa misma ruta symlink, sin cambiar nada según
# dónde aterrice la tarea.
#
# A propósito NO se ejecuta contra "all" salvo que se pida explícitamente:
# el binario solo hace falta en el nodo (o los 5 managers, en modo `shared`)
# que aloja un servicio ya migrado a Infisical, no en todos los nodos de
# golpe (ver ADR 0001, motivo completo).
#
# Uso: bash deploy-infisical-cli.sh <nodo|shared|all> [version]
# Nodos válidos: ryzen | retaco | pi-dns | pi-obs | pi-sonar | pi-utils | pinchi | shared | all
# version: por defecto la fijada más abajo (VERSION) — comprobar antes si
# conviene una más reciente en https://github.com/Infisical/cli/releases
#
# Tras desplegar un binario NUEVO en un nodo que ya tenía contenedores
# montándolo, hace falta RECREARLOS (no solo reiniciarlos) para que dejen de
# mirar al inodo antiguo: docker compose up -d --force-recreate <servicio>
# (mismo problema de inodo que los bind mounts de un solo fichero,
# docs/01-topologia.md). Esto incluye el modo `shared`: un servicio con
# bind-mount al symlink no nota el cambio de destino solo con recrear el
# symlink, el propio contenedor sigue con el inodo viejo montado.
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
  echo "[ERROR] Uso: deploy-infisical-cli.sh <nodo|shared|all> [version]"
  echo "        Nodos válidos: ryzen | retaco | pi-dns | pi-obs | pi-sonar | pi-utils | pinchi | shared | all"
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
  [pinchi]="u-forge@192.168.1.175"
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
  [pinchi]="amd64"
)

# Los 5 managers del Swarm -- son los únicos nodos donde tiene sentido el
# modo `shared` (ryzen/pi-dns están fuera del Swarm, docs/01-topologia.md).
SWARM_NODES=(retaco pi-obs pi-sonar pi-utils pinchi)

# ARCH usa "amd64"/"arm64" (convención de la release de GitHub); el modo
# `shared` nombra los subdirectorios "x86-64"/"aarch64" (más explícito para
# quien no conoce la convención de Go/GitHub releases de memoria).
arch_dirname() {
  case "$1" in
    amd64) echo "x86-64" ;;
    arm64) echo "aarch64" ;;
    *) echo "[ERROR] arquitectura desconocida: $1" >&2; exit 1 ;;
  esac
}

# Descarga y extrae el binario de una arquitectura dada a un directorio
# temporal local, devuelve la ruta del binario ya listo (+x). El llamador
# es responsable de limpiar el directorio temporal.
download_binary() {
  local arch="$1"
  local url="https://github.com/Infisical/cli/releases/download/v${VERSION}/cli_${VERSION}_linux_${arch}.tar.gz"
  local tmp_tgz tmp_dir
  tmp_tgz="$(mktemp)"
  curl -fsSL -o "${tmp_tgz}" "${url}"
  tmp_dir="$(mktemp -d)"
  tar -xzf "${tmp_tgz}" -C "${tmp_dir}" infisical
  rm -f "${tmp_tgz}"
  chmod +x "${tmp_dir}/infisical"
  echo "${tmp_dir}"
}

deploy_node() {
  local name="$1"
  local target="${TARGETS[$name]}"
  local arch="${ARCH[$name]}"
  local dest_dir="/srv/homelab/${name}/infisical-cli"

  echo ""
  echo "=== ${name} (${arch}) — infisical v${VERSION} ==="

  # Descarga y extrae en local (en la máquina donde corre este script), y
  # solo entonces aterriza en el nodo destino — mismo patrón /tmp + sudo cp
  # que el resto del repo (docs/01-topologia.md, "Desplegar un fichero
  # cambiado a un nodo"), evita el problema de inodo de rsync/scp directo.
  local tmp_dir
  tmp_dir="$(download_binary "${arch}")"

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

# Modo `shared`: despliega en los 5 managers del Swarm a
# /srv/homelab/infisical/infisical-cli/<x86-64|aarch64>/infisical + symlink
# .../infisical-cli/infisical -> el subdirectorio correcto según la
# arquitectura real de CADA nodo. Un docker-compose.yml de un servicio SIN
# `constraints` de nodo monta siempre esa ruta symlink -- funciona igual sea
# cual sea el manager donde Swarm aterrice la tarea.
deploy_shared() {
  local dest_root="/srv/homelab/infisical/infisical-cli"

  # Descargar cada arquitectura una sola vez, no una por nodo.
  declare -A tmp_by_arch=()
  for name in "${SWARM_NODES[@]}"; do
    local arch="${ARCH[$name]}"
    if [ -z "${tmp_by_arch[${arch}]+x}" ]; then
      echo ""
      echo "=== descargando infisical v${VERSION} (${arch}) para el modo shared ==="
      tmp_by_arch[${arch}]="$(download_binary "${arch}")"
    fi
  done

  for name in "${SWARM_NODES[@]}"; do
    local target="${TARGETS[$name]}"
    local arch="${ARCH[$name]}"
    local arch_dir
    arch_dir="$(arch_dirname "${arch}")"
    local dest_dir="${dest_root}/${arch_dir}"
    local tmp_dir="${tmp_by_arch[${arch}]}"

    echo ""
    echo "=== ${name} (${arch} -> ${arch_dir}) — infisical v${VERSION}, modo shared ==="

    if [ "${target}" = "local" ]; then
      mkdir -p "${dest_dir}"
      cp "${tmp_dir}/infisical" "${dest_dir}/infisical"
      ln -sfn "${arch_dir}/infisical" "${dest_root}/infisical"
    else
      scp "${tmp_dir}/infisical" "${target}:/tmp/infisical"
      ssh "${target}" "sudo mkdir -p '${dest_dir}' && sudo cp /tmp/infisical '${dest_dir}/infisical' && sudo chmod +x '${dest_dir}/infisical' && rm -f /tmp/infisical && cd '${dest_root}' && sudo ln -sfn '${arch_dir}/infisical' infisical"
    fi

    echo "[OK] ${name}: ${dest_dir}/infisical (symlink ${dest_root}/infisical -> ${arch_dir}/infisical)"
  done

  for tmp_dir in "${tmp_by_arch[@]}"; do
    rm -rf "${tmp_dir}"
  done
}

if [ "${NODE}" = "all" ]; then
  for n in ryzen retaco pi-obs pi-sonar pi-utils pi-dns pinchi; do
    deploy_node "${n}"
  done
elif [ "${NODE}" = "shared" ]; then
  deploy_shared
elif [ -n "${TARGETS[${NODE}]+x}" ]; then
  deploy_node "${NODE}"
else
  echo "[ERROR] Nodo desconocido: '${NODE}'"
  echo "        Nodos válidos: ryzen | retaco | pi-dns | pi-obs | pi-sonar | pi-utils | pinchi | shared | all"
  exit 1
fi

echo ""
echo "[INFO] Binario desplegado. Si algún contenedor ya lo montaba por bind-mount de una versión anterior,"
echo "       recréalo (no solo reinicies) para que recoja el nuevo inodo: docker compose up -d --force-recreate <servicio>."
