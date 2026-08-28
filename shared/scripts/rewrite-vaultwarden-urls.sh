#!/usr/bin/env bash
# =============================================================================
# rewrite-vaultwarden-urls.sh
# Busca y sustituye "*.home.arpa" por "*.404labo.net" en las URIs guardadas
# de los items de Vaultwarden (mejora 41, cierre 2026-08-28 -- home.arpa ya
# no resuelve en ningún sitio del clúster).
#
# NUNCA pide ni ve la contraseña maestra -- consume una sesión YA
# desbloqueada (variable BW_SESSION), que el usuario crea a mano en su
# propia terminal:
#
#   npm install -g @bitwarden/cli          # una sola vez, si no está instalado
#   bw config server https://vaultwarden.404labo.net
#   bw login <tu-email>                    # pide la contraseña maestra, interactivo
#   export BW_SESSION=$(bw unlock --raw)   # pide la contraseña maestra otra vez, interactivo
#   bash shared/scripts/rewrite-vaultwarden-urls.sh            # dry-run, no cambia nada
#   bash shared/scripts/rewrite-vaultwarden-urls.sh --apply    # aplica los cambios de verdad
#
# Al terminar: `bw lock` (o `bw logout`) para no dejar la sesión abierta.
#
# Tres hostnames se retiraron SIN gemelo en 404labo.net (mejora 41) -- una
# sustitución mecánica de texto los dejaría apuntando a un hostname que ya
# no resuelve, así que se tratan aparte, con su destino real:
#   - pihole.home.arpa   -> http://192.168.1.170:8053  (panel directo en la LAN, sin hostname)
#   - apikey.home.arpa   -> http://192.168.1.175:8091  (apikey-service del Swarm, admin directo)
#   - old.index.home.arpa -> sin sustituto (superseded por Capataz, mejora 15) -- se
#     AVISA pero no se reescribe solo, para que decidas a mano si el item sigue
#     haciendo falta o se borra.
#
# Requiere: bw (Bitwarden CLI) en PATH o accesible como `npx @bitwarden/cli`, jq.
# =============================================================================
set -euo pipefail

APPLY=false
if [ "${1:-}" = "--apply" ]; then
  APPLY=true
fi

if [ -z "${BW_SESSION:-}" ]; then
  echo "[ERROR] Falta BW_SESSION -- desbloquea la caja tú mismo primero:" >&2
  echo "        export BW_SESSION=\$(bw unlock --raw)" >&2
  exit 1
fi

BW_BIN="bw"
if ! command -v bw &>/dev/null; then
  BW_BIN="npx @bitwarden/cli"
fi

echo "[INFO] Sincronizando con el servidor..."
$BW_BIN sync --session "$BW_SESSION" >/dev/null

echo "[INFO] Buscando items con URIs bajo home.arpa..."
ITEMS_JSON=$($BW_BIN list items --session "$BW_SESSION")

MATCHES=$(echo "$ITEMS_JSON" | jq -c '[.[] | select(.login.uris? != null) | select(any(.login.uris[]; .uri // "" | test("home\\.arpa")))]')
COUNT=$(echo "$MATCHES" | jq 'length')

if [ "$COUNT" -eq 0 ]; then
  echo "[OK] Ningún item tiene URIs con home.arpa -- nada que hacer."
  exit 0
fi

echo "[INFO] ${COUNT} item(s) con al menos una URI en home.arpa:"
echo ""

# Filtro jq compartido: dado un item, calcula la URI reescrita para cada
# entrada de login.uris (misma regla en el dry-run y en el --apply, para que
# nunca puedan divergir entre sí).
REWRITE_FILTER='
  def rewritten:
    if test("pihole\\.home\\.arpa") then "http://192.168.1.170:8053"
    elif test("apikey\\.home\\.arpa") then "http://192.168.1.175:8091"
    elif test("old\\.index\\.home\\.arpa") then "__SIN_SUSTITUTO__"
    elif test("home\\.arpa") then gsub("home\\.arpa"; "404labo.net")
    else .
    end;
'

echo "$MATCHES" | jq -c '.[]' | while read -r item; do
  id=$(echo "$item" | jq -r '.id')
  name=$(echo "$item" | jq -r '.name')

  echo "--- ${name} (${id}) ---"
  echo "$item" | jq -r "${REWRITE_FILTER}"'
    .login.uris[]? | select((.uri // "") | test("home\\.arpa")) |
    "\(.uri)\t\(.uri | rewritten)"
  ' | while IFS=$'\t' read -r old_uri new_uri; do
    if [ "$new_uri" = "__SIN_SUSTITUTO__" ]; then
      echo "  ⚠️  ${old_uri}  -- old.index.home.arpa no tiene sustituto, revisar a mano (¿sigue haciendo falta este item?)"
    else
      echo "  ${old_uri}  ->  ${new_uri}"
    fi
  done
  echo ""

  if [ "$APPLY" = true ]; then
    # Igual que arriba, pero escribiendo el resultado en .uri (old.index.home.arpa
    # se deja intacto -- __SIN_SUSTITUTO__ es solo para el aviso de pantalla).
    updated=$(echo "$item" | jq "${REWRITE_FILTER}"'
      .login.uris |= map(
        if (.uri // "" | test("old\\.index\\.home\\.arpa")) then .
        elif (.uri // "" | test("home\\.arpa")) then (.uri |= rewritten)
        else .
        end
      )
    ')
    encoded=$(echo "$updated" | $BW_BIN encode)
    echo "$encoded" | $BW_BIN edit item "$id" --session "$BW_SESSION" >/dev/null
    echo "  [APLICADO]"
    echo ""
  fi
done

if [ "$APPLY" = false ]; then
  echo "[INFO] Dry-run -- no se ha cambiado nada. Vuelve a ejecutar con --apply para aplicar de verdad."
else
  echo "[OK] Cambios aplicados. Revisa en la web de Vaultwarden y considera 'bw lock' para cerrar la sesión."
fi
