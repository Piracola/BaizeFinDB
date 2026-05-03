from app.core.config import Settings


def test_settings_defaults() -> None:
    settings = Settings()

    assert settings.app_name == "BaizeFinDB"
    assert settings.app_env == "local"
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.effective_celery_broker_url == settings.redis_url
    assert settings.telegram_bot_token is None
    assert settings.telegram_allowed_chat_id_set == set()
    assert not settings.telegram_bot_token_configured
    assert not settings.telegram_webhook_secret_enabled


def test_settings_reads_environment(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")

    settings = Settings()

    assert settings.app_env == "test"


def test_settings_reads_telegram_environment(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "1001, 1002")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "secret")

    settings = Settings()

    assert settings.telegram_bot_token_configured
    assert settings.telegram_allowed_chat_id_set == {"1001", "1002"}
    assert settings.telegram_webhook_secret_enabled

