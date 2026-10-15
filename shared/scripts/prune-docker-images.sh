#!/usr/bin/env bash
# =============================================================================
# prune-docker-images.sh
# Limpieza de imágenes de Docker antiguas y sin uso, en todos los nodos del
# clúster o en el nodo local. Pensado para liberar disco sin tocar nada que
# esté en uso ni ningún dato.
#
# POR DEFECTO ES UNA SIMULACIÓN: solo lista qué se borraría y cuánto espacio
# liberaría. Para borrar de verdad hay que pasar --apply.
#
# Qué se considera borrable (todo a la vez):
#   - imágenes que NINGÚN contenedor (en marcha o parado) usa en ese nodo, y
#   - creadas hace más de --keep-days días (por defecto 7). El margen es lo que
#     permite un `docker service rollback` o volver a la versión anterior de un
#     stack sin tener que descargarla de nuevo.
# Además, con --apply: contenedores parados y caché de build, con el mismo
# margen de antigüedad.
#
# Lo que NUNCA toca: volúmenes (ahí están los datos), redes, imágenes en uso,
# ni las imágenes PROTEGIDAS (las de dev containers de VS Code, `vsc-*`, y
# cualquier repositorio que un docker-compose.yml de
# /srv/homelab/<nodo>/ declare con `image:` (aunque ahora no tenga contenedor,
# como vLLM/ComfyUI en ryzen, que se alternan con ollama/whisper), más los que
# se listen en /srv/homelab/shared/config/prune-keep.txt (uno por línea) o en la
# variable PRUNE_KEEP, separados por comas).
#
# Uso:
#   prune-docker-images.sh                          # simula en TODOS los nodos
#   prune-docker-images.sh retaco pinchi            # simula solo en esos nodos
#   prune-docker-images.sh --apply                  # borra en todos los nodos
#   prune-docker-images.sh --keep-days 14 --apply   # margen distinto
#   prune-docker-images.sh --local --apply          # solo este equipo, sin SSH
#
# Opciones:
#   --apply          ejecuta la limpieza (sin esto, solo simula)
#   --keep-days N    margen de antigüedad en días (por defecto 7)
#   --local          actúa sobre ESTE equipo, sin SSH (para cron en cada nodo)
#   -h, --help       esta ayuda
#
# Modo clúster: se ejecuta desde un puesto con acceso SSH como `admin` a los
# nodos (ssh-node.sh / ~/.ssh/config, docs/38) y se envía a sí mismo a cada uno
# con --local; no hace falta que el script esté copiado en los nodos.
#
# Cron en un nodo (más adelante, cuando se decida automatizar):
#   0 4 * * 0 /usr/bin/bash /srv/homelab/shared/scripts/prune-docker-images.sh --local --apply >> /var/log/homelab-docker-prune.log 2>&1
#
# Avisos conocidos:
#   - Una imagen solo la usa un contenedor que EXISTA: un servicio de Swarm
#     escalado a 0 o un stack retirado deja su imagen "sin uso" y se borra pasado
#     el margen; al volver a desplegarlo se descarga otra vez (desde el registro
#     propio en retaco, o de internet). Si ese registro está caído, no hay de
#     dónde bajarla -- por eso conviene no usar un margen demasiado corto.
#   - Los stacks de Swarm no se guardan en el nodo (se despliegan desde /tmp),
#     así que sus imágenes NO se detectan como protegidas: solo cuenta que haya
#     un contenedor que las use. Para fijar una imagen de Swarm, añadirla a
#     prune-keep.txt o a PRUNE_KEEP.
# =============================================================================
set -uo pipefail

# Nodos del clúster y su IP (ver docs/02-plan-ip-y-dns.md). El usuario es
# siempre `admin` (docs/38-acceso-ssh-nodos.md).
declare -A NODE_IPS=(
  [pi-dns]="192.168.10.2"
  [pi-dns2]="192.168.10.3"
  [pi-obs]="192.168.10.4"
  [pi-sonar]="192.168.10.5"
  [retaco]="192.168.10.7"
  [pinchi]="192.168.10.8"
  [miugarita]="192.168.10.9"
  [ryzen]="192.168.10.10"
)
ALL_NODES=(retaco pinchi miugarita ryzen pi-dns pi-obs pi-sonar pi-dns2)

APPLY=0
KEEP_DAYS=7
LOCAL=0
TARGETS=()

