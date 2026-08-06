"""
whisper-service — API REST de transcripción de audio con faster-whisper.

Endpoints:
  GET  /health      → estado del servicio y modelo cargado
  POST /transcribe  → transcribir audio (multipart/form-data, campo "file")
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from whisper_service import __version__
from whisper_service.config import settings
from whisper_service.controllers import health_controller, transcribe_controller
from whisper_service.infrastructure.whisper_model import load_model, set_model
from whisper_service.logging_setup import setup_logging

setup_logging(settings)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info(
        "Cargando modelo Whisper: model={} device={} compute_type={}",
        settings.whisper_model,
        settings.whisper_device,
        settings.whisper_compute_type,
    )
    model = load_model(
        settings.whisper_model, settings.whisper_device, settings.whisper_compute_type
    )
    set_model(model)
    logger.info("Modelo cargado correctamente.")
    yield
    logger.info("Apagando whisper-service.")


app = FastAPI(
    title="whisper-service",
    version=__version__,
    description="Transcripción de audio con faster-whisper y CUDA",
    lifespan=lifespan,
)

app.include_router(health_controller.router)
app.include_router(transcribe_controller.router)
