# syntax=docker/dockerfile:1.7

# =============================================================================
# Stage 1: builder — instala dependencias de Python con uv en un venv
# =============================================================================
FROM python:3.14-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# Instala primero solo las dependencias (mejor cacheo de capas Docker).
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --no-dev

# Copia el código de la aplicación e instala el propio proyecto.
COPY src ./src
RUN uv sync --frozen --no-dev

# =============================================================================
# Stage 2: runtime — imagen final con navegador de Playwright instalado
# =============================================================================
FROM python:3.14-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/app/.venv/bin:$PATH" \
    PLAYWRIGHT_BROWSERS_PATH=/app/.playwright-browsers \
    HOST=0.0.0.0 \
    PORT=8000

WORKDIR /app

# Dependencias mínimas de sistema (curl para el HEALTHCHECK; el resto de
# librerías nativas de Chromium las instala `playwright install --with-deps`).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Reutiliza el entorno virtual construido en el stage anterior.
COPY --from=builder /app/.venv /app/.venv
COPY src ./src
COPY README.md ./

# Instala el navegador Chromium de Playwright junto a sus dependencias de
# sistema, necesario para el render de páginas de Crawl4AI.
#
# ⚠️ Con ENABLE_UNDETECTED_BROWSER=true, Crawl4AI usa el Undetected Browser
# Adapter, que por debajo corre sobre "patchright" (fork de Playwright con
# parches de evasión), NO sobre el paquete "playwright" normal — y
# patchright gestiona su PROPIO build de Chromium (misma variable de entorno
# PLAYWRIGHT_BROWSERS_PATH, pero una revisión de navegador distinta). Sin
# este segundo "patchright install", el modo undetected falla en el
# arranque con "BrowserType.launch: Executable doesn't exist at
# .../chromium_headless_shell-.../headless_shell" — pasó de verdad en el
# primer despliegue real con ENABLE_UNDETECTED_BROWSER=true (los tests no lo
# detectan: mockean el repositorio entero, nunca lanzan un navegador real).
RUN playwright install --with-deps chromium \
    && patchright install --with-deps chromium \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Usuario no privilegiado para ejecutar la aplicación.
RUN groupadd --system app \
    && useradd --system --gid app --home-dir /app --shell /usr/sbin/nologin app \
    && chown -R app:app /app

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://localhost:${PORT}/health" || exit 1

CMD ["uvicorn", "crawl4ai_scraper_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
