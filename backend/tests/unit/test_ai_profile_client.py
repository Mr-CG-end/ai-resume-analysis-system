from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Callable

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.schemas.ai_profile import CompactAiProfilePayload
from app.services.ai_profile import (
    MAX_AI_RESPONSE_BYTES,
    AiExtractionError,
    OpenAiProfileExtractor,
)

VALID_PAYLOAD: dict[str, object] = {
    "name": "张三",
    "phone": None,
    "email": "candidate@example.test",
    "address": None,
    "job_intention": None,
    "expected_salary": None,
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


def _completion_bytes(payload: object = VALID_PAYLOAD) -> bytes:
    return json.dumps(
        {"choices": [{"message": {"content": json.dumps(payload)}}]},
        separators=(",", ":"),
    ).encode()


def _sized_completion(size: int) -> bytes:
    body = _completion_bytes()
    assert len(body) <= size
    return body + (b" " * (size - len(body)))


class ClosingByteStream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks
        self.closed = False
        self.iterated = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        self.iterated = True
        for chunk in self._chunks:
            await asyncio.sleep(0)
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


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


@pytest.mark.parametrize(
    "timeout_seconds",
    [0, 61, float("inf"), float("-inf"), float("nan")],
    ids=["zero", "above-maximum", "positive-infinity", "negative-infinity", "nan"],
)
def test_ai_timeout_must_be_finite_and_within_range(timeout_seconds: float) -> None:
    with pytest.raises(ValidationError):
        _settings(ai_timeout_seconds=timeout_seconds)


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
    assert request.headers["Accept-Encoding"] == "identity"
    assert request.extensions["timeout"] == {
        "connect": 0.5,
        "read": 0.5,
        "write": 0.5,
        "pool": 0.5,
    }
    body = json.loads(request.content)
    assert body["model"] == "profile-model"
    assert body["temperature"] == 0
    assert body["enable_thinking"] is False
    assert body["max_tokens"] == 4096
    assert body["response_format"] == {"type": "json_object"}
    assert "profile-v3" in body["messages"][0]["content"]
    assert "year-only" in body["messages"][0]["content"]
    assert "untrusted" in body["messages"][0]["content"].lower()
    assert (
        json.dumps(CompactAiProfilePayload.model_json_schema(), ensure_ascii=False)
        in body["messages"][1]["content"]
    )
    assert "姓名：张三" in body["messages"][1]["content"]
    assert transport.closed is True


@pytest.mark.asyncio
async def test_extract_drops_year_only_employment_period_without_losing_profile() -> None:
    payload = {
        **VALID_PAYLOAD,
        "employment_periods": [
            {
                "start_date": "2022",
                "end_date": "2025",
                "evidence": "2022-2025",
            }
        ],
    }

    def handler(_: httpx.Request) -> httpx.Response:
        return _completion(payload)

    result = await OpenAiProfileExtractor(
        _settings(), transport=httpx.MockTransport(handler)
    ).extract("姓名：张三\n2022-2025")

    assert result.name.value == "张三"
    assert result.employment_periods == []


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
async def test_extract_accepts_exactly_one_mib_identity_response_in_chunks() -> None:
    body = _sized_completion(MAX_AI_RESPONSE_BYTES)
    stream = ClosingByteStream([body[:17], body[17:524_289], body[524_289:]])

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=stream)

    result = await OpenAiProfileExtractor(
        _settings(), transport=httpx.MockTransport(handler)
    ).extract("resume")

    assert result.name.value == "张三"
    assert stream.closed is True


@pytest.mark.asyncio
async def test_extract_retries_identity_response_one_byte_over_limit() -> None:
    body = _sized_completion(MAX_AI_RESPONSE_BYTES + 1)
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(200, stream=ClosingByteStream([body]))

    with pytest.raises(AiExtractionError, match="^AI profile extraction failed$"):
        await OpenAiProfileExtractor(_settings(), transport=httpx.MockTransport(handler)).extract(
            "resume"
        )

    assert attempts == 2


@pytest.mark.asyncio
async def test_extract_rejects_compressed_response_before_reading_stream() -> None:
    attempts = 0
    streams: list[ClosingByteStream] = []

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        stream = ClosingByteStream([b"small-compressed-payload"])
        streams.append(stream)
        return httpx.Response(
            200,
            headers={"Content-Encoding": "gzip"},
            stream=stream,
        )

    with pytest.raises(AiExtractionError, match="^AI profile extraction failed$"):
        await OpenAiProfileExtractor(_settings(), transport=httpx.MockTransport(handler)).extract(
            "resume"
        )

    assert attempts == 2
    assert all(stream.closed for stream in streams)
    assert not any(stream.iterated for stream in streams)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_body",
    [b"\xff", b"not-json"],
    ids=["invalid-utf8", "non-json"],
)
async def test_extract_retries_invalid_encoding_or_json_twice_then_fails(
    invalid_body: bytes,
) -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(200, content=invalid_body)

    with pytest.raises(AiExtractionError, match="^AI profile extraction failed$"):
        await OpenAiProfileExtractor(_settings(), transport=httpx.MockTransport(handler)).extract(
            "resume"
        )

    assert attempts == 2


@pytest.mark.asyncio
async def test_extract_timeout_covers_response_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return _completion()

    def slow_parse(_: bytes) -> object:
        time.sleep(0.2)
        return VALID_PAYLOAD

    monkeypatch.setattr(OpenAiProfileExtractor, "_parse_payload", staticmethod(slow_parse))

    with pytest.raises(AiExtractionError, match="^AI profile extraction failed$"):
        await OpenAiProfileExtractor(
            _settings(ai_timeout_seconds=0.1),
            transport=httpx.MockTransport(handler),
        ).extract("resume")

    assert 1 <= attempts <= 2


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
