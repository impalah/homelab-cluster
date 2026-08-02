FROM nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3-pip \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Instalar uv para gestión de dependencias
RUN pip3 install --no-cache-dir uv

WORKDIR /app

# Copiar archivos de proyecto
COPY pyproject.toml .
COPY src/ ./src/

# Instalar dependencias con uv — "python3" en esta imagen sigue siendo la
# versión por defecto de Ubuntu 22.04 (3.10), no la 3.11 instalada arriba;
# hay que apuntar explícitamente a python3.11, que es lo que pyproject.toml exige.
RUN uv pip install --system --python python3.11 --no-cache .

# Exponer puerto
# 9800 a propósito, no 8000: 8000 es el puerto por defecto de innumerables
# servicios FastAPI/dev — se cambió para evitar colisiones/confusión.
EXPOSE 9800

# Variables de entorno por defecto (sobreescribibles vía docker-compose .env)
ENV WHISPER_MODEL=large-v3
ENV WHISPER_DEVICE=cuda
ENV WHISPER_COMPUTE_TYPE=float16
ENV WHISPER_LANGUAGE=es
ENV HOST=0.0.0.0
ENV PORT=9800

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD curl -sf http://localhost:9800/health || exit 1

CMD ["python3.11", "-m", "uvicorn", "whisper_service.main:app", "--host", "0.0.0.0", "--port", "9800", "--app-dir", "src"]
