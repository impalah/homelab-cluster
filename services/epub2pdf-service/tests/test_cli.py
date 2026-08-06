"""Tests de integración del CLI (argparse + códigos de salida)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from epub2pdf_service.cli import EXIT_PARTIAL_FAILURE, EXIT_SUCCESS, EXIT_TOTAL_FAILURE, main

CALIBRE_RUN = "epub2pdf_service.infrastructure.calibre_converter.subprocess.run"


def _fake_calibre_success(command: list[str], **kwargs: object) -> MagicMock:
    output_path = Path(command[2])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"%PDF-1.4 contenido simulado")
    result = MagicMock(spec=subprocess.CompletedProcess)
    result.returncode = 0
    result.stdout = "ok"
    result.stderr = ""
    return result


class TestCliExitCodes:
    @patch(CALIBRE_RUN, side_effect=_fake_calibre_success)
    def test_full_success_returns_zero(self, mock_run: MagicMock, tmp_path: Path) -> None:
        from tests.conftest import build_epub

        input_dir = tmp_path / "in"
        input_dir.mkdir()
        build_epub(input_dir / "a.epub", title="A")
        output_dir = tmp_path / "out"

        exit_code = main(["--input", str(input_dir), "--output", str(output_dir)])

        assert exit_code == EXIT_SUCCESS

    def test_missing_input_path_returns_total_failure(self, tmp_path: Path) -> None:
        missing = tmp_path / "no_existe"
        output_dir = tmp_path / "out"

        exit_code = main(["--input", str(missing), "--output", str(output_dir)])

        assert exit_code == EXIT_TOTAL_FAILURE

    def test_empty_input_directory_returns_total_failure(self, tmp_path: Path) -> None:
        input_dir = tmp_path / "in"
        input_dir.mkdir()
        output_dir = tmp_path / "out"

        exit_code = main(["--input", str(input_dir), "--output", str(output_dir)])

        assert exit_code == EXIT_TOTAL_FAILURE

    @patch(CALIBRE_RUN)
    def test_partial_failure_returns_one(self, mock_run: MagicMock, tmp_path: Path) -> None:
        from tests.conftest import build_epub

        input_dir = tmp_path / "in"
        input_dir.mkdir()
        build_epub(input_dir / "bueno.epub", title="Bueno")
        (input_dir / "corrupto.epub").write_bytes(b"invalido")

        mock_run.side_effect = lambda command, **kwargs: _fake_calibre_success(command)

        output_dir = tmp_path / "out"
        exit_code = main(["--input", str(input_dir), "--output", str(output_dir)])

        assert exit_code == EXIT_PARTIAL_FAILURE

    def test_total_failure_all_corrupt(self, tmp_path: Path) -> None:
        input_dir = tmp_path / "in"
        input_dir.mkdir()
        (input_dir / "corrupto1.epub").write_bytes(b"invalido")
        (input_dir / "corrupto2.epub").write_bytes(b"invalido tambien")
        output_dir = tmp_path / "out"

        exit_code = main(["--input", str(input_dir), "--output", str(output_dir)])

        assert exit_code == EXIT_TOTAL_FAILURE

    @patch(CALIBRE_RUN, side_effect=_fake_calibre_success)
    def test_single_file_input(self, mock_run: MagicMock, tmp_path: Path) -> None:
        from tests.conftest import build_epub

        epub_file = tmp_path / "solo.epub"
        build_epub(epub_file, title="Solo")
        output_dir = tmp_path / "out"

        exit_code = main(["--input", str(epub_file), "--output", str(output_dir)])

        assert exit_code == EXIT_SUCCESS
        assert (output_dir / "solo.pdf").exists()

    @patch(CALIBRE_RUN, side_effect=_fake_calibre_success)
    def test_settings_defaults_used_when_no_cli_args(
        self, mock_run: MagicMock, tmp_path: Path, monkeypatch
    ) -> None:
        # "settings" es un singleton leído una vez al importar el módulo
        # (mismo patrón que apikey-service/markitdown-service) — para
        # simular "sin argumentos de CLI, usar la config por defecto" en
        # un proceso de test ya arrancado, se parchea el propio objeto en
        # vez de mutar variables de entorno (que ya no se releerían).
        from tests.conftest import build_epub

        input_dir = tmp_path / "in"
        input_dir.mkdir()
        build_epub(input_dir / "a.epub", title="A")
        output_dir = tmp_path / "out"

        from epub2pdf_service.config import settings

        monkeypatch.setattr(settings, "input_path", str(input_dir))
        monkeypatch.setattr(settings, "output_path", str(output_dir))

        exit_code = main([])

        assert exit_code == EXIT_SUCCESS
