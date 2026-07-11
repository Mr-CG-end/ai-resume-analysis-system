import logging
from time import perf_counter
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, status

from app.core.config import Settings, get_settings
from app.domain.errors import JdKeywordsNotFoundError, JdTooLongError, JdTooShortError
from app.schemas.match import MatchEvidence, MatchRequest, MatchResponse, ScoreBreakdown
from app.services.ai_match import MatchAnalyzer, OpenAiMatchAnalyzer
from app.services.jd import JdValidationError, extract_jd_keywords
from app.services.matching import analyze_match

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


def _summary(skill_score: int, experience_score: int) -> str:
    if skill_score >= 75 and experience_score >= 75:
        return "技能覆盖和经历相关性均较高。"
    if skill_score >= 75:
        return "技能覆盖较高，经历相关性仍有提升空间。"
    if experience_score >= 75:
        return "经历相关性较高，仍有部分岗位技能缺失。"
    return "技能覆盖和经历相关性均有限，建议进一步核实。"


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
) -> MatchResponse:
    started_at = perf_counter()
    try:
        keywords = extract_jd_keywords(payload.job_description)
    except JdValidationError as exc:
        raise _JD_ERRORS[exc.code]() from None

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
        scores=ScoreBreakdown(
            skill_match=analysis.skill_score,
            experience_relevance=analysis.experience_score,
            overall=analysis.overall_score,
        ),
        evidence=[MatchEvidence(dimension="experience", text=text) for text in analysis.evidence],
        summary=_summary(analysis.skill_score, analysis.experience_score),
        method=analysis.method,
        warnings=list(analysis.warnings),
        degraded=analysis.degraded,
        cached=False,
    )
    logger.info(
        "match_analyzed",
        extra={
            "event": "match_analyzed",
            "request_id": getattr(request.state, "request_id", None),
            "duration_ms": round((perf_counter() - started_at) * 1000),
            "keyword_count": len(keywords.skills),
            "evidence_count": len(analysis.evidence),
            "method": analysis.method,
            "model": settings.ai_model if analyzer is not None else None,
            "degraded": analysis.degraded,
            "cached": False,
        },
    )
    return response
