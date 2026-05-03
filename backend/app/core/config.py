from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="BaizeFinDB", alias="APP_NAME")
    app_env: str = Field(default="local", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    database_url: str = Field(
        default="postgresql+asyncpg://baizefindb:baizefindb@localhost:5432/baizefindb",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    celery_broker_url: str | None = Field(default=None, alias="CELERY_BROKER_URL")
    celery_result_backend: str | None = Field(default=None, alias="CELERY_RESULT_BACKEND")
    radar_scan_interval_seconds: int = Field(
        default=300,
        gt=0,
        alias="RADAR_SCAN_INTERVAL_SECONDS",
    )
    radar_continuous_p1_trigger_count: int = Field(
        default=3,
        gt=0,
        alias="RADAR_CONTINUOUS_P1_TRIGGER_COUNT",
    )
    radar_continuity_window_minutes: int = Field(
        default=30,
        gt=0,
        alias="RADAR_CONTINUITY_WINDOW_MINUTES",
    )
    tushare_token: str | None = Field(default=None, alias="TUSHARE_TOKEN")
    telegram_bot_token: str | None = Field(default=None, alias="TELEGRAM_BOT_TOKEN")
    telegram_allowed_chat_ids: str | None = Field(
        default=None,
        alias="TELEGRAM_ALLOWED_CHAT_IDS",
    )
    telegram_webhook_secret: str | None = Field(
        default=None,
        alias="TELEGRAM_WEBHOOK_SECRET",
    )
    telegram_push_enabled: bool = Field(default=False, alias="TELEGRAM_PUSH_ENABLED")
    model_audit_store_raw_prompt: bool = Field(
        default=False,
        alias="MODEL_AUDIT_STORE_RAW_PROMPT",
    )
    ops_disk_check_path: str = Field(default=".", alias="OPS_DISK_CHECK_PATH")
    ops_disk_free_percent_alert_threshold: float = Field(
        default=10.0,
        ge=0,
        le=100,
        alias="OPS_DISK_FREE_PERCENT_ALERT_THRESHOLD",
    )

    @property
    def effective_celery_broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def effective_celery_result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url

    @property
    def telegram_allowed_chat_id_set(self) -> set[str]:
        if not self.telegram_allowed_chat_ids:
            return set()

        return {
            chat_id.strip()
            for chat_id in self.telegram_allowed_chat_ids.split(",")
            if chat_id.strip()
        }

    @property
    def telegram_bot_token_configured(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_bot_token.strip())

    @property
    def telegram_webhook_secret_enabled(self) -> bool:
        return bool(self.telegram_webhook_secret and self.telegram_webhook_secret.strip())

    @property
    def tushare_token_configured(self) -> bool:
        return bool(self.tushare_token and self.tushare_token.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
