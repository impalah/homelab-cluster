FROM python:3.12-slim

# Instalar dependencias del sistema para markitdown
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libmagic1 \
    poppler-utils \
    pandoc \
    && rm -rf /var/lib/apt/lists/*

# Instalar uv
RUN pip install --no-cache-dir uv

WORKDIR /app

# Copiar archivos del proyecto
COPY pyproject.toml .
COPY src/ ./src/

# Instalar dependencias con uv (sin entorno virtual, directo al sistema)
RUN uv pip install --system --no-cache .

# Puerto de escucha
EXPOSE 8001

# Variables de entorno por defecto
ENV MARKITDOWN_PORT=8001
ENV MARKITDOWN_LOG_LEVEL=INFO
ENV HOST=0.0.0.0

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -sf http://localhost:8001/health || exit 1

CMD ["python3", "-m", "uvicorn", "markitdown_service.main:app", "--host", "0.0.0.0", "--port", "8001", "--app-dir", "src"]
