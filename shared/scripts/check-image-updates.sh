#!/usr/bin/env bash
# =============================================================================
# check-image-updates.sh
# Comprueba, para cada contenedor en ejecución en el clúster que NO tiene la
# label "com.centurylinklabs.watchtower.enable=true" (es decir, todo lo que
# NO se auto-actualiza: postgres-main, n8n-main, qdrant, sonarqube,
# vaultwarden, portainer, n8n-aux, rsshub, markitdown-service, pihole,
# unbound, nginx, ollama, open-webui...), si el registro tiene una imagen
# más reciente para el MISMO tag que la que está corriendo.
#
# Escribe el resultado como métricas Prometheus (textfile collector) en
# /srv/homelab/pi-obs/node-exporter-textfile/image-updates.prom, leídas por
# el node-exporter de pi-obs y visibles en Grafana.
#
# Pensado para ejecutarse EN pi-obs (vía cron/systemd timer), con acceso SSH
# al resto de nodos. Ver docs/16-mantenimiento-actualizaciones.md.
#
# LIMITACIÓN CONOCIDA: compara el digest de la imagen para el MISMO tag
# (detecta que "n8nio/n8n:latest" se reconstruyó, o que "postgres:16-alpine"
# tiene un parche nuevo) — NO detecta que exista un tag de versión NUEVO
# para una imagen fijada a una versión exacta (p. ej. no avisa de que existe
# vaultwarden/server:1.37.0 mientras siga corriendo 1.36.0). Para esos casos
# sigue haciendo falta revisar manualmente el changelog del proyecto de vez
# en cuando. Tampoco cubre imágenes construidas localmente sin publicar a
# ningún registro (whisper-service) — esas se omiten silenciosamente.
# =============================================================================
set -uo pipefail

OUT_DIR="/srv/homelab/pi-obs/node-exporter-textfile"
OUT_FILE="${OUT_DIR}/image-updates.prom"
TMP_FILE=$(mktemp)

mkdir -p "${OUT_DIR}"

# nombre -> "usuario@ip" ("local" si este script corre en ese mismo nodo).
# Pensado para ejecutarse EN pi-obs — necesita su propia clave SSH autorizada
# en el resto de nodos (incluido ryzen, que no acepta SSH por defecto; hubo
# que instalar/activar openssh-server ahí expresamente para esto).
declare -A TARGETS=(
  [ryzen]="linus@192.168.1.150"
  [retaco]="u-data@192.168.1.174"
  [pi-dns]="u-dns@192.168.1.170"
  [pi-obs]="local"
  [pi-sonar]="u-sonar@192.168.1.172"
  [pi-utils]="u-utils@192.168.1.173"
)

# Script que se ejecuta EN cada nodo remoto: lista, para cada contenedor sin
# la label de watchtower, su nombre, su imagen (tal cual usada en el
# docker-compose, con tag) y el digest de la imagen local que tiene descargada.
REMOTE_SCRIPT='
for c in $(docker ps --format "{{.Names}}"); do
  label=$(docker inspect --format "{{index .Config.Labels \"com.centurylinklabs.watchtower.enable\"}}" "$c" 2>/dev/null)
  if [ "$label" = "true" ]; then
    continue
  fi
  image=$(docker inspect --format "{{.Config.Image}}" "$c" 2>/dev/null)
  localdigest=$(docker inspect --format "{{index .RepoDigests 0}}" "$c" 2>/dev/null | cut -d@ -f2)
  echo "${c}|${image}|${localdigest}"
done
'

{
  echo "# HELP docker_image_outdated 1 si hay una imagen nueva publicada para el mismo tag que el contenedor está usando, 0 si está al día, ausente si no se pudo comprobar."
  echo "# TYPE docker_image_outdated gauge"
} > "${TMP_FILE}"

for node in "${!TARGETS[@]}"; do
  target="${TARGETS[$node]}"
  echo "[INFO] Revisando ${node}..." >&2

  if [ "${target}" = "local" ]; then
    containers=$(bash -c "${REMOTE_SCRIPT}")
  else
    containers=$(ssh -o ConnectTimeout=8 "${target}" "${REMOTE_SCRIPT}" 2>/dev/null)
  fi

  if [ -z "${containers}" ]; then
    echo "[WARN] ${node}: sin datos (¿nodo inalcanzable?)" >&2
    continue
  fi

  while IFS='|' read -r container image localdigest; do
    [ -z "${container}" ] && continue

    # Pequeña pausa entre consultas al registro — Docker Hub anónimo limita
    # a 100 peticiones/6h por IP; con ~25 imágenes y una ejecución diaria no
    # debería acercarse al límite, pero conviene no ir a ráfaga.
    sleep 1

    remotedigest=$(docker buildx imagetools inspect "${image}" --format '{{json .Manifest}}' 2>/dev/null \
      | python3 -c "import sys,json; d=sys.stdin.read().strip(); print(json.loads(d).get('digest','') if d else '')" 2>/dev/null)

    if [ -z "${remotedigest}" ]; then
      # No se pudo consultar el registro (imagen local sin publicar, como
      # whisper-service; límite de peticiones anónimas de Docker Hub si se
      # ha ejecutado el script varias veces seguidas; o problema de red) —
      # se omite, no se reporta como 0 (falso "está al día").
      continue
    fi

    if [ -n "${localdigest}" ] && [ "${localdigest}" != "${remotedigest}" ]; then
      status=1
    else
      status=0
    fi

    echo "docker_image_outdated{node=\"${node}\",container=\"${container}\",image=\"${image}\"} ${status}" >> "${TMP_FILE}"
  done <<< "${containers}"
done

chmod 644 "${TMP_FILE}"
mv "${TMP_FILE}" "${OUT_FILE}"
echo "[OK] Escrito ${OUT_FILE}" >&2
grep -c "^docker_image_outdated" "${OUT_FILE}" | xargs echo "[INFO] Contenedores comprobados:" >&2
grep "} 1$" "${OUT_FILE}" | xargs -r -I{} echo "[INFO] Actualización disponible: {}" >&2

exit 0
