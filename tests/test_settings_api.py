import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import create_app
from app.settings import service as settings_service
from app.settings.schemas import SettingsConnectionCheck


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


def test_editable_settings_contract_is_redacted(monkeypatch) -> None:
    monkeypatch.setenv("TUSHARE_TOKEN", "tushare-secret-value")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "telegram-secret-value")
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "1001, -1002")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "webhook-secret-value")
    monkeypatch.setenv("MODEL_PROVIDER", "custom")
    monkeypatch.setenv("MODEL_PRIMARY_MODEL", "private-primary-model")
    monkeypatch.setenv("MODEL_API_BASE_URL", "https://models.example.test/v1")
    monkeypatch.setenv("MODEL_API_KEY", "model-secret-value")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret-value")
    monkeypatch.setenv("SETTINGS_ADMIN_TOKEN", "owner-secret-value")
    client = TestClient(create_app())

    response = client.get("/settings/editable")

    assert response.status_code == 200
    payload = response.json()
    serialized = json.dumps(payload, ensure_ascii=False)
    assert payload["mode"] == "editable_local_env"
    assert payload["auth"]["admin_token_configured"] is True
    assert payload["auth"]["header_name"] == "X-BaizeFinDB-Settings-Token"
    fields = {field["key"]: field for field in payload["fields"]}
    assert fields["TUSHARE_TOKEN"]["configured"] is True
    assert fields["TUSHARE_TOKEN"]["value"] is None
    assert fields["MODEL_PROVIDER"]["value"] == "custom"
    assert fields["MODEL_PRIMARY_MODEL"]["value"] is None
    assert "tushare-secret-value" not in serialized
    assert "telegram-secret-value" not in serialized
    assert "webhook-secret-value" not in serialized
    assert "owner-secret-value" not in serialized
    assert "model-secret-value" not in serialized
    assert "openai-secret-value" not in serialized
    assert "private-primary-model" not in serialized
    assert "models.example.test" not in serialized


