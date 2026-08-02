#!/usr/bin/env bash
# =============================================================================
# switch-llm-backend.sh
# Alterna entre ollama y vllm en este nodo — NUNCA deben correr a la vez,
# compiten por la misma VRAM (ver docs/07-instalacion-ryzen.md). Para el backend
# que no se pide, espera a que la GPU 0 libere memoria y arranca el pedido.
#
# Uso: bash switch-llm-backend.sh ollama|vllm
# Ejecutar desde /srv/homelab/ryzen (o pasar la ruta como único argumento
# adicional no es necesario: el script se sitúa solo en su propio directorio)
# =============================================================================
set -euo pipefail

TARGET="${1:?Uso: switch-llm-backend.sh ollama|vllm}"
cd "$(dirname "$0")"

if [[ "$TARGET" != "ollama" && "$TARGET" != "vllm" ]]; then
  echo "[ERROR] Backend inválido: '$TARGET'. Usa 'ollama' o 'vllm'."
  exit 1
fi

if [ "$TARGET" = "ollama" ]; then
  OTHER="vllm"
else
  OTHER="ollama"
fi

echo "[INFO] Parando '${OTHER}' (si está corriendo)..."
docker compose stop "${OTHER}"

# "docker compose stop" no devuelve el control hasta que el contenedor ha
# terminado, pero el driver NVIDIA puede tardar un instante extra en liberar
# el contexto CUDA tras la salida del proceso. No se comprueba con
# "nvidia-smi" (whisper-service también reserva GPU 0 permanentemente
# mientras está arriba, así que la memoria libre nunca bajaría de un umbral
# fijo aunque ollama/vllm sí hayan soltado la suya) — un margen fijo corto
# es suficiente y no da falsos avisos.
sleep 3

echo "[INFO] Arrancando '${TARGET}'..."
docker compose up -d "${TARGET}"

echo "[INFO] Esperando healthcheck de '${TARGET}'..."
STATUS="starting"
for i in $(seq 1 90); do
  STATUS=$(docker inspect --format='{{.State.Health.Status}}' "${TARGET}" 2>/dev/null || echo "starting")
  if [ "${STATUS}" = "healthy" ]; then
    break
  fi
  sleep 2
done

if [ "${STATUS}" != "healthy" ]; then
  echo "[WARN] '${TARGET}' no llegó a 'healthy' en el tiempo esperado."
  echo "       Revisa: docker compose logs ${TARGET}"
  exit 1
fi

echo "[OK] Backend activo: ${TARGET}"
docker compose ps ollama vllm
