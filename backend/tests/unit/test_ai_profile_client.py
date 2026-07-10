from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.services.ai_profile import AiExtractionError, OpenAiProfileExtractor

VALID_PAYLOAD: dict[str, object] = {
    "name": {"value": "张三", "evidence": "姓名：张三"},
    "phone": {"value": None, "evidence": None},
    "email": {"value": "candidate@example.test", "evidence": "candidate@example.test"},
    "address": {"value": None, "evidence": None},
    "job_intention": {"value": None, "evidence": None},
    "expected_salary": {"value": None, "evidence": None},
    "education": [],
    "projects": [],
    "employment_periods": [],
}


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "ai_api_key": "secret-test-key",
        "ai_base_url": "https://ai.example.test/v1/",
        "ai_model": "profile-model",
        "ai_timeout_seconds": 0.5,
    }
    values.update(overrides)
    return Settings(**values)


def _completion(payload: object = VALID_PAYLOAD) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": json.dumps(payload)}}]},
    )


class ClosingMockTransport(httpx.MockTransport):
    closed = False

    async def aclose(self) -> None:
        self.closed = True
        await super().aclose()


@pytest.mark.parametrize(
    ("overrides", "configured"),
    [
        ({}, True),
        ({"ai_api_key": None}, False),
        ({"ai_base_url": None}, False),
        ({"ai_model": None}, False),
        ({"ai_api_key": "   "}, False),
    ],
)
def test_ai_configured_requires_complete_nonblank_tuple(
    overrides: dict[str, object], configured: bool
) -> None:
    assert _settings(**overrides).ai_configured is configured


def test_ai_timeout_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        _settings(ai_timeout_seconds=0)


@pytest.mark.asyncio
async def test_extract_posts_strict_prompt_and_validates_payload() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _completion()

    transport = ClosingMockTransport(handler)
    result = await OpenAiProfileExtractor(_settings(), transport=transport).extract(
        "姓名：张三\ncandidate@example.test"
    )

    assert result.name.value == "张三"
    assert result.email.value == "candidate@example.test"
    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == "https://ai.example.test/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer secret-test-key"
    assert request.extensions["timeout"] == {
        "connect": 0.5,
        "read": 0.5,
        "write": 0.5,
        "pool": 0.5,
    }
    body = json.loads(request.content)
    assert body["model"] == "profile-model"
    assert body["temperature"] == 0
    assert body["response_format"] == {"type": "json_object"}
    assert "profile-v1" in body["messages"][0]["content"]
    assert "untrusted" in body["messages"][0]["content"].lower()
    assert "姓名：张三" in body["messages"][1]["content"]
    assert transport.closed is True


@pytest.mark.asyncio
async def test_extract_retries_transport_timeout_twice_with_one_client() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("private timeout detail", request=request)

    transport = ClosingMockTransport(handler)
    with pytest.raises(AiExtractionError, match="^AI profile extraction failed$"):
        await OpenAiProfileExtractor(_settings(), transport=transport).extract("private resume")

    assert attempts == 2
    assert transport.closed is True


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [408, 429, 500, 502, 503, 504])
async def test_extract_retries_retryable_status_then_succeeds(status_code: int) -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(status_code) if attempts == 1 else _completion()

    result = await OpenAiProfileExtractor(
        _settings(), transport=httpx.MockTransport(handler)
    ).extract("resume")

    assert result.name.value == "张三"
    assert attempts == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "first_response",
    [
        lambda: httpx.Response(200, content=b"not-json"),
        lambda: httpx.Response(200, json={"choices": []}),
        lambda: _completion({"name": {"value": None, "evidence": None}}),
    ],
    ids=["non-json", "invalid-shape", "invalid-schema"],
)
async def test_extract_retries_invalid_provider_response(
    first_response: Callable[[], httpx.Response],
) -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return first_response() if attempts == 1 else _completion()

    result = await OpenAiProfileExtractor(
        _settings(), transport=httpx.MockTransport(handler)
    ).extract("resume")

    assert result.name.value == "张三"
    assert attempts == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [400, 401, 403, 404, 422])
async def test_extract_does_not_retry_other_client_errors(status_code: int) -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(status_code, text="private provider response")

    with pytest.raises(AiExtractionError, match="^AI profile extraction failed$"):
        await OpenAiProfileExtractor(_settings(), transport=httpx.MockTransport(handler)).extract(
            "private resume"
        )

    assert attempts == 1


@pytest.mark.asyncio
async def test_extract_returns_safe_error_without_logging_sensitive_data(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"raw-provider-secret")

    with pytest.raises(AiExtractionError) as exc_info:
        await OpenAiProfileExtractor(_settings(), transport=httpx.MockTransport(handler)).extract(
            "resume-personal-data"
        )

    combined = f"{exc_info.value} {caplog.text}"
    assert "secret-test-key" not in combined
    assert "raw-provider-secret" not in combined
    assert "resume-personal-data" not in combined


@pytest.mark.asyncio
async def test_extract_rejects_missing_configuration_without_network() -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return _completion()

    with pytest.raises(AiExtractionError):
        await OpenAiProfileExtractor(
            _settings(ai_model=None), transport=httpx.MockTransport(handler)
        ).extract("resume")

    assert attempts == 0


@pytest.mark.asyncio
async def test_extract_does_not_swallow_unknown_programming_errors() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise RuntimeError("programming error")

    with pytest.raises(RuntimeError, match="programming error"):
        await OpenAiProfileExtractor(_settings(), transport=httpx.MockTransport(handler)).extract(
            "resume"
        )
