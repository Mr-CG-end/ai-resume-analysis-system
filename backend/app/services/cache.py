import hashlib
import json
import re

from pydantic import BaseModel, ValidationError

from app.schemas.match import MatchResponse
from app.schemas.resume import ResumeSnapshot

CACHE_TTL_SECONDS = 24 * 60 * 60
DEFAULT_EXTRACT_VERSION = "v1"
DEFAULT_SCORE_VERSION = "v1"

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,32}$")


def stable_hash(value: str) -> str:
    """Return a deterministic SHA-256 digest for the exact UTF-8 text."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_extract_cache_key(
    pdf_sha256: str,
    extract_version: str = DEFAULT_EXTRACT_VERSION,
) -> str:
    _validate_sha256(pdf_sha256, field_name="pdf_sha256")
    _validate_version(extract_version, field_name="extract_version")
    return f"extract:{pdf_sha256}:{extract_version}"


def build_match_cache_key(
    resume_hash: str,
    jd_hash: str,
    score_version: str = DEFAULT_SCORE_VERSION,
) -> str:
    _validate_sha256(resume_hash, field_name="resume_hash")
    _validate_sha256(jd_hash, field_name="jd_hash")
    _validate_version(score_version, field_name="score_version")
    return f"match:{resume_hash}:{jd_hash}:{score_version}"


def serialize_cache_payload(payload: BaseModel) -> str:
    """Serialize a validated model in a stable, compact JSON representation."""
    return json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def deserialize_resume_snapshot(payload: str | bytes) -> ResumeSnapshot | None:
    return _deserialize_cache_payload(payload, ResumeSnapshot)


def deserialize_match_response(payload: str | bytes) -> MatchResponse | None:
    return _deserialize_cache_payload(payload, MatchResponse)


def _deserialize_cache_payload[CacheModel: BaseModel](
    payload: str | bytes,
    model_type: type[CacheModel],
) -> CacheModel | None:
    try:
        return model_type.model_validate_json(payload, strict=True)
    except (UnicodeDecodeError, ValidationError, ValueError):
        return None


def _validate_sha256(value: str, *, field_name: str) -> None:
    if not _SHA256_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")


def _validate_version(value: str, *, field_name: str) -> None:
    if not _VERSION_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} contains unsupported characters")