usage() { sed -n '2,/^# =====/p' "$0" | sed 's/^# \{0,1\}//' | head -n -1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --apply) APPLY=1 ;;
    --local) LOCAL=1 ;;
    --keep-days) KEEP_DAYS="${2:-}"; shift ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "[ERROR] Opción desconocida: $1" >&2; exit 1 ;;
    *) TARGETS+=("$1") ;;
  esac
  shift
done

case "${KEEP_DAYS}" in
  ''|*[!0-9]*) echo "[ERROR] --keep-days necesita un número entero de días" >&2; exit 1 ;;
esac

human() { numfmt --to=iec --suffix=B "$1" 2>/dev/null || echo "$1 B"; }

# -----------------------------------------------------------------------------
# Modo local: lo que hace de verdad en un nodo.
# -----------------------------------------------------------------------------
run_local() {
  command -v docker >/dev/null || { echo "[ERROR] docker no está instalado aquí"; return 1; }
  docker info >/dev/null 2>&1 || { echo "[ERROR] sin acceso a docker (¿grupo docker?)"; return 1; }

  # Un solo limpiador a la vez en este nodo.
  # (fichero por usuario: en ryzen lo ejecutan linus y admin, y no deben pisarse)
  local lock="/tmp/prune-docker-images.$(id -un).lock"
  exec 9>"${lock}" || { echo "[ERROR] no se puede crear ${lock}"; return 1; }
  flock -n 9 || { echo "[AVISO] ya hay otra limpieza en curso en este nodo, se omite"; return 0; }

  # --- Imágenes PROTEGIDAS: repositorios que algún docker-compose.yml de este
  # nodo declara (aunque ahora no tengan contenedor) + lista manual opcional.
  # Es lo que evita borrar, p. ej., la imagen de vLLM o ComfyUI en ryzen, que se
  # alternan con ollama/whisper (ryzen/switch-*.sh) y pesan decenas de GB.
  local keep_file="/srv/homelab/shared/config/prune-keep.txt" keep
  keep=$( { grep -hE '^\s*image:' /srv/homelab/*/docker-compose*.yml /srv/homelab/*/*/docker-compose*.yml 2>/dev/null \
              | sed -E 's/^\s*image:\s*//; s/["'"'"']//g; s/\s+#.*$//; s/\s+$//'
            [ -r "${keep_file}" ] && grep -vE '^\s*(#|$)' "${keep_file}"
            [ -n "${PRUNE_KEEP:-}" ] && tr ',' '\n' <<<"${PRUNE_KEEP}"
          } | grep -v '\$' | sed -E 's/@sha256:.*$//; s/:[A-Za-z0-9._-]+$//' | sort -u )

  local cutoff used candidates="" ids="" total=0 count=0 prot=0 prot_size=0 id created size tags t repo protected
  cutoff=$(date -d "-${KEEP_DAYS} days" +%s)
  used=$(docker ps -a -q | xargs -r docker inspect --format '{{.Image}}' 2>/dev/null | sort -u)

  while read -r id; do
    [ -n "${id}" ] || continue
    if grep -qxF "${id}" <<<"${used}"; then continue; fi
    created=$(date -d "$(docker image inspect -f '{{.Created}}' "${id}" 2>/dev/null)" +%s 2>/dev/null) || continue
    [ "${created}" -lt "${cutoff}" ] || continue
    size=$(docker image inspect -f '{{.Size}}' "${id}")
    tags=$(docker image inspect -f '{{join .RepoTags ","}}' "${id}")

    protected=0
    for t in ${tags//,/ }; do
      repo="${t%:*}"
      if grep -qxF "${repo}" <<<"${keep}"; then protected=1; break; fi
      # Imágenes de dev containers de VS Code (puesto de trabajo, ryzen):
      # reconstruirlas es lento y no son del clúster.
      case "${repo}" in vsc-*) protected=1; break ;; esac
    done
    if [ "${protected}" -eq 1 ]; then
      prot=$((prot + 1)); prot_size=$((prot_size + size)); continue
    fi

    total=$((total + size)); count=$((count + 1)); ids+="${id} "
    candidates+=$(printf '%s\t%s\t%s' "$(human "${size}")" "$(date -d "@${created}" +%F)" "${tags:-<sin etiqueta>}")$'\n'
  done < <(docker image ls -a --no-trunc --format '{{.ID}}' | sort -u)

  local free_before
  free_before=$(df -B1 --output=avail /var/lib/docker 2>/dev/null | tail -1 | tr -d ' ')

  echo "imágenes a borrar (sin uso, > ${KEEP_DAYS} días, no declaradas en ningún compose): ${count} (~$(human "${total}"))"
  if [ -n "${candidates}" ]; then
    printf '%s' "${candidates}" | sort -hr | head -15 | sed 's/^/    /'
    [ "${count}" -gt 15 ] && echo "    ... y $((count - 15)) más"
  fi
  echo "protegidas por estar declaradas en un compose de este nodo: ${prot} (~$(human "${prot_size}"), no se tocan)"

  if [ "${APPLY}" -ne 1 ]; then
    echo "(simulación: no se ha borrado nada; usa --apply para ejecutar)"
    return 0
  fi

  local until="$((KEEP_DAYS * 24))h"
  echo "-- borrando..."
  docker container prune -f --filter "until=${until}" </dev/null 2>&1 | grep -E 'Total reclaimed' | sed 's/^/    contenedores parados: /'
  # Borrado explícito por ID (no `image prune -a`, que ignoraría las protegidas).
  # `rmi` rechaza una imagen en uso; el filtro de arriba ya la había descartado.
  local ok=0 fail=0
  for id in ${ids}; do
    if docker rmi -f "${id}" </dev/null >/dev/null 2>&1; then ok=$((ok + 1)); else fail=$((fail + 1)); fi
  done
  echo "    imágenes borradas: ${ok}$( [ "${fail}" -gt 0 ] && echo " (${fail} no se pudieron borrar)" )"
  docker image prune -f --filter "until=${until}" </dev/null 2>&1 | grep -E 'Total reclaimed' | sed 's/^/    capas huérfanas: /'
  docker builder prune -f --filter "until=${until}" </dev/null 2>&1 | grep -E 'Total' | sed 's/^/    caché de build: /'
  local free_after
  free_after=$(df -B1 --output=avail /var/lib/docker 2>/dev/null | tail -1 | tr -d ' ')
  echo "    libre en disco: $(human "${free_before}") -> $(human "${free_after}")"
}

