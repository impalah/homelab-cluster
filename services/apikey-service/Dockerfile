FROM python:3.11-slim

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml .
COPY src/ ./src/

RUN uv pip install --system --no-cache .

# 8090 a propósito, no 8000: mismo motivo que whisper-service (ver
# ryzen/services/whisper-service/Dockerfile) — 8000 es el puerto por defecto
# de innumerables servicios FastAPI/dev, se evita para no colisionar.
EXPOSE 8090

ENV APIKEY_HOST=0.0.0.0
ENV APIKEY_PORT=8090

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8090/health')" || exit 1

CMD ["python3", "-m", "uvicorn", "apikey_service.main:app", "--host", "0.0.0.0", "--port", "8090", "--app-dir", "src"]
