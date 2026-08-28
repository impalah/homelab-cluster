#!/usr/bin/env bash
# =============================================================================
# deploy-traefik-cert.sh
# Rota el docker secret de Swarm con el certificado/clave real de
# *.404labo.net en Traefik, disparado como --reloadcmd de acme.sh tras cada
# renovación real (shared/scripts/renew-letsencrypt.sh, cron en pi-dns) --
# mejora 41 (2026-08-28), cierra el hueco de rotación manual documentado en
# docs/31-docker-swarm.md fase 3b.
#
# Los secrets de Swarm son inmutables: no se puede "actualizar" uno en sitio,
# hay que crear una versión nueva (-vN+1) y mover el servicio de Traefik
# (docker-swarm/stacks/traefik/, `mode: global`) a referenciarla con
# `docker service update` -- un solo comando cubre las 5 réplicas (una por
# nodo manager) sin necesitar `docker stack deploy`. La versión que queda
# en docker-swarm/stacks/traefik/docker-compose.yml (git) puede quedarse
# desincronizada del número real tras una rotación automática -- se
# actualiza a mano la próxima vez que ese fichero se toque por otro motivo,
# igual que ya pasa con otros secrets de este repo.
#
# pi-dns está deliberadamente FUERA del Swarm (docs/31) -- este script se
# ejecuta ahí pero opera sobre un nodo manager (retaco) por SSH, con una
# clave dedicada de un solo propósito (u-dns -> u-data@retaco, ver mejora 41
# en docs/22-mejoras-futuras.md) que NO da acceso a nada más. El contenido
# del certificado/clave se manda por pipe SSH directo (cat | ssh ... docker
# secret create -), nunca toca disco en retaco.
#
# Uso: deploy-traefik-cert.sh (sin argumentos -- rutas fijas, coherentes con
# renew-letsencrypt.sh: CERT_HOME=/srv/homelab/pi-dns/acme.sh/certs).
# =============================================================================
set -euo pipefail

CERT_DIR=/srv/homelab/pi-dns/acme.sh/certs/404labo.net_ecc
FULLCHAIN="${CERT_DIR}/fullchain.cer"
KEY="${CERT_DIR}/404labo.net.key"

RETACO_HOST=u-data@192.168.1.174
RETACO_SSH_KEY=/home/u-dns/.ssh/id_ed25519_retaco_certs
SWARM_SERVICE=traefik_traefik
SECRET_BASENAME=404labo-net

ssh_retaco() {
  ssh -i "${RETACO_SSH_KEY}" -o BatchMode=yes "${RETACO_HOST}" "$@"
}

if [ ! -r "${FULLCHAIN}" ] || [ ! -r "${KEY}" ]; then
  echo "deploy-traefik-cert.sh: no se puede leer ${FULLCHAIN} o ${KEY}" >&2
  exit 1
fi

# Versión actualmente en uso por el servicio -- de ahí sacamos N, la nueva
# es N+1. No asumimos "v1": una rotación previa pudo haber dejado el
# servicio en cualquier versión.
CURRENT_CRT_SECRET=$(ssh_retaco "docker service inspect ${SWARM_SERVICE} \
  --format '{{range .Spec.TaskTemplate.ContainerSpec.Secrets}}{{.SecretName}} {{end}}'" \
  | tr ' ' '\n' | grep "^${SECRET_BASENAME}-crt-v" || true)

if [ -z "${CURRENT_CRT_SECRET}" ]; then
  echo "deploy-traefik-cert.sh: no se encontró un secret ${SECRET_BASENAME}-crt-vN en ${SWARM_SERVICE}" >&2
  exit 1
fi

CURRENT_VERSION=$(echo "${CURRENT_CRT_SECRET}" | grep -oP "${SECRET_BASENAME}-crt-v\K[0-9]+")
NEXT_VERSION=$((CURRENT_VERSION + 1))

NEW_CRT_SECRET="${SECRET_BASENAME}-crt-v${NEXT_VERSION}"
NEW_KEY_SECRET="${SECRET_BASENAME}-key-v${NEXT_VERSION}"
OLD_CRT_SECRET="${SECRET_BASENAME}-crt-v${CURRENT_VERSION}"
OLD_KEY_SECRET="${SECRET_BASENAME}-key-v${CURRENT_VERSION}"

echo "deploy-traefik-cert.sh: rotando ${OLD_CRT_SECRET}/${OLD_KEY_SECRET} -> ${NEW_CRT_SECRET}/${NEW_KEY_SECRET}"

cat "${FULLCHAIN}" | ssh_retaco "docker secret create ${NEW_CRT_SECRET} -"
cat "${KEY}" | ssh_retaco "docker secret create ${NEW_KEY_SECRET} -"

ssh_retaco "docker service update \
  --secret-rm ${OLD_CRT_SECRET} \
  --secret-add source=${NEW_CRT_SECRET},target=404labo-net.crt \
  --secret-rm ${OLD_KEY_SECRET} \
  --secret-add source=${NEW_KEY_SECRET},target=404labo-net.key \
  ${SWARM_SERVICE}"

# Solo se retira la versión anterior si el update anterior no ha fallado
# (set -e ya habría cortado antes) -- deja como mucho 1 versión vieja huérfana
# si algo falla a media rotación, nunca acumula sin límite.
ssh_retaco "docker secret rm ${OLD_CRT_SECRET} ${OLD_KEY_SECRET}" || \
  echo "deploy-traefik-cert.sh: aviso -- no se pudo borrar ${OLD_CRT_SECRET}/${OLD_KEY_SECRET} (¿todavía en uso por una tarea antigua?)" >&2

echo "deploy-traefik-cert.sh: ${SWARM_SERVICE} actualizado a ${NEW_CRT_SECRET}/${NEW_KEY_SECRET}"
