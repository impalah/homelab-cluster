import pytest
from fastapi.testclient import TestClient

from apikey_service import __version__
from apikey_service.config import settings
from apikey_service.main import app

ADMIN_HEADERS = {"Authorization": f"Bearer {settings.admin_token}"}


@pytest.fixture
def client(monkeypatch):
    # setup_logging() real abriría un exportador OTLP contra un collector
    # que no existe en el entorno de test — se sustituye por un no-op.
    # El resto del lifespan (creación de esquema) sí corre de verdad,
    # contra el sqlite de test.
    monkeypatch.setattr("apikey_service.main.setup_logging", lambda: None)
    with TestClient(app) as test_client:
        yield test_client


def test_health_returns_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "version": __version__,
        "service": "apikey-service",
    }


def test_validate_without_key_is_401(client):
    assert client.get("/validate").status_code == 401


def test_validate_with_wrong_key_is_401(client):
    response = client.get("/validate", headers={"X-Api-Key": "does-not-exist"})
    assert response.status_code == 401


def test_keys_endpoints_require_admin_token(client):
    assert client.get("/keys").status_code == 401
    assert client.post("/keys", json={"label": "x"}).status_code == 401
    assert client.delete("/keys/1").status_code == 401


def test_keys_endpoints_reject_wrong_admin_token(client):
    headers = {"Authorization": "Bearer wrong"}
    assert client.get("/keys", headers=headers).status_code == 401


def test_create_list_validate_revoke_full_lifecycle(client):
    create_response = client.post("/keys", json={"label": "ci-test"}, headers=ADMIN_HEADERS)
    assert create_response.status_code == 201
    body = create_response.json()
    assert body["label"] == "ci-test"
    assert "key" in body
    raw_key = body["key"]
    key_id = body["id"]

    # La key funciona
    validate_response = client.get("/validate", headers={"X-Api-Key": raw_key})
    assert validate_response.status_code == 200
    assert validate_response.json() == {"status": "ok"}

    # Aparece listada, sin el valor en claro
    list_response = client.get("/keys", headers=ADMIN_HEADERS)
    assert list_response.status_code == 200
    listed = [k for k in list_response.json() if k["id"] == key_id]
    assert len(listed) == 1
    assert "key" not in listed[0]
    assert listed[0]["revoked_at"] is None

    # Se revoca
    revoke_response = client.delete(f"/keys/{key_id}", headers=ADMIN_HEADERS)
    assert revoke_response.status_code == 204

    # Ya no es válida
    validate_after_revoke = client.get("/validate", headers={"X-Api-Key": raw_key})
    assert validate_after_revoke.status_code == 401


def test_revoke_nonexistent_key_is_404(client):
    response = client.delete("/keys/999999", headers=ADMIN_HEADERS)
    assert response.status_code == 404


def test_create_key_requires_label_field(client):
    response = client.post("/keys", json={}, headers=ADMIN_HEADERS)
    assert response.status_code == 422
