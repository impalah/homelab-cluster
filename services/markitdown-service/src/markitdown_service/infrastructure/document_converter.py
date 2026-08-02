"""Envoltorio sobre la librería MarkItDown — aísla la dependencia externa
del resto de capas (el service no importa "markitdown" directamente)."""

from markitdown import MarkItDown


class DocumentConverter:
    def __init__(self) -> None:
        self._markitdown = MarkItDown()

    def convert(self, file_path: str) -> str:
        result = self._markitdown.convert(file_path)
        return result.text_content
