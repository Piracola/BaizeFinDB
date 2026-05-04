import asyncio

from celery import Celery

from app.core.config import Settings, get_settings
from app.db.session import AsyncSessionLocal
from app.providers.service import collect_minimal_akshare, collect_tushare_announcements
from app.radar.service import run_radar_scan
from app.telegram.client import TelegramClient
from app.telegram.push_service import send_latest_radar_push

settings = get_settings()

RADAR_BEAT_SCHEDULE_NAME = "collect-and-run-radar-every-5-minutes"
TUSHARE_ANNS_D_BEAT_SCHEDULE_NAME = "collect-tushare-announcements"
TUSHARE_ANNS_D_TASK_NAME = "baizefindb.providers.collect_tushare_announcements"

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


def build_beat_schedule(active_settings: Settings) -> dict[str, dict[str, object]]:
    schedule: dict[str, dict[str, object]] = {
        RADAR_BEAT_SCHEDULE_NAME: {
            "task": "baizefindb.radar.collect_and_scan",
            "schedule": float(active_settings.radar_scan_interval_seconds),
        },
    }

    if active_settings.tushare_anns_d_beat_enabled:
        schedule[TUSHARE_ANNS_D_BEAT_SCHEDULE_NAME] = {
            "task": TUSHARE_ANNS_D_TASK_NAME,
            "schedule": float(active_settings.tushare_anns_d_beat_interval_seconds),
        }

    return schedule


celery_app.conf.beat_schedule = build_beat_schedule(settings)


@celery_app.task(name="baizefindb.tasks.ping")
def ping() -> str:
    return "pong"


@celery_app.task(
    name="baizefindb.providers.collect_tushare_announcements",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def collect_tushare_announcements_task() -> dict[str, object]:
    return asyncio.run(_collect_tushare_announcements())


async def _collect_tushare_announcements() -> dict[str, object]:
    async with AsyncSessionLocal() as session:
        result = await collect_tushare_announcements(session)
        return result.model_dump(mode="json")


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


@celery_app.task(
    name="baizefindb.radar.collect_and_scan",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def collect_and_run_radar_task() -> dict[str, object]:
    return asyncio.run(_collect_and_run_radar())


async def _collect_and_run_radar() -> dict[str, object]:
    async with AsyncSessionLocal() as session:
        collection = await collect_minimal_akshare(session)
        scan = await run_radar_scan(session)
        telegram_push = await _send_configured_telegram_push(session)
        return {
            "collection": collection.model_dump(mode="json"),
            "scan": scan.model_dump(mode="json"),
            "telegram_push": telegram_push,
        }


@celery_app.task(
    name="baizefindb.telegram.push_latest_radar",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def push_latest_radar_task() -> dict[str, object]:
    return asyncio.run(_push_latest_radar())


async def _push_latest_radar() -> dict[str, object]:
    async with AsyncSessionLocal() as session:
        result = await _send_configured_telegram_push(session)
        return result


async def _send_configured_telegram_push(session) -> dict[str, object]:
    if not settings.telegram_push_enabled:
        return {"push_enabled": False, "deliveries": []}

    result = await send_latest_radar_push(
        session=session,
        settings=settings,
        client=TelegramClient(settings.telegram_bot_token),
        respect_enabled=True,
    )
    return result.model_dump(mode="json")
