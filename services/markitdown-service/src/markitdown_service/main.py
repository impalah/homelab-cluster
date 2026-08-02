"""
markitdown-service — API REST de conversión de documentos a Markdown.

Endpoints:
  GET  /health    → estado del servicio
  POST /convert   → convertir documento a Markdown (multipart/form-data, campo "file")
"""

import sys

from fastapi import FastAPI
from loguru import logger

from markitdown_service import __version__
from markitdown_service.config import settings
from markitdown_service.controllers import convert_controller, health_controller

logger.remove()
logger.add(sys.stdout, level=settings.markitdown_log_level.upper(), enqueue=True)

app = FastAPI(
    title="markitdown-service",
    version=__version__,
    description="Convierte documentos (PDF, DOCX, XLSX, PPTX, HTML, imágenes, audio) a Markdown",
)

app.include_router(health_controller.router)
app.include_router(convert_controller.router)
