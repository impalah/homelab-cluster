from whisper_service.infrastructure import whisper_model as whisper_model_module
from whisper_service.infrastructure.whisper_model import get_model, load_model, set_model


def test_load_model_uses_configured_device_when_it_succeeds(monkeypatch):
    created: list[tuple[str, str, str]] = []

    def fake_whisper_model(name: str, device: str, compute_type: str) -> str:
        created.append((name, device, compute_type))
        return "fake-model"

    monkeypatch.setattr(whisper_model_module, "WhisperModel", fake_whisper_model)

    result = load_model("large-v3", "cuda", "float16")

    assert result == "fake-model"
    assert created == [("large-v3", "cuda", "float16")]


def test_load_model_falls_back_to_cpu_when_configured_device_fails(monkeypatch):
    calls: list[tuple[str, str]] = []

    def fake_whisper_model(name: str, device: str, compute_type: str) -> str:
        calls.append((device, compute_type))
        if device == "cuda":
            raise RuntimeError("CUDA no disponible")
        return "fake-model-cpu"

    monkeypatch.setattr(whisper_model_module, "WhisperModel", fake_whisper_model)

    result = load_model("large-v3", "cuda", "float16")

    assert result == "fake-model-cpu"
    assert calls == [
        ("cuda", "float16"),
        ("cpu", whisper_model_module._CPU_FALLBACK_COMPUTE_TYPE),
    ]


def test_set_and_get_model_share_module_state(monkeypatch):
    monkeypatch.setattr(whisper_model_module, "_model", None)

    assert get_model() is None

    set_model("some-model")

    assert get_model() == "some-model"
