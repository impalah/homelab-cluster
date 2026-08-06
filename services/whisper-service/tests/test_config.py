from whisper_service.config import Settings, settings


def test_default_values():
    assert settings.whisper_model == "large-v3"
    assert settings.whisper_device == "cuda"
    assert settings.whisper_compute_type == "float16"
    assert settings.whisper_language == "es"
    assert settings.host == "0.0.0.0"
    assert settings.port == 9800
    assert settings.log_level == "INFO"
    assert settings.log_format == "text"


def test_env_vars_override_defaults(monkeypatch):
    monkeypatch.setenv("WHISPER_MODEL", "medium")
    monkeypatch.setenv("WHISPER_DEVICE", "cpu")
    monkeypatch.setenv("PORT", "9801")

    s = Settings()

    assert s.whisper_model == "medium"
    assert s.whisper_device == "cpu"
    assert s.port == 9801


def test_env_vars_are_case_insensitive(monkeypatch):
    monkeypatch.setenv("whisper_language", "en")

    s = Settings()

    assert s.whisper_language == "en"
