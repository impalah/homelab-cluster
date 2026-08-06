"""Tests para pdf2chunks_service.infrastructure.chunk_writer."""

from __future__ import annotations

import json
from pathlib import Path

from pdf2chunks_service.domain.models import Chunk, ProcessingResult
from pdf2chunks_service.infrastructure.chunk_writer import write_result


def _result_with_chunk() -> ProcessingResult:
    chunk = Chunk.create(
        document_id="d",
        text="hola",
        page=1,
        chapter=None,
        title=None,
        author=None,
        source_file="doc.pdf",
        chunk_index=0,
        ocr_applied=False,
    )
    return ProcessingResult(source_file="doc.pdf", success=True, chunks=[chunk])


def test_write_result_json_format(tmp_path: Path):
    out_dir = tmp_path / "out"

    out_path = write_result(_result_with_chunk(), out_dir, "json")

    assert out_path == out_dir / "doc.json"
    data = json.loads(out_path.read_text())
    assert isinstance(data, list)
    assert data[0]["text"] == "hola"


def test_write_result_jsonl_format(tmp_path: Path):
    out_dir = tmp_path / "out"

    out_path = write_result(_result_with_chunk(), out_dir, "jsonl")

    assert out_path == out_dir / "doc.jsonl"
    lines = out_path.read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["text"] == "hola"


def test_write_result_no_chunks_returns_none(tmp_path: Path):
    result = ProcessingResult(source_file="doc.pdf", success=True, chunks=[])
    assert write_result(result, tmp_path / "out", "json") is None
