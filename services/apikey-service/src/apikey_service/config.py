from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APIKEY_")

    host: str = "0.0.0.0"
    port: int = 8090

    # --- Logging (Loguru) ----------------------------------------------
    log_level: str = "INFO"
    log_format: Literal["text", "json"] = "text"

    # postgres-main en retaco, base de datos aislada creada con
    # shared/scripts/create-postgres-db.sh (ver docs/06-instalacion-pi1-dns.md)
    database_url: str = "postgresql+asyncpg://apikeys:CHANGE_ME@192.168.1.174:5432/apikeys"

    # Protege POST/GET/DELETE /keys — nunca protege /validate (lo llama nginx
    # en cada petición de cualquier servicio protegido, sin credencial de admin)
    admin_token: str = "CHANGE_ME"

    # OTLP HTTP del otel-collector en pi-obs — solo para el logger de
    # auditoría (intentos de acceso fallidos), no para los logs generales
    # del servicio (esos van por loguru a stdout)
    otel_exporter_otlp_logs_endpoint: str = "http://192.168.1.171:4318/v1/logs"
    otel_service_name: str = "apikey-service"


settings = Settings()
