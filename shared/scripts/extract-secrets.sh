#!/usr/bin/env bash
# =============================================================================
# extract-secrets.sh
#
# Recovery tool for the 2026-09-29 Swarm advertise-address incident
# (docs/31-docker-swarm.md). For every Docker Swarm secret currently in use,
# finds a live container that has it mounted and reads its exact plaintext
# from /run/secrets/<target> -- the only way to read a Swarm secret's value,
# since the Swarm API itself never exposes it. Writes ONE file per real
# secret name (as `docker secret ls` shows it), so it can be fed straight
# into `docker secret create <name> <file>` later without anyone needing to
# retype or paste the value.
#
# Run this FROM THIS WORKSTATION (already has SSH access to every node).
# Claude does not read this output -- only file PATHS get referenced later,
# never the contents.
#
# Usage: bash extract-secrets.sh
# =============================================================================
set -o pipefail

OUTDIR="$HOME/homelab-secrets-backup-$(date +%Y%m%d-%H%M%S)"
SECDIR="$OUTDIR/secrets"
mkdir -p "$SECDIR"
chmod 700 "$OUTDIR" "$SECDIR"

echo "[INFO] Escribiendo en: $OUTDIR"
echo ""

declare -A NODES=(
  [retaco]="admin@192.168.10.7"
  [pinchi]="admin@192.168.10.8"
  [miugarita]="admin@192.168.10.9"
)

MANAGER="admin@192.168.10.7"

# --- 1. Construir el mapa: nombre real del secret -> (servicio, fichero destino) ---
echo "[INFO] Leyendo definición de servicios desde el manager..."
readarray -t services < <(ssh -o ConnectTimeout=6 "$MANAGER" "docker service ls --format '{{.Name}}'" 2>/dev/null </dev/null)

declare -A SECRET_TO_SERVICE=()
declare -A SECRET_TO_TARGET=()

for svc in "${services[@]}"; do
  [ -z "$svc" ] && continue
  json=$(ssh -o ConnectTimeout=6 "$MANAGER" \
    "docker service inspect '$svc' --format '{{json .Spec.TaskTemplate.ContainerSpec.Secrets}}'" 2>/dev/null </dev/null)
  [ -z "$json" ] && continue
  [ "$json" = "null" ] && continue

  readarray -t pairs < <(echo "$json" | python3 -c '
import json,sys
data = json.load(sys.stdin)
for s in (data or []):
    print(s["SecretName"] + "\t" + s["File"]["Name"])
' 2>/dev/null)

  for pair in "${pairs[@]}"; do
    [ -z "$pair" ] && continue
    sname="${pair%%$'\t'*}"
    tfile="${pair#*$'\t'}"
    [ -z "$sname" ] && continue
    SECRET_TO_SERVICE["$sname"]="$svc"
    SECRET_TO_TARGET["$sname"]="$tfile"
  done
done

echo "[INFO] Mapeados ${#SECRET_TO_SERVICE[@]} secrets a su servicio real."
echo ""

# --- 2. Para cada secret, localizar un contenedor vivo de ese servicio y leer el fichero ---
ok_count=0
declare -a missing=()

for sname in "${!SECRET_TO_SERVICE[@]}"; do
  svc="${SECRET_TO_SERVICE[$sname]}"
  tfile="${SECRET_TO_TARGET[$sname]}"

  task_node=$(ssh -o ConnectTimeout=6 "$MANAGER" \
    "docker service ps '$svc' --filter 'desired-state=running' --format '{{.Node}}'" 2>/dev/null </dev/null | head -1)

  if [ -z "$task_node" ] || [ -z "${NODES[$task_node]:-}" ]; then
    missing+=("$sname (servicio $svc sin tarea Running localizable)")
    continue
  fi

  target="${NODES[$task_node]}"
  cname=$(ssh -o ConnectTimeout=6 "$target" \
    "docker ps --filter 'name=${svc}' --format '{{.Names}}'" 2>/dev/null </dev/null | head -1)

  if [ -z "$cname" ]; then
    missing+=("$sname (servicio $svc: sin contenedor local en $task_node)")
    continue
  fi

  dest="$SECDIR/${sname}.secret"
  if ssh -o ConnectTimeout=6 "$target" \
      "docker exec '$cname' cat '/run/secrets/$tfile'" </dev/null > "$dest" 2>/dev/null && [ -s "$dest" ]; then
    chmod 600 "$dest"
    ok_count=$((ok_count + 1))
    echo "[OK] $sname  (<- $task_node/$cname:/run/secrets/$tfile)"
  else
    rm -f "$dest"
    missing+=("$sname (fallo leyendo $task_node/$cname:/run/secrets/$tfile)")
  fi
done

echo ""
echo "[INFO] Extraídos correctamente: $ok_count"
if [ "${#missing[@]}" -gt 0 ]; then
  echo "[WARN] No extraídos (servicio caído/sin tarea viva ahora mismo):"
  printf '  - %s\n' "${missing[@]}"
  printf '%s\n' "${missing[@]}" > "$OUTDIR/_no_extraidos.txt"
fi

# --- 3. Backup adicional de datos reales de Vaultwarden (no son secrets de Swarm) ---
echo ""
echo "[INFO] Backup adicional de datos de Vaultwarden..."
VW_TARGET="${NODES[pinchi]}"
if ssh -o ConnectTimeout=6 -o BatchMode=yes "$VW_TARGET" "echo ok" </dev/null >/dev/null 2>&1; then
  VW_BACKUP_NAME="vaultwarden-backup-$(date +%Y%m%d-%H%M%S).tar.gz"
  ssh -o ConnectTimeout=10 "$VW_TARGET" \
    "sudo tar -czf /srv/homelab/backups/pinchi/${VW_BACKUP_NAME} -C /srv/homelab/pinchi/vaultwarden data" </dev/null 2>&1
  echo "[OK] Backup de Vaultwarden: pinchi:/srv/homelab/backups/pinchi/${VW_BACKUP_NAME}"
else
  echo "[WARN] pinchi no accesible -- backup adicional de Vaultwarden omitido."
fi

echo ""
echo "[DONE] Secrets en: $SECDIR  (un fichero por nombre real de secret, listo para 'docker secret create <nombre> <fichero>')"
echo "[DONE] Permisos 700/600 en todo el árbol."
echo "[DONE] Avisa cuando esté listo. Si faltan secrets de servicios caídos, dime cuáles son importantes y los recuperamos aparte."
