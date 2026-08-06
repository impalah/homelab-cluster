from pdf2chunks_service.config import settings
from pdf2chunks_service.services.chunking_strategies import get_chunking_strategy
from pdf2chunks_service.services.pdf_processing_service import PdfProcessingService


def get_processing_service() -> PdfProcessingService:
    return PdfProcessingService(
        ocr_char_threshold=settings.ocr_char_threshold,
        ocr_language=settings.ocr_language,
        chunking_strategy=get_chunking_strategy(
            settings.chunking_strategy,
            chunk_size_tokens=settings.chunk_size_tokens,
            overlap_ratio=settings.chunk_overlap_ratio,
        ),
    )
