import logging
from time import perf_counter
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, status

from app.api.dependencies import get_cache_store
from app.core.config import Settings, get_settings
from app.domain.errors import JdKeywordsNotFoundError, JdTooLongError, JdTooShortError
from app.schemas.match import MatchEvidence, MatchRequest, MatchResponse, ScoreBreakdown
from app.services.ai_match import MatchAnalyzer, OpenAiMatchAnalyzer
from app.services.cache import (
    build_match_cache_key,
    deserialize_match_response,
    resume_snapshot_hash,
    serialize_cache_payload,
    stable_hash,
)
from app.services.jd import RESPONSIBILITY_LABELS, JdValidationError, extract_jd_keywords
from app.services.matching import DeterministicMatch, analyze_match, score_deterministic_match
from app.services.redis_cache import CacheStore

router = APIRouter(tags=["matches"])
logger = logging.getLogger(__name__)

_JD_ERRORS = {
    "JD_TOO_SHORT": JdTooShortError,
    "JD_TOO_LONG": JdTooLongError,
    "JD_KEYWORDS_NOT_FOUND": JdKeywordsNotFoundError,
}


def get_match_analyzer(
    settings: Annotated[Settings, Depends(get_settings)],
) -> MatchAnalyzer | None:
    if not settings.ai_configured:
        return None
    return OpenAiMatchAnalyzer(settings)


def _responsibility_labels(values: tuple[str, ...]) -> list[str]:
    return [RESPONSIBILITY_LABELS.get(value, value) for value in values]


def _summary(
    *,
    matched_skill_count: int,
    skill_count: int,
    matched_responsibility_count: int,
    responsibility_count: int,
    method: str,
    evidence_count: int,
) -> str:
    skill_detail = f"技能关键词匹配 {matched_skill_count}/{skill_count} 项"
    if method == "hybrid":
        return f"{skill_detail}；AI 结合 {evidence_count} 条简历原文证据评估经历相关性。"
    return (
        f"{skill_detail}；AI 精评未完成，经历分暂按职责关键词覆盖率 "
        f"{matched_responsibility_count}/{responsibility_count} 计算。"
    )


@router.post(
    "/matches",
    response_model=MatchResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_match(
    payload: MatchRequest,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    analyzer: Annotated[MatchAnalyzer | None, Depends(get_match_analyzer)],
    cache: Annotated[CacheStore, Depends(get_cache_store)],
) -> MatchResponse:
    started_at = perf_counter()
    try:
        keywords = extract_jd_keywords(payload.job_description)
    except JdValidationError as exc:
        raise _JD_ERRORS[exc.code]() from None

    cache_key = build_match_cache_key(
        resume_snapshot_hash(payload.resume_snapshot),
        stable_hash(keywords.normalized_text),
    )
    cached_response = deserialize_match_response(await cache.get(cache_key) or "")
    deterministic = score_deterministic_match(keywords, payload.resume_snapshot.cleaned_text)
    if cached_response is not None and _cached_match_is_valid(
        cached_response,
        keywords.skills,
        keywords.responsibilities,
        deterministic,
        payload.resume_snapshot.cleaned_text,
    ):
        cached_data = cached_response.model_dump(mode="json")
        cached_data["match_id"] = f"mat_{uuid4()}"
        cached_data["resume_id"] = payload.resume_snapshot.resume_id
        cached_data["cached"] = True
        response = MatchResponse.model_validate(cached_data)
        _log_match_result(request, settings, started_at, response, analyzer)
        return response

    analysis = await analyze_match(
        keywords=keywords,
        job_description=keywords.normalized_text,
        cleaned_text=payload.resume_snapshot.cleaned_text,
        analyzer=analyzer,
    )
    response = MatchResponse(
        match_id=f"mat_{uuid4()}",
        resume_id=payload.resume_snapshot.resume_id,
        jd_keywords=list(keywords.skills),
        matched_keywords=list(analysis.matched_keywords),
        missing_keywords=list(analysis.missing_keywords),
        responsibility_keywords=_responsibility_labels(keywords.responsibilities),
        matched_responsibilities=_responsibility_labels(analysis.matched_responsibilities),
        missing_responsibilities=_responsibility_labels(analysis.missing_responsibilities),
        scores=ScoreBreakdown(
            skill_match=analysis.skill_score,
            experience_relevance=analysis.experience_score,
            overall=analysis.overall_score,
        ),
        evidence=[MatchEvidence(dimension="experience", text=text) for text in analysis.evidence],
        summary=_summary(
            matched_skill_count=len(analysis.matched_keywords),
            skill_count=len(keywords.skills),
            matched_responsibility_count=len(analysis.matched_responsibilities),
            responsibility_count=len(keywords.responsibilities),
            method=analysis.method,
            evidence_count=len(analysis.evidence),
        ),
        method=analysis.method,
        warnings=list(analysis.warnings),
        degraded=analysis.degraded,
        cached=False,
    )
    await cache.set(
        cache_key,
        serialize_cache_payload(response),
        ttl_seconds=settings.cache_ttl_seconds,
    )
    _log_match_result(request, settings, started_at, response, analyzer)
    return response


def _log_match_result(
    request: Request,
    settings: Settings,
    started_at: float,
    response: MatchResponse,
    analyzer: MatchAnalyzer | None,
) -> None:
    logger.info(
        "match_analyzed",
        extra={
            "event": "match_analyzed",
            "request_id": getattr(request.state, "request_id", None),
            "duration_ms": round((perf_counter() - started_at) * 1000),
            "keyword_count": len(response.jd_keywords),
            "evidence_count": len(response.evidence),
            "method": response.method,
            "model": settings.ai_model if analyzer is not None else None,
            "degraded": response.degraded,
            "cached": response.cached,
        },
    )


def _cached_match_is_valid(
    response: MatchResponse,
    skills: tuple[str, ...],
    responsibilities: tuple[str, ...],
    deterministic: DeterministicMatch,
    cleaned_text: str,
) -> bool:
    if response.jd_keywords != list(skills):
        return False
    if response.matched_keywords != list(deterministic.matched_keywords):
        return False
    if response.missing_keywords != list(deterministic.missing_keywords):
        return False
    if response.responsibility_keywords != _responsibility_labels(responsibilities):
        return False
    if response.matched_responsibilities != _responsibility_labels(
        deterministic.matched_responsibilities
    ):
        return False
    if response.missing_responsibilities != _responsibility_labels(
        deterministic.missing_responsibilities
    ):
        return False
    if response.scores.skill_match != deterministic.skill_score:
        return False
    if response.summary != _summary(
        matched_skill_count=len(response.matched_keywords),
        skill_count=len(response.jd_keywords),
        matched_responsibility_count=len(response.matched_responsibilities),
        responsibility_count=len(response.responsibility_keywords),
        method=response.method,
        evidence_count=len(response.evidence),
    ):
        return False
    if response.method == "rule_fallback":
        return (
            not response.evidence
            and response.scores.experience_relevance == deterministic.experience_score
        )
    return bool(response.evidence) and all(
        item.text.strip() and item.text in cleaned_text for item in response.evidence
    )
