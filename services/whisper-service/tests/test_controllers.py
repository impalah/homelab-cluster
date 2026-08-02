import io

from whisper_service import __version__
from whisper_service.infrastructure import whisper_model as whisper_model_module


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


def test_health_returns_config_values(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "version": __version__,
        "service": "whisper-service",
        "model": "large-v3",
        "device": "cuda",
        "compute_type": "float16",
        "language": "es",
    }


def test_transcribe_returns_503_when_model_not_loaded(client, monkeypatch):
    monkeypatch.setattr(whisper_model_module, "_model", None)

    response = client.post(
        "/transcribe",
        files={"file": ("audio.mp3", io.BytesIO(b"fake audio bytes"), "audio/mpeg")},
    )

    assert response.status_code == 503
    assert "no cargado" in response.json()["detail"]


def test_transcribe_success(client, monkeypatch):
    fake_model = _FakeModel()
    monkeypatch.setattr(whisper_model_module, "_model", fake_model)

    response = client.post(
        "/transcribe",
        files={"file": ("audio.mp3", io.BytesIO(b"fake audio bytes"), "audio/mpeg")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "Hola mundo"
    assert body["language"] == "es"
    assert body["language_probability"] == 0.9877
    assert body["duration"] == 12.35
    assert body["model"] == "large-v3"
    assert fake_model.last_call_kwargs["language"] == "es"
    assert fake_model.last_call_kwargs["task"] == "transcribe"


def test_transcribe_uses_language_form_field_over_default(client, monkeypatch):
    fake_model = _FakeModel()
    monkeypatch.setattr(whisper_model_module, "_model", fake_model)

    response = client.post(
        "/transcribe",
        files={"file": ("audio.mp3", io.BytesIO(b"fake audio bytes"), "audio/mpeg")},
        data={"language": "en", "task": "translate"},
    )

    assert response.status_code == 200
    assert fake_model.last_call_kwargs["language"] == "en"
    assert fake_model.last_call_kwargs["task"] == "translate"


def test_transcribe_rejects_empty_file(client, monkeypatch):
    monkeypatch.setattr(whisper_model_module, "_model", _FakeModel())

    response = client.post(
        "/transcribe",
        files={"file": ("audio.mp3", io.BytesIO(b""), "audio/mpeg")},
    )

    assert response.status_code == 400
    assert "vac" in response.json()["detail"].lower()


def test_transcribe_rejects_unrecognized_content_type(client, monkeypatch):
    monkeypatch.setattr(whisper_model_module, "_model", _FakeModel())

    response = client.post(
        "/transcribe",
        files={
            "file": ("audio.weird", io.BytesIO(b"fake audio bytes"), "application/octet-stream")
        },
    )

    assert response.status_code == 415
    assert "no soportado" in response.json()["detail"]


def test_transcribe_accepts_file_without_content_type(client, monkeypatch):
    # httpx no siempre puede adivinar un content-type (ej. sin extensión
    # reconocible) — sin content-type no hay nada que rechazar en el chequeo
    # de tipo, así que sigue adelante e intenta transcribir igualmente.
    fake_model = _FakeModel()
    monkeypatch.setattr(whisper_model_module, "_model", fake_model)

    response = client.post(
        "/transcribe",
        files={"file": ("noext", io.BytesIO(b"fake audio bytes"), "")},
    )

    assert response.status_code == 200


def test_transcribe_returns_500_on_transcription_error(client, monkeypatch):
    fake_model = _FakeModel(raise_exc=RuntimeError("boom"))
    monkeypatch.setattr(whisper_model_module, "_model", fake_model)

    response = client.post(
        "/transcribe",
        files={"file": ("audio.mp3", io.BytesIO(b"fake audio bytes"), "audio/mpeg")},
    )

    assert response.status_code == 500
    assert "boom" in response.json()["detail"]
