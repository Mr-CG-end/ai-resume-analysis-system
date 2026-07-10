import logging
from time import perf_counter
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, status

from app.api.upload import parse_pdf_upload
from app.core.config import Settings, get_settings
from app.schemas.resume import DocumentMetadata, ResumeSnapshot
from app.services.ai_profile import OpenAiProfileExtractor
from app.services.profile import ProfileExtractor, analyze_profile

router = APIRouter(tags=["resumes"])
logger = logging.getLogger(__name__)


def get_profile_extractor(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ProfileExtractor | None:
    if not settings.ai_configured:
        return None
    return OpenAiProfileExtractor(settings)


@router.post(
    "/resumes",
    response_model=ResumeSnapshot,
    status_code=status.HTTP_201_CREATED,
)
async def create_resume_snapshot(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    extractor: Annotated[ProfileExtractor | None, Depends(get_profile_extractor)],
) -> ResumeSnapshot:
    started_at = perf_counter()
    parsed = await parse_pdf_upload(
        request,
        max_bytes=settings.max_pdf_bytes,
        max_pages=settings.max_pdf_pages,
        max_chars=settings.max_resume_chars,
    )
    analysis = await analyze_profile(parsed.cleaned_text, extractor)
    snapshot = ResumeSnapshot(
        resume_id=f"res_{uuid4()}",
        document=DocumentMetadata(
            filename=parsed.filename,
            page_count=parsed.page_count,
            character_count=parsed.character_count,
        ),
        cleaned_text=parsed.cleaned_text,
        profile=analysis.profile,
        warnings=list(analysis.warnings),
        degraded=analysis.degraded,
        cached=False,
    )
    logger.info(
        "resume_analyzed",
        extra={
            "event": "resume_analyzed",
            "request_id": getattr(request.state, "request_id", None),
            "duration_ms": round((perf_counter() - started_at) * 1000),
            "page_count": parsed.page_count,
            "character_count": parsed.character_count,
            "model": settings.ai_model if extractor is not None else None,
            "degraded": analysis.degraded,
            "cached": False,
        },
    )
    return snapshot
