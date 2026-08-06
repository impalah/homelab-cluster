"""Tests de integración de la API HTTP (GET /health, POST /convert)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from epub2pdf_service import __version__
from epub2pdf_service import dependencies as dependencies_module


def _fake_convert_success(source_epub: Path, output_pdf: Path, timeout_seconds: int) -> MagicMock:
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    output_pdf.write_bytes(b"%PDF-1.4 contenido simulado")
    result = MagicMock(spec=subprocess.CompletedProcess)
    result.returncode = 0
    result.stdout = "ok"
    result.stderr = ""
    return result


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "version": __version__,
        "service": "epub2pdf-service",
    }


def test_convert_input_path_missing(client: TestClient, tmp_path: Path) -> None:
    missing = tmp_path / "no-existe"
    response = client.post(
        "/convert",
        json={"input_path": str(missing), "output_path": str(tmp_path / "out")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failure"
    assert body["total"] == 0


def test_convert_success(client: TestClient, tmp_path: Path, monkeypatch) -> None:
    from tests.conftest import build_epub

    monkeypatch.setattr(dependencies_module._converter, "convert", _fake_convert_success)

    input_dir = tmp_path / "in"
    input_dir.mkdir()
    build_epub(input_dir / "libro.epub", title="Libro")
    output_dir = tmp_path / "out"

    response = client.post(
        "/convert",
        json={"input_path": str(input_dir), "output_path": str(output_dir)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["total"] == 1
    assert body["successes"] == 1
    assert body["failures"] == 0
    assert body["results"][0]["status"] == "success"


def test_convert_partial_failure(client: TestClient, tmp_path: Path, monkeypatch) -> None:
    from tests.conftest import build_epub

    monkeypatch.setattr(dependencies_module._converter, "convert", _fake_convert_success)

    input_dir = tmp_path / "in"
    input_dir.mkdir()
    build_epub(input_dir / "bueno.epub", title="Bueno")
    (input_dir / "corrupto.epub").write_bytes(b"no es un epub valido")
    output_dir = tmp_path / "out"

    response = client.post(
        "/convert",
        json={"input_path": str(input_dir), "output_path": str(output_dir)},
    )

    body = response.json()
    assert body["status"] == "partial_failure"
    assert body["successes"] == 1
    assert body["failures"] == 1


def test_convert_total_failure(client: TestClient, tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    (input_dir / "corrupto.epub").write_bytes(b"no es un epub valido")
    output_dir = tmp_path / "out"

    response = client.post(
        "/convert",
        json={"input_path": str(input_dir), "output_path": str(output_dir)},
    )

    body = response.json()
    assert body["status"] == "failure"
    assert body["successes"] == 0
    assert body["failures"] == 1
    assert body["results"][0]["reason"] == "corrupt_epub"