def test_editable_settings_save_requires_admin_token_when_configured(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    _set_default_settings_env(monkeypatch)
    monkeypatch.setenv("SETTINGS_ADMIN_TOKEN", "owner-token")
    client = TestClient(create_app())

    response = client.put(
        "/settings/editable",
        json={"values": {"TUSHARE_TOKEN": "new-token"}, "clear": []},
    )

    assert response.status_code == 403
    assert not (tmp_path / ".env").exists()


def test_editable_settings_save_writes_local_env_and_refreshes_status(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    _set_default_settings_env(monkeypatch)
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("MODEL_PROVIDER", raising=False)
    monkeypatch.delenv("MODEL_PRIMARY_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("SETTINGS_ADMIN_TOKEN", "owner-token")
    client = TestClient(create_app())

    response = client.put(
        "/settings/editable",
        headers={"X-BaizeFinDB-Settings-Token": "owner-token"},
        json={
            "values": {
                "TUSHARE_TOKEN": "new-tushare-token",
                "TELEGRAM_BOT_TOKEN": "new-telegram-token",
                "MODEL_ANALYSIS_ENABLED": True,
                "MODEL_PROVIDER": "openai",
                "MODEL_PRIMARY_MODEL": "gpt-private",
                "OPENAI_API_KEY": "new-openai-token",
            },
            "clear": [],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    serialized = json.dumps(payload, ensure_ascii=False)
    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert payload["saved"] is True
    assert "TUSHARE_TOKEN" in payload["updated_keys"]
    assert payload["settings"]["status"]["tushare"]["token_configured"] is True
    assert payload["settings"]["status"]["model"]["analysis_enabled"] is True
    assert payload["settings"]["status"]["model"]["provider"] == "openai"
    assert payload["settings"]["status"]["model"]["openai_api_key_configured"] is True
    assert "TUSHARE_TOKEN=new-tushare-token" in env_text
    assert "TELEGRAM_BOT_TOKEN=new-telegram-token" in env_text
    assert "MODEL_PROVIDER=openai" in env_text
    assert "OPENAI_API_KEY=new-openai-token" in env_text
    assert "new-tushare-token" not in serialized
    assert "new-telegram-token" not in serialized
    assert "new-openai-token" not in serialized
    assert "gpt-private" not in serialized


def test_editable_settings_blank_secret_is_unchanged_and_clear_removes_value(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "TUSHARE_TOKEN=old-token\nTELEGRAM_BOT_TOKEN=old-telegram-token\n",
        encoding="utf-8",
    )
    _set_default_settings_env(monkeypatch)
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("SETTINGS_ADMIN_TOKEN", "owner-token")
    client = TestClient(create_app())

    response = client.put(
        "/settings/editable",
        headers={"X-BaizeFinDB-Settings-Token": "owner-token"},
        json={
            "values": {"TUSHARE_TOKEN": "", "TELEGRAM_BOT_TOKEN": "ignored"},
            "clear": ["TELEGRAM_BOT_TOKEN"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert payload["unchanged_secret_keys"] == ["TUSHARE_TOKEN"]
    assert "TUSHARE_TOKEN=old-token" in env_text
    assert "TELEGRAM_BOT_TOKEN=" in env_text
    assert "old-telegram-token" not in env_text


def test_editable_settings_validation_rejects_unsafe_values(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    _set_default_settings_env(monkeypatch)
    monkeypatch.setenv("SETTINGS_ADMIN_TOKEN", "owner-token")
    client = TestClient(create_app())

    response = client.put(
        "/settings/editable",
        headers={"X-BaizeFinDB-Settings-Token": "owner-token"},
        json={
            "values": {
                "MODEL_PROVIDER": "custom",
                "MODEL_API_BASE_URL": "https://user:pass@models.example.test/v1",
            },
            "clear": [],
        },
    )

    assert response.status_code == 422
    serialized = json.dumps(response.json(), ensure_ascii=False)
    assert "user:pass" not in serialized


def test_settings_connection_test_requires_admin_token_when_configured(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    _set_default_settings_env(monkeypatch)
    monkeypatch.setenv("SETTINGS_ADMIN_TOKEN", "owner-token")
    client = TestClient(create_app())

    response = client.post("/settings/connection-test", json={"target": "server"})

    assert response.status_code == 403


def test_settings_connection_test_runs_explicit_targets_without_leaking_secrets(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    _set_default_settings_env(monkeypatch)
    monkeypatch.setenv("TUSHARE_TOKEN", "tushare-secret-value")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "telegram-secret-value")
    monkeypatch.setenv("MODEL_ANALYSIS_ENABLED", "true")
    monkeypatch.setenv("MODEL_PROVIDER", "openai")
    monkeypatch.setenv("MODEL_PRIMARY_MODEL", "private-primary-model")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret-value")
    monkeypatch.setenv("SETTINGS_ADMIN_TOKEN", "owner-token")

    async def fake_tushare(settings):
        return SettingsConnectionCheck(name="tushare", status="ok", detail="Tushare ok")

    async def fake_telegram(settings):
        return SettingsConnectionCheck(name="telegram", status="ok", detail="Telegram ok")

    async def fake_model(settings):
        return SettingsConnectionCheck(name="model", status="ok", detail="Model ok")

    monkeypatch.setattr("app.settings.service._test_tushare_connection", fake_tushare)
    monkeypatch.setattr("app.settings.service._test_telegram_connection", fake_telegram)
    monkeypatch.setattr("app.settings.service._test_model_connection", fake_model)
    client = TestClient(create_app())

    response = client.post(
        "/settings/connection-test",
        headers={"X-BaizeFinDB-Settings-Token": "owner-token"},
        json={"target": "all"},
    )

    assert response.status_code == 200
    payload = response.json()
    serialized = json.dumps(payload, ensure_ascii=False)
    assert payload["status"] == "ok"
    assert [check["name"] for check in payload["checks"]] == [
        "server",
        "tushare",
        "telegram",
        "model",
    ]
    assert "tushare-secret-value" not in serialized
    assert "telegram-secret-value" not in serialized
    assert "openai-secret-value" not in serialized
    assert "private-primary-model" not in serialized
    assert "owner-token" not in serialized


def test_settings_connection_test_sanitizes_provider_errors(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    _set_default_settings_env(monkeypatch)
    monkeypatch.setenv("TUSHARE_TOKEN", "tushare-secret-value")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret-value")

    async def failing_tushare(settings):
        raise RuntimeError(
            "provider failed token=tushare-secret-value api_key=openai-secret-value"
        )

    monkeypatch.setattr("app.settings.service._test_tushare_connection", failing_tushare)
    client = TestClient(create_app())

    response = client.post("/settings/connection-test", json={"target": "tushare"})

    assert response.status_code == 200
    serialized = json.dumps(response.json(), ensure_ascii=False)
    assert "tushare-secret-value" not in serialized
    assert "openai-secret-value" not in serialized
    assert "<redacted>" in serialized


@pytest.mark.asyncio
async def test_tushare_connection_test_uses_daily_endpoint(monkeypatch) -> None:
    calls = []

    class FakeTushareProvider:
        def __init__(self, settings: Settings) -> None:
            self.settings = settings

        async def fetch(self, endpoint: str):
            calls.append(endpoint)
            return SimpleNamespace(row_count=8)

    monkeypatch.setattr(settings_service, "TushareProvider", FakeTushareProvider)

    result = await settings_service._test_tushare_connection(
        Settings(TUSHARE_TOKEN="tushare-secret-value")
    )

    assert result.status == "ok"
    assert result.detail == "Tushare daily responded with 8 rows."
    assert calls == ["daily"]


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
    monkeypatch.setenv("SETTINGS_ADMIN_TOKEN", "")
