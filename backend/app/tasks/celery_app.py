import asyncio

from celery import Celery

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.providers.service import collect_minimal_akshare
from app.radar.service import run_radar_scan

settings = get_settings()

celery_app = Celery(
    "baizefindb",
    broker=settings.effective_celery_broker_url,
    backend=settings.effective_celery_result_backend,
)

celery_app.conf.update(
    timezone="Asia/Shanghai",
    enable_utc=False,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

celery_app.conf.beat_schedule = {
    "collect-akshare-minimal-every-5-minutes": {
        "task": "baizefindb.providers.collect_akshare_minimal",
        "schedule": 300.0,
    },
    "run-radar-scan-every-5-minutes": {
        "task": "baizefindb.radar.run_scan",
        "schedule": 300.0,
    }
}


@celery_app.task(name="baizefindb.tasks.ping")
def ping() -> str:
    return "pong"


@celery_app.task(
    name="baizefindb.providers.collect_akshare_minimal",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def collect_akshare_minimal_task() -> dict[str, object]:
    return asyncio.run(_collect_akshare_minimal())


async def _collect_akshare_minimal() -> dict[str, object]:
    async with AsyncSessionLocal() as session:
        result = await collect_minimal_akshare(session)
        return result.model_dump(mode="json")


@celery_app.task(
    name="baizefindb.radar.run_scan",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def run_radar_scan_task() -> dict[str, object]:
    return asyncio.run(_run_radar_scan())


async def _run_radar_scan() -> dict[str, object]:
    async with AsyncSessionLocal() as session:
        result = await run_radar_scan(session)
        return result.model_dump(mode="json")
