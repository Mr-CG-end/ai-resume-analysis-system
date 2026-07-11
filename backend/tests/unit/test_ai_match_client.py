from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx
import pytest

from app.core.config import Settings
from app.schemas.ai_match import AiExperiencePayload
from app.services.ai_match import MAX_AI_RESPONSE_BYTES, AiMatchingError, OpenAiMatchAnalyzer


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "ai_api_key": "secret",
        "ai_base_url": "https://ai.example/v1/",
        "ai_model": "match-model",
        "ai_timeout_seconds": 0.5,
    }
    values.update(overrides)
    return Settings(**values)


def _completion(payload: object) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(payload)}}]})


class ClosingStream(httpx.AsyncByteStream):
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.closed = False
        self.iterated = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        self.iterated = True
        yield self.data

    async def aclose(self) -> None:
        self.closed = True


def test_payload_is_strict_and_bounded() -> None:
    assert (
        AiExperiencePayload(experience_relevance=83, evidence=["负责后端开发"]).experience_relevance
        == 83
    )
    with pytest.raises(ValueError):
        AiExperiencePayload.model_validate(
            {"experience_relevance": 101, "evidence": [], "summary": "no"}
        )
    with pytest.raises(ValueError):
        AiExperiencePayload(experience_relevance=50, evidence=["x"] * 6)


@pytest.mark.asyncio
async def test_analyze_posts_untrusted_json_and_filters_exact_evidence() -> None:
    requests: list[httpx.Request] = []
    resume = "负责后端开发\n使用 Python 构建 API"

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _completion(
            {
                "experience_relevance": 87,
                "evidence": ["负责后端开发", "幻觉", "负责后端开发", "使用 Python 构建 API"],
            }
        )

    result = await OpenAiMatchAnalyzer(_settings(), transport=httpx.MockTransport(handler)).analyze(
        "招聘后端工程师", resume
    )
    assert result == AiExperiencePayload(
        experience_relevance=87, evidence=["负责后端开发", "使用 Python 构建 API"]
    )
    request = requests[0]
    assert str(request.url) == "https://ai.example/v1/chat/completions"
    assert request.headers["Accept-Encoding"] == "identity"
    body = json.loads(request.content)
    assert body["temperature"] == 0
    assert body["enable_thinking"] is False
    assert body["response_format"] == {"type": "json_object"}
    assert "match-v1" in body["messages"][0]["content"]
    assert json.dumps("招聘后端工程师", ensure_ascii=False) in body["messages"][1]["content"]
    assert json.dumps(resume, ensure_ascii=False) in body["messages"][1]["content"]


@pytest.mark.asyncio
async def test_no_exact_evidence_retries_then_fails() -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return _completion({"experience_relevance": 99, "evidence": ["hallucination"]})

    with pytest.raises(AiMatchingError, match="^AI experience matching failed$"):
        await OpenAiMatchAnalyzer(_settings(), transport=httpx.MockTransport(handler)).analyze(
            "岗位", "真实简历"
        )
    assert attempts == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504])
async def test_retryable_status_retries_once(status: int) -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return (
            httpx.Response(status)
            if attempts == 1
            else _completion({"experience_relevance": 70, "evidence": ["后端开发"]})
        )

    result = await OpenAiMatchAnalyzer(_settings(), transport=httpx.MockTransport(handler)).analyze(
        "岗位", "后端开发"
    )
    assert result.experience_relevance == 70 and attempts == 2


@pytest.mark.asyncio
async def test_compressed_response_is_rejected_before_read() -> None:
    streams: list[ClosingStream] = []

    def handler(_: httpx.Request) -> httpx.Response:
        stream = ClosingStream(b"private")
        streams.append(stream)
        return httpx.Response(200, headers={"Content-Encoding": "gzip"}, stream=stream)

    with pytest.raises(AiMatchingError):
        await OpenAiMatchAnalyzer(_settings(), transport=httpx.MockTransport(handler)).analyze(
            "岗位", "简历"
        )
    assert len(streams) == 2 and all(s.closed and not s.iterated for s in streams)


@pytest.mark.asyncio
async def test_response_over_one_mib_is_rejected() -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(200, stream=ClosingStream(b" " * (MAX_AI_RESPONSE_BYTES + 1)))

    with pytest.raises(AiMatchingError):
        await OpenAiMatchAnalyzer(_settings(), transport=httpx.MockTransport(handler)).analyze(
            "岗位", "简历"
        )
    assert attempts == 2


@pytest.mark.asyncio
async def test_missing_config_avoids_network_and_unknown_errors_propagate() -> None:
    attempts = 0

    def counting(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return _completion({})

    with pytest.raises(AiMatchingError):
        await OpenAiMatchAnalyzer(
            _settings(ai_api_key=None), transport=httpx.MockTransport(counting)
        ).analyze("岗位", "简历")
    assert attempts == 0

    def broken(_: httpx.Request) -> httpx.Response:
        raise RuntimeError("programming error")

    with pytest.raises(RuntimeError, match="programming error"):
        await OpenAiMatchAnalyzer(_settings(), transport=httpx.MockTransport(broken)).analyze(
            "岗位", "简历"
        )
