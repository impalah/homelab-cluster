from markitdown_service.config import Settings, settings


def test_default_values():
    assert settings.markitdown_port == 8001
    assert settings.markitdown_log_level == "INFO"
    assert settings.host == "0.0.0.0"
    assert settings.max_file_size == 52_428_800


def test_env_vars_override_defaults(monkeypatch):
    monkeypatch.setenv("MARKITDOWN_PORT", "9999")
    monkeypatch.setenv("MAX_FILE_SIZE", "1024")

    s = Settings()

    assert s.markitdown_port == 9999
    assert s.max_file_size == 1024


def test_env_vars_are_case_insensitive(monkeypatch):
    monkeypatch.setenv("markitdown_log_level", "DEBUG")

    s = Settings()

    assert s.markitdown_log_level == "DEBUG"
