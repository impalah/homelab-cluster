from apikey_service.config import Settings, settings


def test_default_values_not_overridden_by_test_env():
    # host/port no se tocan en conftest.py, deben conservar el default real
    assert settings.host == "0.0.0.0"
    assert settings.port == 8090
    assert settings.otel_service_name == "apikey-service"


def test_env_prefix_applies_to_new_instances(monkeypatch):
    monkeypatch.setenv("APIKEY_PORT", "9999")
    s = Settings()
    assert s.port == 9999


def test_test_env_vars_from_conftest_are_applied():
    # Estas sí las fija conftest.py antes de importar nada
    assert settings.admin_token == "test-admin-token"
    assert settings.database_url.startswith("sqlite+aiosqlite:///")
