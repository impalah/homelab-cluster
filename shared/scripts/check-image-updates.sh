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
# /srv/homelab/node-exporter-textfile/image-updates.prom, leídas por el
# node-exporter de ESE MISMO nodo (stack `common`) y visibles en Grafana.
#
# Corre LOCALMENTE en cada nodo por cron, solo sobre sus propios contenedores
# -- igual que check-os-updates.sh. Hasta 2026-10-08 era un único job
# centralizado en pi-obs que entraba por SSH a los demás nodos; se descentralizó
# al retirar las Raspberry Pi del Swarm: no depende de ningún nodo concreto, no
# necesita claves SSH entre nodos (había que autorizar a mano la de pi-obs en
# cada uno) y un nodo caído solo deja sin refrescar su propio fichero.
# Requiere `docker login registry.404labo.net` del usuario que lo ejecuta (si
# no, las imágenes del registro privado se omiten sin avisar) y
# `docker buildx` + `python3`.
#
# Uso: bash check-image-updates.sh [nombre-del-nodo]
#   El nombre es el label `node` de las métricas; por defecto `hostname -s`.
#   ryzen hay que pasarlo explícito (su hostname es `mole`, el clúster lo
#   llama `ryzen`). Cron típico (minuto distinto por nodo, para no lanzar
#   todas las consultas anónimas a Docker Hub a la vez):
#     35 3 * * * bash /srv/homelab/shared/scripts/check-image-updates.sh ryzen
#
# Aviso opcional por ntfy (mejora 4, docs/22-mejoras-futuras.md/
# docs/34-ntfy-notificaciones.md): exportar NTFY_TOKEN (token de un usuario
# con permiso de escritura en el topic homelab-alerts) para que, además de
# las métricas, publique un push cuando encuentre algo desactualizado.
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

OUT_DIR="/srv/homelab/node-exporter-textfile"
OUT_FILE="${OUT_DIR}/image-updates.prom"
TMP_FILE=$(mktemp)
NODE="${1:-$(hostname -s)}"

if [ ! -d "${OUT_DIR}" ]; then
  echo "[ERROR] No existe ${OUT_DIR} -- ¿node-exporter de este nodo tiene montado el textfile collector? (mejora 36)" >&2
  exit 1
fi

# Lista, en este nodo, para cada contenedor sin
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

echo "[INFO] Revisando ${NODE}..." >&2
containers=$(bash -c "${REMOTE_SCRIPT}")

if [ -z "${containers}" ]; then
  echo "[WARN] ${NODE}: sin contenedores que comprobar" >&2
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

  echo "docker_image_outdated{node=\"${NODE}\",container=\"${container}\",image=\"${image}\"} ${status}" >> "${TMP_FILE}"
done <<< "${containers}"

chmod 644 "${TMP_FILE}"
mv "${TMP_FILE}" "${OUT_FILE}" || { echo "[ERROR] No se pudo escribir ${OUT_FILE} (¿permisos de ${OUT_DIR} para $(id -un)?)" >&2; exit 1; }
echo "[OK] Escrito ${OUT_FILE}" >&2
grep -c "^docker_image_outdated" "${OUT_FILE}" | xargs echo "[INFO] Contenedores comprobados:" >&2
outdated=$(grep "} 1$" "${OUT_FILE}")
echo "${outdated}" | xargs -r -I{} echo "[INFO] Actualización disponible: {}" >&2

# Punto 5 (opcional) de la mejora 4 (docs/22-mejoras-futuras.md): aviso por
# ntfy si hay algo desactualizado -- solo si NTFY_TOKEN está exportado (no
# hardcodeado aquí, mismo criterio que el resto de secretos del repo). Sin
# NTFY_TOKEN, el script sigue funcionando exactamente igual que antes de la
# mejora 4 (solo métricas, sin push) -- no bloqueante, `|| true` a propósito.
if [ -n "${outdated}" ] && [ -n "${NTFY_TOKEN:-}" ]; then
  count=$(echo "${outdated}" | wc -l)
  curl -fsS -H "Authorization: Bearer ${NTFY_TOKEN}" \
    -H "Title: Actualizaciones de imagen pendientes" \
    -H "Priority: default" \
    -H "Tags: whale" \
    -d "${count} contenedor(es) con imagen nueva publicada en el mismo tag -- ver panel de Grafana o ${OUT_FILE}." \
    https://ntfy.404labo.net/homelab-alerts >/dev/null \
    || echo "[WARN] No se pudo publicar el aviso en ntfy (¿token inválido o ntfy caído?)" >&2
fi

exit 0
