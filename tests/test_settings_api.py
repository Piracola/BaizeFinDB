import json

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_settings_status_default_is_read_only_and_redacted(monkeypatch) -> None:
    _set_default_settings_env(monkeypatch)
    client = TestClient(create_app())

    response = client.get("/settings/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["report_type"] == "settings_status"
    assert payload["mode"] == "read_only_env"
    assert payload["config_source"] == "environment"
    assert "does not expose secret values" in payload["read_only_boundary"]
    assert payload["tushare"]["token_configured"] is False
    assert payload["telegram"]["bot_token_configured"] is False
    assert payload["telegram"]["allowed_chat_count"] == 0
    assert payload["model"]["status"] == "ok"
    assert payload["model"]["analysis_enabled"] is False
    assert payload["model"]["provider"] == "disabled"
    assert payload["model"]["openai_api_key_configured"] is False
    assert payload["model"]["model_api_key_configured"] is False


def test_settings_status_configured_state_never_returns_secret_values(monkeypatch) -> None:
    monkeypatch.setenv("TUSHARE_TOKEN", "tushare-secret-value")
    monkeypatch.setenv("TUSHARE_ANNS_D_BEAT_ENABLED", "true")
    monkeypatch.setenv("TUSHARE_ANNS_D_BEAT_INTERVAL_SECONDS", "1800")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "telegram-secret-value")
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "1001, 1002")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "webhook-secret-value")
    monkeypatch.setenv("TELEGRAM_REQUIRE_BINDING", "true")
    monkeypatch.setenv("TELEGRAM_PUSH_ENABLED", "true")
    monkeypatch.setenv("MODEL_ANALYSIS_ENABLED", "true")
    monkeypatch.setenv("MODEL_PROVIDER", "custom")
    monkeypatch.setenv("MODEL_PRIMARY_MODEL", "private-primary-model")
    monkeypatch.setenv("MODEL_FALLBACK_MODEL", "private-fallback-model")
    monkeypatch.setenv("MODEL_API_BASE_URL", "https://models.example.test/v1")
    monkeypatch.setenv("MODEL_API_KEY", "model-secret-value")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret-value")
    monkeypatch.setenv("MODEL_AUDIT_STORE_RAW_PROMPT", "false")
    client = TestClient(create_app())

    response = client.get("/settings/status")

    assert response.status_code == 200
    payload = response.json()
    serialized = json.dumps(payload, ensure_ascii=False)
    assert payload["tushare"]["token_configured"] is True
    assert payload["tushare"]["anns_d_beat_enabled"] is True
    assert payload["tushare"]["anns_d_beat_interval_seconds"] == 1800
    assert payload["telegram"]["bot_token_configured"] is True
    assert payload["telegram"]["allowed_chat_count"] == 2
    assert payload["telegram"]["webhook_secret_enabled"] is True
    assert payload["telegram"]["require_binding"] is True
    assert payload["telegram"]["push_enabled"] is True
    assert payload["model"]["status"] == "ok"
    assert payload["model"]["analysis_enabled"] is True
    assert payload["model"]["provider"] == "custom"
    assert payload["model"]["primary_model_configured"] is True
    assert payload["model"]["fallback_model_configured"] is True
    assert payload["model"]["custom_base_url_configured"] is True
    assert payload["model"]["model_api_key_configured"] is True
    assert payload["model"]["openai_api_key_configured"] is True
    assert "tushare-secret-value" not in serialized
    assert "telegram-secret-value" not in serialized
    assert "webhook-secret-value" not in serialized
    assert "model-secret-value" not in serialized
    assert "openai-secret-value" not in serialized
    assert "private-primary-model" not in serialized
    assert "private-fallback-model" not in serialized
    assert "models.example.test" not in serialized


def _set_default_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TUSHARE_TOKEN", "")
    monkeypatch.setenv("TUSHARE_ANNS_D_BEAT_ENABLED", "false")
    monkeypatch.setenv("TUSHARE_ANNS_D_BEAT_INTERVAL_SECONDS", "3600")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "")
    monkeypatch.setenv("TELEGRAM_REQUIRE_BINDING", "false")
    monkeypatch.setenv("TELEGRAM_PUSH_ENABLED", "false")
    monkeypatch.setenv("MODEL_ANALYSIS_ENABLED", "false")
    monkeypatch.setenv("MODEL_PROVIDER", "disabled")
    monkeypatch.setenv("MODEL_PRIMARY_MODEL", "")
    monkeypatch.setenv("MODEL_FALLBACK_MODEL", "")
    monkeypatch.setenv("MODEL_API_BASE_URL", "")
    monkeypatch.setenv("MODEL_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("MODEL_AUDIT_STORE_RAW_PROMPT", "false")
