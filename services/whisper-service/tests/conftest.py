import pytest
from fastapi.testclient import TestClient

from whisper_service.main import app


@pytest.fixture
def client() -> TestClient:
    # Sin "with": así NO se dispara el lifespan (que cargaría un WhisperModel
    # real vía CUDA/descarga de pesos) — cada test que necesite un modelo
    # "cargado" monkeypatchea whisper_service.infrastructure.whisper_model._model
    # directamente (vía set_model, ver test_controllers.py).
    return TestClient(app)
