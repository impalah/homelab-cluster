"""Tests de integración de la API HTTP (GET /health, POST /process)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from pdf2chunks_service import __version__


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "version": __version__,
        "service": "pdf2chunks-service",
    }


def test_process_input_path_missing(client: TestClient, tmp_path: Path) -> None:
    missing = tmp_path / "no-existe"
    response = client.post(
        "/process",
        json={"input_path": str(missing), "output_path": str(tmp_path / "out")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failure"
    assert body["total"] == 0


def test_process_success(
    client: TestClient, tmp_pdf_dir: Path, native_text_pdf: Path, output_dir: Path
) -> None:
    response = client.post(
        "/process",
        json={"input_path": str(tmp_pdf_dir), "output_path": str(output_dir)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["total"] == 1
    assert body["successes"] == 1
    assert body["failures"] == 0
    assert body["results"][0]["chunk_count"] > 0
    assert (output_dir / "native.json").exists()


def test_process_partial_failure(
    client: TestClient,
    tmp_pdf_dir: Path,
    native_text_pdf: Path,
    corrupt_pdf: Path,
    output_dir: Path,
) -> None:
    response = client.post(
        "/process",
        json={"input_path": str(tmp_pdf_dir), "output_path": str(output_dir)},
    )

    body = response.json()
    assert body["status"] == "partial_failure"
    assert body["successes"] == 1
    assert body["failures"] == 1
    failed_entry = next(r for r in body["results"] if not r["success"])
    assert failed_entry["error"] is not None
