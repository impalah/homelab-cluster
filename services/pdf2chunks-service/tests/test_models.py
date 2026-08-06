"""Tests para pdf2chunks_service.domain.models."""

from __future__ import annotations

import uuid

from pdf2chunks_service.domain.models import Chunk, DocumentMetadata, ProcessingResult, TocEntry


def test_document_metadata_chapter_for_page_with_toc():
    toc = [
        TocEntry(level=1, title="Introducción", page=1),
        TocEntry(level=1, title="Desarrollo", page=5),
        TocEntry(level=1, title="Conclusión", page=10),
    ]
    meta = DocumentMetadata(document_id="abc", source_file="f.pdf", toc=toc)

    assert meta.chapter_for_page(1) == "Introducción"
    assert meta.chapter_for_page(3) == "Introducción"
    assert meta.chapter_for_page(5) == "Desarrollo"
    assert meta.chapter_for_page(9) == "Desarrollo"
    assert meta.chapter_for_page(10) == "Conclusión"
    assert meta.chapter_for_page(100) == "Conclusión"


def test_document_metadata_chapter_for_page_before_first_entry():
    toc = [TocEntry(level=1, title="Introducción", page=3)]
    meta = DocumentMetadata(document_id="abc", source_file="f.pdf", toc=toc)
    assert meta.chapter_for_page(1) is None


def test_document_metadata_chapter_for_page_without_toc():
    meta = DocumentMetadata(document_id="abc", source_file="f.pdf", toc=[])
    assert meta.chapter_for_page(1) is None


def test_chunk_create_generates_uuid_and_char_count():
    chunk = Chunk.create(
        document_id="docid123",
        text="hola mundo",
        page=1,
        chapter="Intro",
        title="Título",
        author="Autor",
        source_file="f.pdf",
        chunk_index=0,
        ocr_applied=False,
    )

    assert uuid.UUID(chunk.chunk_id)  # valida formato UUID
    assert chunk.char_count == len("hola mundo")
    assert chunk.document_id == "docid123"
    assert chunk.ocr_applied is False


def test_chunk_to_dict_has_exact_fields():
    chunk = Chunk.create(
        document_id="docid123",
        text="texto",
        page=2,
        chapter=None,
        title=None,
        author=None,
        source_file="f.pdf",
        chunk_index=1,
        ocr_applied=True,
    )
    d = chunk.to_dict()

    expected_keys = {
        "chunk_id",
        "document_id",
        "text",
        "page",
        "chapter",
        "title",
        "author",
        "source_file",
        "chunk_index",
        "char_count",
        "ocr_applied",
    }
    assert set(d.keys()) == expected_keys
    assert d["ocr_applied"] is True
    assert d["char_count"] == len("texto")


def test_two_chunks_have_different_ids():
    c1 = Chunk.create(
        document_id="d",
        text="a",
        page=1,
        chapter=None,
        title=None,
        author=None,
        source_file="f.pdf",
        chunk_index=0,
        ocr_applied=False,
    )
    c2 = Chunk.create(
        document_id="d",
        text="a",
        page=1,
        chapter=None,
        title=None,
        author=None,
        source_file="f.pdf",
        chunk_index=1,
        ocr_applied=False,
    )
    assert c1.chunk_id != c2.chunk_id


def test_processing_result_defaults():
    result = ProcessingResult(source_file="f.pdf", success=True)
    assert result.chunks == []
    assert result.warnings == []
    assert result.error is None
