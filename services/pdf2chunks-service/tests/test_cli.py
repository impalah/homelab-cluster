"""Tests para pdf2chunks_service.cli."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from pdf2chunks_service.cli import (
    EXIT_PARTIAL_FAILURE,
    EXIT_SUCCESS,
    EXIT_TOTAL_FAILURE,
    run,
)

OCR_PAGE = "pdf2chunks_service.services.pdf_processing_service.ocr_engine.ocr_page"


def test_run_success_single_pdf(native_text_pdf: Path, output_dir: Path):
    exit_code = run([str(native_text_pdf), str(output_dir)])
    assert exit_code == EXIT_SUCCESS
    out_file = output_dir / "native.json"
    assert out_file.exists()
    data = json.loads(out_file.read_text())
    assert len(data) > 0


def test_run_success_directory_batch(
    tmp_pdf_dir: Path, native_text_pdf: Path, blank_pdf: Path, output_dir: Path
):
    with patch(OCR_PAGE, return_value="texto ocr " * 10):
        exit_code = run([str(tmp_pdf_dir), str(output_dir)])

    assert exit_code == EXIT_SUCCESS
    assert (output_dir / "native.json").exists()
    assert (output_dir / "blank.json").exists()


def test_run_total_failure_no_input_path(tmp_path: Path, output_dir: Path):
    exit_code = run([str(tmp_path / "no_existe.pdf"), str(output_dir)])
    assert exit_code == EXIT_TOTAL_FAILURE


def test_run_total_failure_no_pdfs_found(tmp_path: Path, output_dir: Path):
    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()
    exit_code = run([str(empty_dir), str(output_dir)])
    assert exit_code == EXIT_TOTAL_FAILURE


def test_run_total_failure_only_corrupt(corrupt_pdf: Path, output_dir: Path):
    exit_code = run([str(corrupt_pdf), str(output_dir)])
    assert exit_code == EXIT_TOTAL_FAILURE


def test_run_partial_failure_mixed_batch(
    tmp_pdf_dir: Path, native_text_pdf: Path, corrupt_pdf: Path, output_dir: Path
):
    exit_code = run([str(tmp_pdf_dir), str(output_dir)])
    assert exit_code == EXIT_PARTIAL_FAILURE
    assert (output_dir / "native.json").exists()


def test_run_with_cli_overrides(native_text_pdf: Path, output_dir: Path):
    exit_code = run(
        [
            str(native_text_pdf),
            str(output_dir),
            "--ocr-char-threshold",
            "5",
            "--chunk-size-tokens",
            "10",
            "--chunk-overlap-ratio",
            "0.1",
            "--chunking-strategy",
            "fixed_size",
            "--output-format",
            "jsonl",
        ]
    )
    assert exit_code == EXIT_SUCCESS
    assert (output_dir / "native.jsonl").exists()


def test_main_invokes_sys_exit(monkeypatch, native_text_pdf: Path, output_dir: Path):
    import sys

    from pdf2chunks_service.cli import main

    monkeypatch.setattr(sys, "argv", ["pdf2chunks-service", str(native_text_pdf), str(output_dir)])
    try:
        main()
    except SystemExit as exc:
        assert exc.code == EXIT_SUCCESS
    else:
        raise AssertionError("main() debería llamar a sys.exit")
