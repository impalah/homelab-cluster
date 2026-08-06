"""
pdf2chunks-service — API REST de troceado (chunking) de PDF para RAG.

Endpoints:
  GET  /health    -> estado del servicio
  POST /process   -> trocear por lote {"input_path": ..., "output_path": ...}

Modo alternativo: CLI bajo demanda (pdf2chunks_service.cli), pensado para
invocarse como contenedor efímero desde n8n (Execute Command/SSH) en vez
de mantener el servicio siempre arriba. Ver README.md.
"""

from fastapi import FastAPI

from pdf2chunks_service import __version__
from pdf2chunks_service.config import settings
from pdf2chunks_service.controllers import health_controller, process_controller
from pdf2chunks_service.logging_setup import setup_logging

setup_logging(settings)

app = FastAPI(
    title="pdf2chunks-service",
    version=__version__,
    description=(
        "Troceado (chunking) de PDF a fragmentos indexables para el pipeline RAG de homelab."
    ),
)

app.include_router(health_controller.router)
app.include_router(process_controller.router)
