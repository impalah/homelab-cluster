from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from apikey_service import __version__
from apikey_service.controllers import health_controller, keys_controller, validate_controller
from apikey_service.db import Base, engine
from apikey_service.logging_setup import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("apikey-service listo, esquema verificado")
    yield


app = FastAPI(title="apikey-service", version=__version__, lifespan=lifespan)

app.include_router(health_controller.router)
app.include_router(validate_controller.router)
app.include_router(keys_controller.router)
