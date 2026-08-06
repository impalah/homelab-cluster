FROM python:3.12-slim

LABEL org.opencontainers.image.title="epub2pdf-service" \
      org.opencontainers.image.description="Conversion de EPUB a PDF (Calibre) para el pipeline de contenido homelab"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    EPUB2PDF_CALIBRE_BINARY=ebook-convert \
    EPUB2PDF_INPUT_PATH=/data/input \
    EPUB2PDF_OUTPUT_PATH=/data/output

# Instalación headless de Calibre y dependencias del sistema necesarias para
# ejecutar ebook-convert sin entorno gráfico (offscreen Qt).
RUN apt-get update && apt-get install -y --no-install-recommends \
        wget \
        xz-utils \
        libxcomposite1 \
        libxcursor1 \
        libxi6 \
        libxrandr2 \
        libxtst6 \
        libxkbcommon0 \
        libxkbcommon-x11-0 \
        libgl1 \
        libopengl0 \
        libegl1 \
        libnss3 \
        libglib2.0-0 \
        fontconfig \
        ca-certificates \
        libxcb-cursor0 \
        libxcb-icccm4 \
        libxcb-image0 \
        libxcb-keysyms1 \
        libxcb-randr0 \
        libxcb-render-util0 \
        libxcb-shape0 \
        libxcb-shm0 \
        libxcb-sync1 \
        libxcb-xfixes0 \
        libxcb-xinerama0 \
        libxcb-xkb1 \
        libdbus-1-3 \
        libxss1 \
        libxft2 \
        libxdamage1 \
        libxfixes3 \
        libasound2t64 \
        libnspr4 \
        libgbm1 \
        libpango-1.0-0 \
        libcairo2 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libcups2 \
        libdrm2 \
        libxcb1 \
        at-spi2-core \
        libpulse0 \
    && wget -nv -O /tmp/calibre-installer.sh \
        https://download.calibre-ebook.com/linux-installer.sh \
    && sh /tmp/calibre-installer.sh install_dir=/opt/calibre isolated=y \
    && ln -sf /opt/calibre/calibre/ebook-convert /usr/local/bin/ebook-convert \
    && rm -f /tmp/calibre-installer.sh \
    && apt-get purge -y wget \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Calibre headless requiere QT_QPA_PLATFORM=offscreen cuando no hay servidor
# gráfico disponible en el contenedor.
ENV QT_QPA_PLATFORM=offscreen

# La salida a PDF de Calibre usa Qt WebEngine (Chromium embebido) para
# renderizar. Chromium se niega a arrancar como root sin --no-sandbox — y
# este contenedor corre como root (imagen base sin usuario propio). Visto en
# vivo: "Running as root without --no-sandbox is not supported". El sandbox
# de Chromium no aporta nada aquí (ya estamos dentro del aislamiento del
# propio contenedor), así que desactivarlo así es la solución estándar para
# Calibre/QtWebEngine en Docker.
ENV QTWEBENGINE_CHROMIUM_FLAGS=--no-sandbox

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml .
COPY src/ ./src/

RUN uv pip install --system --no-cache .

RUN mkdir -p /data/input /data/output
VOLUME ["/data/input", "/data/output"]

# 8003 a propósito, no 8000/8001/8090/9800/8002 — puertos ya usados por
# crawl4ai-scraper-service/markitdown-service/apikey-service/whisper-service
# en este mismo clúster (ver docs/17-firewall-acceso-directo.md).
EXPOSE 8003

ENV EPUB2PDF_HOST=0.0.0.0
ENV EPUB2PDF_PORT=8003

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8003/health')" || exit 1

# Modo por defecto: API HTTP persistente (mismo patrón que el resto de
# microservicios del clúster: apikey-service, markitdown-service, etc.).
#
# Modo alternativo: CLI bajo demanda, pensada para invocarse desde n8n
# (Execute Command/SSH) como contenedor efímero por lote de ficheros, sin
# mantener el servicio siempre arriba. Para arrancar en este modo,
# sobreescribe el entrypoint:
#   docker run --rm --entrypoint python3 \
#     -v /ruta/entrada:/data/input:ro -v /ruta/salida:/data/output \
#     registry.home.arpa/epub2pdf-service:latest \
#     -m epub2pdf_service.cli --input /data/input --output /data/output
CMD ["python3", "-m", "uvicorn", "epub2pdf_service.main:app", "--host", "0.0.0.0", "--port", "8003", "--app-dir", "src"]
