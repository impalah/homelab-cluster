"""Tests unitarios e integración del ConversionService.

Todas las invocaciones a Calibre se mockean vía `subprocess.run` (dentro
de infrastructure.calibre_converter) para no depender de que el binario
`ebook-convert` esté instalado en el entorno de pruebas.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from epub2pdf_service.domain.models import ConversionErrorReason, ConversionStatus
from epub2pdf_service.services.conversion_service import (
    ConversionService,
    discover_epub_files,
    resolve_output_path,
)

CALIBRE_RUN = "epub2pdf_service.infrastructure.calibre_converter.subprocess.run"


def _fake_calibre_success(command: list[str], **kwargs: object) -> MagicMock:
    # Simula que Calibre crea el fichero de salida y devuelve returncode 0.
    output_path = Path(command[2])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"%PDF-1.4 contenido simulado")
    result = MagicMock(spec=subprocess.CompletedProcess)
    result.returncode = 0
    result.stdout = "ok"
    result.stderr = ""
    return result


class TestResolveOutputPath:
    def test_no_collision_returns_stem_pdf(self, tmp_path: Path) -> None:
        source = tmp_path / "libro.epub"
        source.write_text("x")
        output_dir = tmp_path / "out"
        output_dir.mkdir()

        result = resolve_output_path(source, output_dir)

        assert result == output_dir / "libro.pdf"

    def test_collision_appends_counter(self, tmp_path: Path) -> None:
        source = tmp_path / "libro.epub"
        source.write_text("x")
        output_dir = tmp_path / "out"
        output_dir.mkdir()
        (output_dir / "libro.pdf").write_text("existing")

        result = resolve_output_path(source, output_dir)

        assert result == output_dir / "libro (1).pdf"

    def test_multiple_collisions(self, tmp_path: Path) -> None:
        source = tmp_path / "libro.epub"
        source.write_text("x")
        output_dir = tmp_path / "out"
        output_dir.mkdir()
        (output_dir / "libro.pdf").write_text("existing")
        (output_dir / "libro (1).pdf").write_text("existing")

        result = resolve_output_path(source, output_dir)

        assert result == output_dir / "libro (2).pdf"

    def test_exhausted_attempts_raises(self, tmp_path: Path) -> None:
        source = tmp_path / "libro.epub"
        source.write_text("x")
        output_dir = tmp_path / "out"
        output_dir.mkdir()
        (output_dir / "libro.pdf").write_text("existing")
        (output_dir / "libro (1).pdf").write_text("existing")

        with pytest.raises(RuntimeError):
            resolve_output_path(source, output_dir, max_attempts=1)


class TestDiscoverEpubFiles:
    def test_single_file_input(self, valid_epub_path: Path) -> None:
        assert discover_epub_files(valid_epub_path) == [valid_epub_path]

    def test_non_epub_single_file_returns_empty(self, tmp_path: Path) -> None:
        txt_file = tmp_path / "doc.txt"
        txt_file.write_text("hola")
        assert discover_epub_files(txt_file) == []

    def test_directory_lists_only_epub_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.epub").write_text("a")
        (tmp_path / "b.epub").write_text("b")
        (tmp_path / "c.txt").write_text("c")

        result = discover_epub_files(tmp_path)

        assert sorted(p.name for p in result) == ["a.epub", "b.epub"]

    def test_empty_directory_returns_empty(self, empty_input_dir: Path) -> None:
        assert discover_epub_files(empty_input_dir) == []

    def test_nonexistent_path_returns_empty(self, tmp_path: Path) -> None:
        assert discover_epub_files(tmp_path / "no_existe") == []


class TestConvertSingleSuccess:
    @patch(CALIBRE_RUN, side_effect=_fake_calibre_success)
    def test_successful_conversion_creates_pdf_and_sidecar(
        self,
        mock_run: MagicMock,
        valid_epub_path: Path,
        output_dir: Path,
        conversion_service: ConversionService,
    ) -> None:
        result = conversion_service.convert_single(valid_epub_path, output_dir)

        assert result.status == ConversionStatus.SUCCESS
        assert result.output_path is not None
        assert result.output_path.exists()
        assert result.output_path.name == "libro_valido.pdf"

        sidecar = output_dir / "libro_valido.meta.json"
        assert sidecar.exists()
        assert "Libro de Prueba" in sidecar.read_text(encoding="utf-8")
        mock_run.assert_called_once()

    @patch(CALIBRE_RUN, side_effect=_fake_calibre_success)
    def test_successful_conversion_without_metadata(
        self,
        mock_run: MagicMock,
        epub_without_metadata_path: Path,
        output_dir: Path,
        conversion_service: ConversionService,
    ) -> None:
        result = conversion_service.convert_single(epub_without_metadata_path, output_dir)

        assert result.status == ConversionStatus.SUCCESS
        assert (output_dir / "libro_sin_metadatos.meta.json").exists()


class TestConvertSingleFailures:
    def test_corrupt_epub_fails_gracefully(
        self,
        corrupt_epub_path: Path,
        output_dir: Path,
        conversion_service: ConversionService,
    ) -> None:
        result = conversion_service.convert_single(corrupt_epub_path, output_dir)

        assert result.status == ConversionStatus.FAILURE
        assert result.reason == ConversionErrorReason.CORRUPT_EPUB
        assert result.output_path is None

    @patch(CALIBRE_RUN)
    def test_calibre_failure_returncode(
        self,
        mock_run: MagicMock,
        valid_epub_path: Path,
        output_dir: Path,
        conversion_service: ConversionService,
    ) -> None:
        mock_run.return_value = MagicMock(
            spec=subprocess.CompletedProcess,
            returncode=1,
            stdout="",
            stderr="Error desconocido de conversion",
        )

        result = conversion_service.convert_single(valid_epub_path, output_dir)

        assert result.status == ConversionStatus.FAILURE
        assert result.reason == ConversionErrorReason.CALIBRE_FAILURE
        assert result.output_path is None

    @patch(CALIBRE_RUN)
    def test_drm_detected_from_stderr(
        self,
        mock_run: MagicMock,
        valid_epub_path: Path,
        output_dir: Path,
        conversion_service: ConversionService,
    ) -> None:
        mock_run.return_value = MagicMock(
            spec=subprocess.CompletedProcess,
            returncode=1,
            stdout="",
            stderr="This book is protected by DRM and cannot be converted",
        )

        result = conversion_service.convert_single(valid_epub_path, output_dir)

        assert result.status == ConversionStatus.FAILURE
        assert result.reason == ConversionErrorReason.DRM_PROTECTED

    @patch(CALIBRE_RUN, side_effect=subprocess.TimeoutExpired(cmd="ebook-convert", timeout=5))
    def test_conversion_timeout(
        self,
        mock_run: MagicMock,
        valid_epub_path: Path,
        output_dir: Path,
        conversion_service: ConversionService,
    ) -> None:
        result = conversion_service.convert_single(valid_epub_path, output_dir)

        assert result.status == ConversionStatus.FAILURE
        assert result.reason == ConversionErrorReason.TIMEOUT

    @patch(CALIBRE_RUN, side_effect=RuntimeError("fallo inesperado"))
    def test_unexpected_error_is_captured(
        self,
        mock_run: MagicMock,
        valid_epub_path: Path,
        output_dir: Path,
        conversion_service: ConversionService,
    ) -> None:
        result = conversion_service.convert_single(valid_epub_path, output_dir)

        assert result.status == ConversionStatus.FAILURE
        assert result.reason == ConversionErrorReason.UNKNOWN


class TestConvertBatch:
    @patch(CALIBRE_RUN, side_effect=_fake_calibre_success)
    def test_batch_all_success(
        self,
        mock_run: MagicMock,
        tmp_path: Path,
        conversion_service: ConversionService,
    ) -> None:
        from tests.conftest import build_epub

        input_dir = tmp_path / "in"
        input_dir.mkdir()
        for i in range(3):
            build_epub(input_dir / f"libro{i}.epub", title=f"Libro {i}")

        output_dir = tmp_path / "out"
        results = conversion_service.convert_batch(input_dir, output_dir)

        assert len(results) == 3
        assert all(r.status == ConversionStatus.SUCCESS for r in results)

    def test_batch_empty_directory_returns_empty_list(
        self,
        empty_input_dir: Path,
        output_dir: Path,
        conversion_service: ConversionService,
    ) -> None:
        assert conversion_service.convert_batch(empty_input_dir, output_dir) == []

    @patch(CALIBRE_RUN)
    def test_batch_partial_failure(
        self,
        mock_run: MagicMock,
        tmp_path: Path,
        conversion_service: ConversionService,
    ) -> None:
        from tests.conftest import build_epub

        input_dir = tmp_path / "in"
        input_dir.mkdir()
        build_epub(input_dir / "bueno.epub", title="Bueno")
        (input_dir / "corrupto.epub").write_bytes(b"no es un epub valido")

        mock_run.side_effect = lambda command, **kwargs: _fake_calibre_success(command)

        output_dir = tmp_path / "out"
        results = conversion_service.convert_batch(input_dir, output_dir)

        assert len(results) == 2
        statuses = {r.source_path.name: r.status for r in results}
        assert statuses["bueno.epub"] == ConversionStatus.SUCCESS
        assert statuses["corrupto.epub"] == ConversionStatus.FAILURE
