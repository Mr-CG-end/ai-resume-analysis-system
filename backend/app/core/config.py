from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_version: str = "0.1.0"
    ai_api_key: str | None = None
    ai_base_url: str | None = None
    ai_model: str | None = None
    ai_timeout_seconds: float = Field(default=20.0, gt=0)
    redis_url: str | None = None
    max_pdf_bytes: int = 10_485_760
    max_pdf_pages: int = 30
    max_resume_chars: int = 100_000

    @property
    def ai_configured(self) -> bool:
        """Return whether the complete model-provider tuple is present."""
        return all(
            value is not None and value.strip()
            for value in (self.ai_api_key, self.ai_base_url, self.ai_model)
        )


def get_settings() -> Settings:
    """Load settings at request time so environment changes are immediately visible."""
    return Settings()
