"""Envoltorio sobre faster-whisper — aísla la librería externa del resto de
capas (el service no importa faster_whisper directamente)."""

import io

from faster_whisper import WhisperModel
from faster_whisper.transcribe import TranscriptionInfo
from loguru import logger

# Fallback si la carga en GPU falla (driver/CUDA no disponible, VRAM
# insuficiente, etc.): "int8" es el compute_type portable en CPU (float16
# no está soportado ahí). Mucho más lento que GPU — es red de seguridad para
# no caerse del todo, no un modo de operación normal.
_CPU_FALLBACK_COMPUTE_TYPE = "int8"

# Modelo cargado en el lifespan de la app — vive aquí (no en main.py) para
# que el service pueda leerlo vía get_model() sin depender de un global de
# otro módulo.
_model: WhisperModel | None = None


def load_model(model_name: str, device: str, compute_type: str) -> WhisperModel:
    """Carga el modelo en el device pedido; si falla, reintenta en CPU."""
    try:
        return WhisperModel(model_name, device=device, compute_type=compute_type)
    except Exception as exc:
        logger.warning(
            "Fallo al cargar el modelo en device={} ({}) — reintentando en CPU (compute_type={}).",
            device,
            exc,
            _CPU_FALLBACK_COMPUTE_TYPE,
        )
        return WhisperModel(model_name, device="cpu", compute_type=_CPU_FALLBACK_COMPUTE_TYPE)


def set_model(model: WhisperModel | None) -> None:
    global _model
    _model = model


def get_model() -> WhisperModel | None:
    return _model


def run_transcription(
    model: WhisperModel, audio_buffer: io.BytesIO, language: str, task: str
) -> tuple[str, TranscriptionInfo]:
    """Transcribe y consume el generador de segmentos — pensada para correr
    en un executor (thread aparte), no directamente en el event loop.

    faster-whisper devuelve "segments" como un generador perezoso: el trabajo
    pesado no ocurre en la llamada a "model.transcribe()" (que retorna casi
    al instante), sino al iterar los segmentos — por eso ambas cosas van
    juntas aquí dentro, y no solo la llamada a transcribe().
    """
    segments, info = model.transcribe(
        audio_buffer,
        language=language,
        task=task,
        beam_size=5,
        vad_filter=True,
    )
    full_text = " ".join(seg.text.strip() for seg in segments)
    return full_text, info
