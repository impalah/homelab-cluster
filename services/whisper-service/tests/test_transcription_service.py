import pytest

from whisper_service.services.transcription_service import (
    EmptyAudioError,
    ModelNotLoadedError,
    TranscriptionFailedError,
    TranscriptionService,
    UnsupportedContentTypeError,
)


class _FakeSegment:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeInfo:
    def __init__(
        self, language: str = "es", language_probability: float = 0.987654, duration: float = 12.345
    ) -> None:
        self.language = language
        self.language_probability = language_probability
        self.duration = duration


class _FakeModel:
    """Sustituye a WhisperModel en los tests — nunca carga pesos ni usa CUDA."""

    def __init__(self, segments=None, info=None, raise_exc: Exception | None = None) -> None:
        self._segments = (
            segments if segments is not None else [_FakeSegment("Hola"), _FakeSegment("mundo")]
        )
        self._info = info if info is not None else _FakeInfo()
        self._raise_exc = raise_exc
        self.last_call_kwargs: dict | None = None

    def transcribe(self, audio_buffer, **kwargs):
        self.last_call_kwargs = kwargs
        if self._raise_exc is not None:
            raise self._raise_exc
        return self._segments, self._info


async def test_transcribe_raises_when_model_not_loaded():
    service = TranscriptionService(model=None)

    with pytest.raises(ModelNotLoadedError):
        await service.transcribe(b"audio", "audio/mpeg", "audio.mp3", "es", "transcribe")


async def test_transcribe_rejects_unsupported_content_type():
    service = TranscriptionService(model=_FakeModel())

    with pytest.raises(UnsupportedContentTypeError) as exc_info:
        await service.transcribe(b"audio", "application/octet-stream", "a.bin", "es", "transcribe")

    assert exc_info.value.content_type == "application/octet-stream"


async def test_transcribe_accepts_missing_content_type():
    fake_model = _FakeModel()
    service = TranscriptionService(model=fake_model)

    result = await service.transcribe(b"audio", None, "a", "es", "transcribe")

    assert result.text == "Hola mundo"


async def test_transcribe_rejects_empty_audio():
    service = TranscriptionService(model=_FakeModel())

    with pytest.raises(EmptyAudioError):
        await service.transcribe(b"", "audio/mpeg", "audio.mp3", "es", "transcribe")


async def test_transcribe_success_returns_result_and_passes_language_and_task():
    fake_model = _FakeModel()
    service = TranscriptionService(model=fake_model)

    result = await service.transcribe(b"audio bytes", "audio/mpeg", "audio.mp3", "en", "translate")

    assert result.text == "Hola mundo"
    assert result.language == "es"
    assert result.language_probability == 0.9877
    assert result.duration == 12.35
    assert fake_model.last_call_kwargs["language"] == "en"
    assert fake_model.last_call_kwargs["task"] == "translate"


async def test_transcribe_raises_transcription_failed_on_generic_error():
    fake_model = _FakeModel(raise_exc=RuntimeError("boom"))
    service = TranscriptionService(model=fake_model)

    with pytest.raises(TranscriptionFailedError) as exc_info:
        await service.transcribe(b"audio bytes", "audio/mpeg", "audio.mp3", "es", "transcribe")

    assert "boom" in str(exc_info.value)
