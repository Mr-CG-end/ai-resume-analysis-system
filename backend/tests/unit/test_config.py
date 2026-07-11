import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_cors_origins_default_to_local_vite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    settings = Settings(_env_file=None)
    assert settings.allowed_cors_origins == ("http://localhost:5173",)


def test_cors_origins_are_trimmed_and_split() -> None:
    settings = Settings(
        _env_file=None,
        cors_origins="http://localhost:5173, https://example.github.io ",
    )
    assert settings.allowed_cors_origins == (
        "http://localhost:5173",
        "https://example.github.io",
    )


@pytest.mark.parametrize(
    "value",
    ["", "   ", "*,http://localhost:5173", "http://localhost:5173,"],
)
def test_cors_origins_reject_empty_and_wildcard(value: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, cors_origins=value)
