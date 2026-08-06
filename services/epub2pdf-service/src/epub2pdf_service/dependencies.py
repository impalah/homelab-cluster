from epub2pdf_service.config import settings
from epub2pdf_service.infrastructure.calibre_converter import CalibreConverter
from epub2pdf_service.services.conversion_service import ConversionService

# Instanciado una sola vez — CalibreConverter no tiene estado por-request,
# igual que DocumentConverter en markitdown-service.
_converter = CalibreConverter(settings.calibre_binary)


def get_conversion_service() -> ConversionService:
    return ConversionService(
        _converter,
        settings.conversion_timeout_seconds,
        settings.max_filename_collision_attempts,
    )
