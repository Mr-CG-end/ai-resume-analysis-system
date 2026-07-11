from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends

from app.core.config import Settings, get_settings
from app.services.redis_cache import CacheStore, create_cache


async def get_cache_store(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncIterator[CacheStore]:
    cache = create_cache(settings.redis_url)
    try:
        yield cache
    finally:
        await cache.aclose()
