from markitdown_service.config import settings
from markitdown_service.infrastructure.document_converter import DocumentConverter
from markitdown_service.services.conversion_service import ConversionService

# Instanciado una sola vez (igual que antes en main.py) — MarkItDown() no es
# barato de crear y no tiene estado por-request.
_converter = DocumentConverter()


def get_conversion_service() -> ConversionService:
    return ConversionService(_converter, settings.max_file_size)
