"""Reglas de negocio de la transcripción: validación de modelo cargado/tipo
de contenido/audio no vacío, orquestación del executor y traducción de
errores. No conoce FastAPI ni HTTPException — eso lo traduce el controller
a partir de las excepciones de aquí (mismo patrón que
apikey_service.services.apikey_service)."""

import asyncio
import io
from dataclasses import dataclass

from faster_whisper import WhisperModel
from loguru import logger

from whisper_service.infrastructure.whisper_model import run_transcription

# Content-types soportados. faster-whisper decodifica el audio internamente
# vía PyAV (FFmpeg estático embebido en el wheel), así que en la práctica
# soporta más formatos de los que aceptamos aquí — esta lista es la barrera
# de entrada explícita del API, no una limitación real del decodificador.
ALLOWED_CONTENT_TYPES = {
    "audio/mpeg",
    "audio/wav",
    "audio/ogg",
    "audio/mp4",
    "audio/flac",
    "audio/x-flac",
    "video/mp4",
}


class TranscriptionError(Exception):
    """Base de los errores de transcripción — el controller la traduce a HTTPException."""


class ModelNotLoadedError(TranscriptionError):
    pass


class UnsupportedContentTypeError(TranscriptionError):
    def __init__(self, content_type: str) -> None:
        self.content_type = content_type
        super().__init__(f"Tipo de contenido no soportado: {content_type}")


class EmptyAudioError(TranscriptionError):
    pass


class TranscriptionFailedError(TranscriptionError):
    pass


@dataclass
class TranscriptionResult:
    text: str
    language: str
    language_probability: float
    duration: float


class TranscriptionService:
    def __init__(self, model: WhisperModel | None) -> None:
        self._model = model

    async def transcribe(
        self,
        content: bytes,
        content_type: str | None,
        filename: str | None,
        language: str,
        task: str,
    ) -> TranscriptionResult:
        if self._model is None:
            raise ModelNotLoadedError()

        if content_type and content_type not in ALLOWED_CONTENT_TYPES:
            raise UnsupportedContentTypeError(content_type)

        if len(content) == 0:
            raise EmptyAudioError()

        logger.info(
            "Transcribiendo archivo: nombre={} tamaño={} bytes idioma={}",
            filename,
            len(content),
            language,
        )

        try:
            audio_buffer = io.BytesIO(content)
            loop = asyncio.get_running_loop()
            full_text, info = await loop.run_in_executor(
                None, run_transcription, self._model, audio_buffer, language, task
            )
            logger.info("Transcripción completada. Duración audio: {:.1f}s", info.duration)

            return TranscriptionResult(
                text=full_text,
                language=info.language,
                language_probability=round(info.language_probability, 4),
                duration=round(info.duration, 2),
            )

        except Exception as exc:
            logger.error("Error durante la transcripción: {}", exc)
            raise TranscriptionFailedError(str(exc)) from exc
