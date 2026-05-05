import pytest
from pydantic import ValidationError

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
    assert not settings.tushare_token_configured
    assert settings.tushare_anns_d_beat_enabled is False
    assert settings.tushare_anns_d_beat_interval_seconds == 3600
    assert settings.telegram_bot_token is None
    assert settings.telegram_allowed_chat_id_set == set()
    assert not settings.telegram_bot_token_configured
    assert not settings.telegram_webhook_secret_enabled
    assert settings.telegram_require_binding is False
    assert settings.telegram_push_enabled is False
    assert settings.model_analysis_enabled is False
    assert settings.model_provider == "disabled"
    assert settings.model_provider_normalized == "disabled"
    assert settings.model_primary_model is None
    assert settings.model_fallback_model is None
    assert settings.model_api_base_url is None
    assert settings.model_api_key is None
    assert settings.openai_api_key is None
    assert settings.model_primary_model_configured is False
    assert settings.model_fallback_model_configured is False
    assert settings.model_api_base_url_configured is False
    assert settings.model_api_key_configured is False
    assert settings.openai_api_key_configured is False
    assert settings.model_audit_store_raw_prompt is False
    assert settings.ops_disk_free_percent_alert_threshold == 10.0
    assert settings.ops_cpu_usage_percent_alert_threshold == 90.0
    assert settings.ops_memory_used_percent_alert_threshold == 90.0


def test_settings_reads_environment(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("RADAR_SCAN_INTERVAL_SECONDS", "120")
    monkeypatch.setenv("RADAR_CONTINUOUS_P1_TRIGGER_COUNT", "2")
    monkeypatch.setenv("RADAR_CONTINUITY_WINDOW_MINUTES", "15")
    monkeypatch.setenv("TUSHARE_ANNS_D_BEAT_ENABLED", "true")
    monkeypatch.setenv("TUSHARE_ANNS_D_BEAT_INTERVAL_SECONDS", "1800")
    monkeypatch.setenv("OPS_CPU_USAGE_PERCENT_ALERT_THRESHOLD", "85")
    monkeypatch.setenv("OPS_MEMORY_USED_PERCENT_ALERT_THRESHOLD", "88")

    settings = Settings()

    assert settings.app_env == "test"
    assert settings.radar_scan_interval_seconds == 120
    assert settings.radar_continuous_p1_trigger_count == 2
    assert settings.radar_continuity_window_minutes == 15
    assert settings.tushare_anns_d_beat_enabled is True
    assert settings.tushare_anns_d_beat_interval_seconds == 1800
    assert settings.ops_cpu_usage_percent_alert_threshold == 85.0
    assert settings.ops_memory_used_percent_alert_threshold == 88.0


@pytest.mark.parametrize("interval_seconds", ["0", "-1"])
def test_tushare_announcements_beat_interval_must_be_positive(
    monkeypatch,
    interval_seconds: str,
) -> None:
    monkeypatch.setenv("TUSHARE_ANNS_D_BEAT_INTERVAL_SECONDS", interval_seconds)

    with pytest.raises(ValidationError):
        Settings()


def test_settings_reads_telegram_environment(monkeypatch) -> None:
    monkeypatch.setenv("TUSHARE_TOKEN", "tushare-token")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "1001, 1002")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "secret")
    monkeypatch.setenv("TELEGRAM_REQUIRE_BINDING", "true")
    monkeypatch.setenv("TELEGRAM_PUSH_ENABLED", "true")

    settings = Settings()

    assert settings.tushare_token_configured
    assert settings.telegram_bot_token_configured
    assert settings.telegram_allowed_chat_id_set == {"1001", "1002"}
    assert settings.telegram_webhook_secret_enabled
    assert settings.telegram_require_binding is True
    assert settings.telegram_push_enabled is True


def test_settings_reads_model_audit_environment(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_AUDIT_STORE_RAW_PROMPT", "true")

    settings = Settings()

    assert settings.model_audit_store_raw_prompt is True


def test_settings_reads_model_provider_environment(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_ANALYSIS_ENABLED", "true")
    monkeypatch.setenv("MODEL_PROVIDER", "OpenAI")
    monkeypatch.setenv("MODEL_PRIMARY_MODEL", "gpt-test-primary")
    monkeypatch.setenv("MODEL_FALLBACK_MODEL", "gpt-test-fallback")
    monkeypatch.setenv("MODEL_API_BASE_URL", "https://models.example.test/v1")
    monkeypatch.setenv("MODEL_API_KEY", "custom-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")

    settings = Settings()

    assert settings.model_analysis_enabled is True
    assert settings.model_provider == "OpenAI"
    assert settings.model_provider_normalized == "openai"
    assert settings.model_primary_model_configured is True
    assert settings.model_fallback_model_configured is True
    assert settings.model_api_base_url_configured is True
    assert settings.model_api_key_configured is True
    assert settings.openai_api_key_configured is True
