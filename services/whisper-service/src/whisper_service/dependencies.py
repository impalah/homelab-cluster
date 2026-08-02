from whisper_service.infrastructure.whisper_model import get_model
from whisper_service.services.transcription_service import TranscriptionService


def get_transcription_service() -> TranscriptionService:
    return TranscriptionService(get_model())
