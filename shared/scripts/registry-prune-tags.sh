#!/usr/bin/env bash
# =============================================================================
# registry-prune-tags.sh
# Política de retención de tags para registry.home.arpa — mejora 8 de
# docs/22-mejoras-futuras.md ("Registry — limpieza y garbage collection").
#
# Por cada repositorio (imagen), conserva SIEMPRE "latest" más las KEEP
# versiones más recientes (por orden de versión semántica del propio tag,
# p. ej. "0.3.0" > "0.2.1" > "0.1.0"), y borra el MANIFEST (no el blob en
# sí — eso lo hace registry-garbage-collect.sh después) de cualquier tag
# de versión más antiguo. KEEP=3 por defecto — política acordada: 3
# versiones antiguas por imagen, además de "latest".
#
# SOLO EJECUCIÓN MANUAL A PROPÓSITO, mismo motivo que
# registry-garbage-collect.sh: borrar el tag equivocado en un registry con
# pocas imágenes es más caro de deshacer que revisar un dry-run a mano.
#
# Este script SOLO desreferencia tags (llamada DELETE a la API v2) — no
# libera espacio en disco por sí solo. Para recuperar el espacio de verdad,
# ejecutar después registry-garbage-collect.sh.
#
# Requiere credenciales del registry (usuario compartido, ver
# docs/05-instalacion-retaco.md sección 5.3 y Vaultwarden "Docker Registry
# (registry.home.arpa)") vía variables de entorno — NUNCA hardcodeadas:
#   REGISTRY_USER=admin REGISTRY_PASSWORD=xxx bash registry-prune-tags.sh
#
# Uso:
#   REGISTRY_USER=... REGISTRY_PASSWORD=... bash registry-prune-tags.sh [--dry-run|--apply] [KEEP]
# Por defecto: modo=--dry-run, KEEP=3
#
# Requiere: curl, jq.
# =============================================================================
set -euo pipefail

REGISTRY_URL="${REGISTRY_URL:-https://registry.home.arpa}"
REGISTRY_USER="${REGISTRY_USER:?Debes exportar REGISTRY_USER}"
REGISTRY_PASSWORD="${REGISTRY_PASSWORD:?Debes exportar REGISTRY_PASSWORD}"

MODE="${1:---dry-run}"
KEEP="${2:-3}"

if [ "${MODE}" != "--dry-run" ] && [ "${MODE}" != "--apply" ]; then
  echo "[ERROR] Uso: REGISTRY_USER=... REGISTRY_PASSWORD=... bash registry-prune-tags.sh [--dry-run|--apply] [KEEP]"
  exit 1
fi

# Acepta application/vnd.docker.distribution.manifest.v2+json (imagen de una
# sola plataforma) Y application/vnd.oci.image.index.v1+json /
# application/vnd.docker.distribution.manifest.list.v2+json (manifest list
# multi-arch, como apikey-service/markitdown-service/capataz-*) — sin este
# segundo Accept, el registry devuelve el manifest v1 legado (sin
# Docker-Content-Digest fiable) para las imágenes multi-arch.
MANIFEST_ACCEPT=(
  -H "Accept: application/vnd.docker.distribution.manifest.v2+json"
  -H "Accept: application/vnd.docker.distribution.manifest.list.v2+json"
  -H "Accept: application/vnd.oci.image.index.v1+json"
)

resolve_digest() {
  local repo="$1" ref="$2"
  curl -fsS -u "${REGISTRY_USER}:${REGISTRY_PASSWORD}" -I "${MANIFEST_ACCEPT[@]}" \
    "${REGISTRY_URL}/v2/${repo}/manifests/${ref}" 2>/dev/null \
    | grep -i '^docker-content-digest:' | tr -d '\r' | awk '{print $2}'
}

echo "[INFO] Repositorios en ${REGISTRY_URL}..."
REPOS=$(curl -fsS -u "${REGISTRY_USER}:${REGISTRY_PASSWORD}" "${REGISTRY_URL}/v2/_catalog?n=1000" | jq -r '.repositories[]')

TOTAL_PRUNED=0

for REPO in ${REPOS}; do
  echo ""
  echo "=== ${REPO} ==="

  TAGS=$(curl -fsS -u "${REGISTRY_USER}:${REGISTRY_PASSWORD}" "${REGISTRY_URL}/v2/${REPO}/tags/list?n=1000" \
    | jq -r '.tags[]? // empty' | grep -v '^latest$' || true)

  if [ -z "${TAGS}" ]; then
    echo "  (sin tags de versión, solo 'latest' o ninguno) — nada que podar"
    continue
  fi

  # sort -V: orden de versión (natural), -r: descendente (más reciente primero)
  SORTED=$(printf '%s\n' "${TAGS}" | sort -Vr)
  KEEP_TAGS=$(printf '%s\n' "${SORTED}" | head -n "${KEEP}")
  PRUNE_TAGS=$(printf '%s\n' "${SORTED}" | tail -n "+$((KEEP + 1))")

  echo "  Conservar: latest, $(printf '%s' "${KEEP_TAGS}" | tr '\n' ' ')"

  if [ -z "${PRUNE_TAGS}" ]; then
    echo "  Nada que podar (${KEEP} o menos versiones antiguas en total)."
    continue
  fi

  LATEST_DIGEST=$(resolve_digest "${REPO}" "latest" || true)

  for TAG in ${PRUNE_TAGS}; do
    DIGEST=$(resolve_digest "${REPO}" "${TAG}" || true)

    if [ -z "${DIGEST}" ]; then
      echo "  [WARN] No se pudo resolver el digest de ${REPO}:${TAG} — se salta"
      continue
    fi

    if [ -n "${LATEST_DIGEST}" ] && [ "${DIGEST}" = "${LATEST_DIGEST}" ]; then
      echo "  [SKIP] ${TAG} — mismo digest que 'latest', nunca se borra"
      continue
    fi

    if [ "${MODE}" = "--dry-run" ]; then
      echo "  [DRY-RUN] Se borraría ${REPO}:${TAG} (${DIGEST})"
    else
      HTTP_CODE=$(curl -fsS -u "${REGISTRY_USER}:${REGISTRY_PASSWORD}" -X DELETE \
        -o /dev/null -w '%{http_code}' \
        "${REGISTRY_URL}/v2/${REPO}/manifests/${DIGEST}")
      echo "  [DELETE] ${REPO}:${TAG} -> HTTP ${HTTP_CODE}"
    fi
    TOTAL_PRUNED=$((TOTAL_PRUNED + 1))
  done
done

echo ""
if [ "${MODE}" = "--dry-run" ]; then
  echo "[INFO] Dry-run completado — ${TOTAL_PRUNED} tag(s) se borrarían. Para aplicar de verdad:"
  echo "         REGISTRY_USER=... REGISTRY_PASSWORD=... bash registry-prune-tags.sh --apply ${KEEP}"
else
  echo "[OK] ${TOTAL_PRUNED} tag(s) podados. Los blobs siguen en disco hasta ejecutar:"
  echo "       bash registry-garbage-collect.sh retaco registry --apply"
fi
