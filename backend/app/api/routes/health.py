from fastapi import APIRouter, Response, status

from app.core.config import get_settings
from app.core.redis import check_redis
from app.db.session import check_database

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.app_env,
    }


@router.get("/health/ready")
async def readiness(response: Response) -> dict[str, object]:
    settings = get_settings()
    checks = {
        "database": await check_database(),
        "redis": await check_redis(),
    }
    ready = all(check["status"] == "ok" for check in checks.values())

    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ready" if ready else "not_ready",
        "service": settings.app_name,
        "checks": checks,
    }

