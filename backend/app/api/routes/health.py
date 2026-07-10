from collections.abc import Awaitable, Callable
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Response, status
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import Settings, get_settings
from app.schemas.health import DependencyStatus, HealthResponse

router = APIRouter(tags=["health"])
RedisPing = Callable[[str], Awaitable[bool]]


async def ping_redis(redis_url: str) -> bool:
    client = Redis.from_url(
        redis_url,
        socket_connect_timeout=0.5,
        socket_timeout=0.5,
    )
    try:
        ping_result = await cast(Awaitable[object], client.ping())
        return bool(ping_result)
    except (RedisError, TimeoutError):
        return False
    finally:
        await client.aclose()


def get_redis_ping() -> RedisPing:
    return ping_redis


@router.get("/health", response_model=HealthResponse)
async def get_health(
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
    redis_ping: Annotated[RedisPing, Depends(get_redis_ping)],
) -> HealthResponse:
    redis_status: Literal["disabled", "up", "down"]
    if settings.redis_url is None:
        redis_status = "disabled"
    else:
        redis_status = "up" if await redis_ping(settings.redis_url) else "down"

    if not settings.ai_api_key:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        overall_status: Literal["ok", "degraded", "unavailable"] = "unavailable"
        ai_status: Literal["configured", "unavailable"] = "unavailable"
    else:
        overall_status = "degraded" if redis_status == "down" else "ok"
        ai_status = "configured"

    return HealthResponse(
        status=overall_status,
        version=settings.app_version,
        dependencies=DependencyStatus(
            ai=ai_status,
            redis=redis_status,
        ),
    )
