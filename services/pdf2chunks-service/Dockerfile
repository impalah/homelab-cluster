FROM python:3.12-slim

LABEL org.opencontainers.image.title="pdf2chunks-service" \
      org.opencontainers.image.description="Troceado (chunking) de PDF a fragmentos indexables para el pipeline RAG de homelab"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# tesseract-ocr: motor de OCR usado por PyMuPDF (page.get_textpage_ocr) como
# fallback cuando una página no tiene texto nativo suficiente. eng+spa
# cubren los idiomas del pipeline de contenido; libgl1/libglib2.0-0 son
# dependencias de carga dinámica de MuPDF.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-spa \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml .
COPY src/ ./src/

RUN uv pip install --system --no-cache .

RUN mkdir -p /data/input /data/output
VOLUME ["/data/input", "/data/output"]

# 8004 a propósito, no 8000/8001/8090/9800/8002/8003 — puertos ya usados por
# crawl4ai-scraper-service/markitdown-service/apikey-service/whisper-service/
# epub2pdf-service en este mismo clúster (ver docs/17-firewall-acceso-directo.md).
EXPOSE 8004

ENV PDF2CHUNKS_HOST=0.0.0.0
ENV PDF2CHUNKS_PORT=8004

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8004/health')" || exit 1

# Modo por defecto: API HTTP persistente (mismo patrón que el resto de
# microservicios del clúster: apikey-service, markitdown-service, etc.).
#
# Modo alternativo: CLI bajo demanda, pensada para invocarse desde n8n
# (Execute Command/SSH) como contenedor efímero por lote de ficheros, sin
# mantener el servicio siempre arriba. Para arrancar en este modo,
# sobreescribe el entrypoint:
#   docker run --rm --entrypoint python3 \
#     -v /ruta/entrada:/data/input:ro -v /ruta/salida:/data/output \
#     registry.home.arpa/pdf2chunks-service:latest \
#     -m pdf2chunks_service.cli /data/input /data/output
CMD ["python3", "-m", "uvicorn", "pdf2chunks_service.main:app", "--host", "0.0.0.0", "--port", "8004", "--app-dir", "src"]
