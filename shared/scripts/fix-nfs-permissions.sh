#!/usr/bin/env bash
# =============================================================================
# fix-nfs-permissions.sh
# Audita (y con --apply repara) los ficheros del NAS (`ketekasko`, montado en
# /mnt/nfs-data) que el usuario de su servicio no puede leer o recorrer. Es la
# avería que deja un apagado no limpio del NAS: al volver, parte de los
# ficheros de Forgejo, Capataz u Open WebUI aparecen con modo 0 y el servicio
# no arranca (`open .../app.ini: permission denied`). Pasó el 2026-10-13 y el
# 2026-10-15 (docs/31-docker-swarm.md).
#
# Ejecutar EN `retaco` (o en cualquier nodo con /mnt/nfs-data montado), como un
# usuario con `sudo` sin contraseña (admin). Por defecto SOLO AUDITA.
#
#   fix-nfs-permissions.sh                  # audita todos los directorios
#   fix-nfs-permissions.sh forgejo          # audita solo ese directorio
#   fix-nfs-permissions.sh --apply          # repara todos
#   fix-nfs-permissions.sh --apply forgejo  # repara solo ese
#
# Cómo decide: para cada directorio de primer nivel, el usuario del servicio es
# el UID que posee más ficheros (1000 Forgejo/n8n/Authentik/Capataz, 1001
# open-webui...). Prueba, con `sudo -u "#<uid>"`, qué NO puede leer o recorrer
# (`find ! -readable / ! -executable`), que es lo que de verdad importa: en este
# NAS el modo que reportan `stat`/`find -perm` no es fiable (el modo 0 coexiste
# con una ACL rwx), así que no se fía de eso. Ese mismo criterio no se puede
# aplicar a los que posee root (registry, komodo): no los toca.
#
# Qué hace con lo que encuentra (solo --apply):
#   directorios -> 0755 | claves (*.pem, rutas /ssh/) -> 0600 | resto -> 0644
# No cambia propietario, no toca lo que ya es accesible y no hace `chmod -R`.
# =============================================================================
set -uo pipefail

ROOT="${NFS_ROOT:-/mnt/nfs-data}"
APPLY=0
ONLY=()
for a in "$@"; do
  case "$a" in
    --apply) APPLY=1 ;;
    -h|--help) sed -n '2,/^# ====/p' "$0" | sed 's/^# \{0,1\}//' | head -n -1; exit 0 ;;
    -*) echo "[ERROR] opción desconocida: $a" >&2; exit 1 ;;
    *) ONLY+=("$a") ;;
  esac
done

[ -d "${ROOT}" ] || { echo "[ERROR] ${ROOT} no existe (¿NFS sin montar?)" >&2; exit 1; }
sudo -n true 2>/dev/null || { echo "[ERROR] hace falta sudo sin contraseña" >&2; exit 1; }

echo "Modo: $( [ "${APPLY}" -eq 1 ] && echo 'REPARAR' || echo 'AUDITAR (no cambia nada; usa --apply)' ) | raíz: ${ROOT}"

unreadable() { # $1 = directorio, $2 = uid
  sudo -u "#$2" find "$1" \( -type f ! -readable \) -o \( -type d ! -readable \) -o \( -type d ! -executable \) 2>/dev/null | sort -u
}

TOTAL=0
for d in $(sudo ls "${ROOT}"); do
  [ -d "${ROOT}/${d}" ] || continue
  case "${d}" in '#recycle'|'@'*|'.'*) continue ;; esac
  if [ ${#ONLY[@]} -gt 0 ]; then
    keep=0; for o in "${ONLY[@]}"; do [ "$o" = "$d" ] && keep=1; done
    [ "${keep}" -eq 1 ] || continue
  fi

  uid=$(sudo find "${ROOT}/${d}" -type f -printf '%U\n' 2>/dev/null | sort | uniq -c | sort -rn | head -1 | awk '{print $2}')
  [ -n "${uid}" ] || { echo "  ${d}: (sin ficheros)"; continue; }
  if [ "${uid}" = "0" ]; then echo "  ${d}: lo posee root, no se audita"; continue; fi

  list=$(unreadable "${ROOT}/${d}" "${uid}")
  n=$(printf '%s' "${list}" | grep -c . || true)
  if [ "${n}" -eq 0 ]; then echo "  ${d}: OK (uid ${uid})"; continue; fi

  TOTAL=$((TOTAL + n))
  echo "  ${d}: ${n} elementos que uid ${uid} no puede leer/recorrer"
  printf '%s\n' "${list}" | sed "s#^${ROOT}/#      #" | head -5
  [ "${n}" -gt 5 ] && echo "      ... y $((n - 5)) más"

  if [ "${APPLY}" -eq 1 ]; then
    while IFS= read -r p; do
      [ -n "$p" ] || continue
      if [ -d "$p" ]; then sudo chmod 0755 "$p"
      else case "$p" in *.pem|*/ssh/*) sudo chmod 0600 "$p" ;; *) sudo chmod 0644 "$p" ;; esac
      fi
    done <<< "${list}"
    resto=$(unreadable "${ROOT}/${d}" "${uid}" | grep -c . || true)
    echo "      -> reparado; quedan ${resto}"
    TOTAL=$((TOTAL - n + resto))
  fi
done

echo ""
if [ "${TOTAL}" -eq 0 ]; then echo "[OK] Nada pendiente."; exit 0; fi
if [ "${APPLY}" -eq 1 ]; then echo "[AVISO] Quedan ${TOTAL} elementos sin reparar."; exit 1; fi
echo "[AVISO] ${TOTAL} elementos con problema. Ejecuta con --apply para repararlos."
exit 1
