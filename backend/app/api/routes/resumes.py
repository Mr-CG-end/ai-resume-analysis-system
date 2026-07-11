import logging
from time import perf_counter
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, status
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import get_cache_store
from app.api.upload import read_pdf_upload
from app.core.config import Settings, get_settings
from app.domain.errors import PdfPageLimitExceededError, PdfTextTooLongError
from app.schemas.resume import DocumentMetadata, ResumeSnapshot
from app.services.ai_profile import OpenAiProfileExtractor
from app.services.cache import (
    build_extract_cache_key,
    deserialize_resume_snapshot,
    serialize_cache_payload,
    stable_bytes_hash,
)
from app.services.pdf import parse_pdf, validate_pdf_input
from app.services.profile import ProfileExtractor, analyze_profile
from app.services.redis_cache import CacheStore

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
    cache: Annotated[CacheStore, Depends(get_cache_store)],
) -> ResumeSnapshot:
    started_at = perf_counter()
    upload = await read_pdf_upload(request, max_bytes=settings.max_pdf_bytes)
    validate_pdf_input(
        upload.pdf_bytes,
        filename=upload.filename,
        content_type=upload.content_type,
        max_bytes=settings.max_pdf_bytes,
    )
    cache_key = build_extract_cache_key(stable_bytes_hash(upload.pdf_bytes))
    cached_snapshot = deserialize_resume_snapshot(await cache.get(cache_key) or "")
    if cached_snapshot is not None:
        if cached_snapshot.document.page_count > settings.max_pdf_pages:
            raise PdfPageLimitExceededError(
                details={
                    "max_pages": settings.max_pdf_pages,
                    "actual_pages": cached_snapshot.document.page_count,
                }
            )
        if cached_snapshot.document.character_count > settings.max_resume_chars:
            raise PdfTextTooLongError(
                details={
                    "max_chars": settings.max_resume_chars,
                    "actual_chars": cached_snapshot.document.character_count,
                }
            )
        cached_data = cached_snapshot.model_dump(mode="json")
        cached_data["resume_id"] = f"res_{uuid4()}"
        cached_data["cached"] = True
        cached_data["document"]["filename"] = upload.filename
        snapshot = ResumeSnapshot.model_validate(cached_data)
        _log_resume_result(request, settings, started_at, snapshot, extractor)
        return snapshot

    parsed = await run_in_threadpool(
        parse_pdf,
        upload.pdf_bytes,
        filename=upload.filename,
        content_type=upload.content_type,
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
    await cache.set(
        cache_key,
        serialize_cache_payload(snapshot),
        ttl_seconds=settings.cache_ttl_seconds,
    )
    _log_resume_result(request, settings, started_at, snapshot, extractor)
    return snapshot


def _log_resume_result(
    request: Request,
    settings: Settings,
    started_at: float,
    snapshot: ResumeSnapshot,
    extractor: ProfileExtractor | None,
) -> None:
    logger.info(
        "resume_analyzed",
        extra={
            "event": "resume_analyzed",
            "request_id": getattr(request.state, "request_id", None),
            "duration_ms": round((perf_counter() - started_at) * 1000),
            "page_count": snapshot.document.page_count,
            "character_count": snapshot.document.character_count,
            "model": settings.ai_model if extractor is not None else None,
            "degraded": snapshot.degraded,
            "cached": snapshot.cached,
        },
    )