if [ "${LOCAL}" -eq 1 ]; then
  echo "[$(hostname -s)] $( [ "${APPLY}" -eq 1 ] && echo APLICANDO || echo SIMULACIÓN ) (margen ${KEEP_DAYS} días)"
  run_local
  exit $?
fi

# -----------------------------------------------------------------------------
# Modo clúster: se reenvía a sí mismo a cada nodo por SSH con --local.
# -----------------------------------------------------------------------------
[ ${#TARGETS[@]} -gt 0 ] || TARGETS=("${ALL_NODES[@]}")

for n in "${TARGETS[@]}"; do
  [ -n "${NODE_IPS[$n]:-}" ] || { echo "[ERROR] Nodo desconocido: ${n} (válidos: ${ALL_NODES[*]})" >&2; exit 1; }
done

ARGS=(--local --keep-days "${KEEP_DAYS}")
[ "${APPLY}" -eq 1 ] && ARGS+=(--apply)

echo "Modo: $( [ "${APPLY}" -eq 1 ] && echo 'APLICAR (borra de verdad)' || echo 'SIMULACIÓN (no borra nada)' ) | margen: ${KEEP_DAYS} días | nodos: ${TARGETS[*]}"
FAILED=()
for n in "${TARGETS[@]}"; do
  echo ""
  echo "=== ${n} (${NODE_IPS[$n]}) ==="
  # El script viaja por la entrada estándar de `bash -s`; la salida se recoge
  # entera para poder indentarla y conservar el código de salida de ssh.
  out=$(ssh -o BatchMode=yes -o ConnectTimeout=8 "admin@${NODE_IPS[$n]}" "bash -s -- ${ARGS[*]}" < "$0" 2>&1)
  rc=$?
  printf '%s\n' "${out}" | sed 's/^/  /'
  [ "${rc}" -eq 0 ] || FAILED+=("${n}")
done

echo ""
if [ ${#FAILED[@]} -gt 0 ]; then
  echo "[AVISO] Fallaron o no respondieron: ${FAILED[*]}"
  exit 1
fi
echo "[OK] Terminado en ${#TARGETS[@]} nodo(s)."
