from redis import asyncio as redis

from app.core.config import get_settings


async def check_redis() -> dict[str, str]:
    settings = get_settings()
    client = redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )

    try:
        await client.ping()
    except Exception as exc:
        return {
            "status": "down",
            "error": exc.__class__.__name__,
            "detail": str(exc)[:300],
        }
    finally:
        await client.aclose()

    return {"status": "ok"}

