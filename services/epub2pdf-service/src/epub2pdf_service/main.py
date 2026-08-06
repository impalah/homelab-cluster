"""
epub2pdf-service — API REST de conversión de EPUB a PDF (Calibre).

Endpoints:
  GET  /health    -> estado del servicio
  POST /convert   -> convertir por lote {"input_path": ..., "output_path": ...}

Modo alternativo: CLI bajo demanda (epub2pdf_service.cli), pensado para
invocarse como contenedor efímero desde n8n (Execute Command/SSH) en vez
de mantener el servicio siempre arriba. Ver README.md.
"""

from fastapi import FastAPI

from epub2pdf_service import __version__
from epub2pdf_service.config import settings
from epub2pdf_service.controllers import convert_controller, health_controller
from epub2pdf_service.logging_setup import setup_logging
from epub2pdf_service.telemetry import init_telemetry

setup_logging(settings)
init_telemetry(settings)

app = FastAPI(
    title="epub2pdf-service",
    version=__version__,
    description="Conversión de EPUB a PDF (Calibre) para el pipeline de contenido homelab.",
)

app.include_router(health_controller.router)
app.include_router(convert_controller.router)
