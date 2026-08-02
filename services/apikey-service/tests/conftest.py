"""Fixtures comunes. El bloque de variables de entorno de arriba del todo
tiene que ejecutarse ANTES de que se importe cualquier módulo de
apikey_service (config.py lee el entorno al construir "settings" a nivel de
módulo) — por eso vive en conftest.py, que pytest carga antes de recolectar
los tests, y por eso usa os.environ.setdefault en vez de un fixture normal.
"""

import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).parent / "test_apikeys.db"
if TEST_DB_PATH.exists():
    TEST_DB_PATH.unlink()

os.environ.setdefault("APIKEY_DATABASE_URL", f"sqlite+aiosqlite:///{TEST_DB_PATH}")
os.environ.setdefault("APIKEY_ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("APIKEY_OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", "http://localhost:4318/v1/logs")

import pytest  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from apikey_service.db import Base, async_session, engine  # noqa: E402


@pytest.fixture(autouse=True)
async def _reset_schema():
    """Esquema limpio antes de cada test — sqlite de fichero, rápido de recrear."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest.fixture
async def db_session() -> AsyncSession:
    async with async_session() as session:
        yield session
