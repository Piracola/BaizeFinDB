from app.core.config import Settings


def test_settings_defaults() -> None:
    settings = Settings()

    assert settings.app_name == "BaizeFinDB"
    assert settings.app_env == "local"
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.effective_celery_broker_url == settings.redis_url
    assert settings.radar_scan_interval_seconds == 300
    assert settings.radar_continuous_p1_trigger_count == 3
    assert settings.radar_continuity_window_minutes == 30
    assert settings.telegram_bot_token is None
    assert settings.telegram_allowed_chat_id_set == set()
    assert not settings.telegram_bot_token_configured
    assert not settings.telegram_webhook_secret_enabled
    assert settings.telegram_push_enabled is False


def test_settings_reads_environment(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("RADAR_SCAN_INTERVAL_SECONDS", "120")
    monkeypatch.setenv("RADAR_CONTINUOUS_P1_TRIGGER_COUNT", "2")
    monkeypatch.setenv("RADAR_CONTINUITY_WINDOW_MINUTES", "15")

    settings = Settings()

    assert settings.app_env == "test"
    assert settings.radar_scan_interval_seconds == 120
    assert settings.radar_continuous_p1_trigger_count == 2
    assert settings.radar_continuity_window_minutes == 15


def test_settings_reads_telegram_environment(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "1001, 1002")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "secret")
    monkeypatch.setenv("TELEGRAM_PUSH_ENABLED", "true")

    settings = Settings()

    assert settings.telegram_bot_token_configured
    assert settings.telegram_allowed_chat_id_set == {"1001", "1002"}
    assert settings.telegram_webhook_secret_enabled
    assert settings.telegram_push_enabled is True

