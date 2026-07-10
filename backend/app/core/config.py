from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_version: str = "0.1.0"
    ai_api_key: str | None = None
    redis_url: str | None = None
    max_pdf_bytes: int = 10_485_760
    max_pdf_pages: int = 30
    max_resume_chars: int = 100_000


def get_settings() -> Settings:
    """Load settings at request time so environment changes are immediately visible."""
    return Settings()
