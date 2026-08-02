import io

from markitdown_service import __version__
from markitdown_service import dependencies as dependencies_module
from markitdown_service.config import settings


def test_health_returns_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "version": __version__,
        "service": "markitdown-service",
    }


def test_convert_plain_text_file(client):
    content = b"Hello world, this is a test."
    response = client.post(
        "/convert",
        files={"file": ("test.txt", io.BytesIO(content), "text/plain")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "test.txt"
    assert body["extension"] == ".txt"
    assert body["size_bytes"] == len(content)
    assert "Hello world" in body["markdown"]
    assert body["characters"] == len(body["markdown"])


def test_convert_html_file(client):
    html = b"<html><body><h1>Title</h1><p>Some paragraph.</p></body></html>"
    response = client.post(
        "/convert",
        files={"file": ("page.html", io.BytesIO(html), "text/html")},
    )

    assert response.status_code == 200
    body = response.json()
    assert "Title" in body["markdown"]


def test_convert_uses_filename_hint_when_upload_name_has_no_extension(client):
    content = b"Some content"
    response = client.post(
        "/convert",
        files={"file": ("upload", io.BytesIO(content), "application/octet-stream")},
        data={"filename_hint": "document.txt"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "document.txt"
    assert body["extension"] == ".txt"


def test_convert_rejects_unsupported_extension(client):
    response = client.post(
        "/convert",
        files={"file": ("virus.exe", io.BytesIO(b"whatever"), "application/octet-stream")},
    )

    assert response.status_code == 415
    assert "no soportado" in response.json()["detail"]


def test_convert_rejects_empty_file(client):
    response = client.post(
        "/convert",
        files={"file": ("empty.txt", io.BytesIO(b""), "text/plain")},
    )

    assert response.status_code == 400
    assert "vac" in response.json()["detail"].lower()


def test_convert_rejects_file_over_max_size(client, monkeypatch):
    monkeypatch.setattr(settings, "max_file_size", 10)
    content = b"this is definitely more than ten bytes"

    response = client.post(
        "/convert",
        files={"file": ("big.txt", io.BytesIO(content), "text/plain")},
    )

    assert response.status_code == 413
    assert "grande" in response.json()["detail"]


def test_convert_returns_422_when_conversion_produces_no_content(client, monkeypatch):
    monkeypatch.setattr(dependencies_module._converter, "convert", lambda path: "   ")

    response = client.post(
        "/convert",
        files={"file": ("test.txt", io.BytesIO(b"content"), "text/plain")},
    )

    assert response.status_code == 422
    assert "no produjo contenido" in response.json()["detail"]


def test_convert_returns_500_on_conversion_error(client, monkeypatch):
    def _boom(path):
        raise RuntimeError("boom")

    monkeypatch.setattr(dependencies_module._converter, "convert", _boom)

    response = client.post(
        "/convert",
        files={"file": ("test.txt", io.BytesIO(b"content"), "text/plain")},
    )

    assert response.status_code == 500
    assert "boom" in response.json()["detail"]


def test_convert_without_extension_and_without_hint_still_attempts_conversion(client):
    # Sin extensión reconocible ni filename_hint, no hay nada que rechazar en
    # el chequeo de formato soportado (ext queda vacío) — pasa a intentar
    # convertir de todas formas; markitdown la trata como texto plano.
    response = client.post(
        "/convert",
        files={"file": ("noext", io.BytesIO(b"Plain content"), "application/octet-stream")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["extension"] == "desconocida"
    assert body["markdown"] == "Plain content"
