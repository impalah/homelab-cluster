#!/usr/bin/env bash
# =============================================================================
# switch-gpu1-backend.sh
# Alterna entre whisper-service y comfyui en la GPU 1 (RTX 3070, 8GB) — NUNCA
# deben correr a la vez, comparten tarjeta (ver docs/07-instalacion-ryzen.md).
# Independiente de switch-llm-backend.sh (GPU 0, ollama/vllm) — puedes tener
# p.ej. ollama + comfyui a la vez, o vllm + whisper-service, sin problema:
# cada script controla una GPU distinta.
#
# Uso: bash switch-gpu1-backend.sh whisper-service|comfyui
# =============================================================================
set -euo pipefail

TARGET="${1:?Uso: switch-gpu1-backend.sh whisper-service|comfyui}"
cd "$(dirname "$0")"

if [[ "$TARGET" != "whisper-service" && "$TARGET" != "comfyui" ]]; then
  echo "[ERROR] Backend inválido: '$TARGET'. Usa 'whisper-service' o 'comfyui'."
  exit 1
fi

if [ "$TARGET" = "whisper-service" ]; then
  OTHER="comfyui"
else
  OTHER="whisper-service"
fi

echo "[INFO] Parando '${OTHER}' (si está corriendo)..."
docker compose stop "${OTHER}"

# Margen fijo corto tras el stop, no comprobación por nvidia-smi — mismo
# razonamiento que switch-llm-backend.sh: no hay forma fiable de distinguir
# "memoria ya liberada" de "memoria de otro proceso ajeno" con un simple
# umbral, así que se confía en que "docker compose stop" ya ha esperado a
# que el proceso termine antes de devolver el control.
sleep 3

echo "[INFO] Arrancando '${TARGET}'..."
docker compose up -d "${TARGET}"

echo "[INFO] Esperando healthcheck de '${TARGET}'..."
STATUS="starting"
for i in $(seq 1 60); do
  STATUS=$(docker inspect --format='{{.State.Health.Status}}' "${TARGET}" 2>/dev/null || echo "starting")
  if [ "${STATUS}" = "healthy" ]; then
    break
  fi
  sleep 3
done

if [ "${STATUS}" != "healthy" ]; then
  echo "[WARN] '${TARGET}' no llegó a 'healthy' en el tiempo esperado."
  echo "       Revisa: docker compose logs ${TARGET}"
  exit 1
fi

echo "[OK] Backend activo en GPU 1: ${TARGET}"
docker compose ps whisper-service comfyui
