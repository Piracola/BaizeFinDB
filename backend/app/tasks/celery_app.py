from celery import Celery

from app.core.config import get_settings

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


@celery_app.task(name="baizefindb.tasks.ping")
def ping() -> str:
    return "pong"

