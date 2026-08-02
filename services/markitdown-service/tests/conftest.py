import pytest
from fastapi.testclient import TestClient

from markitdown_service.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
