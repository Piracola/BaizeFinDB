from datetime import UTC, datetime
from typing import Any

from app.audit.model_provider_readiness import evaluate_model_provider_readiness
from app.core.config import Settings, get_settings
from app.settings.schemas import (
    ModelSettingsStatus,
    SettingsReadinessCheck,
    SettingsReadinessSummary,
    SettingsStatusRead,
    TelegramSettingsStatus,
    TushareSettingsStatus,
)

SETTINGS_STATUS_BOUNDARY = (
    "Read-only settings status; reads configuration flags only; does not expose "
    "secret values, write env files, call provider APIs, validate tokens over the "
    "network, read databases, run scans, generate reports, send Telegram messages, "
    "or invoke models"
)


def build_settings_status(
    settings: Settings | None = None,
    *,
    generated_at: datetime | None = None,
) -> SettingsStatusRead:
    current_settings = settings or get_settings()
    model_report = evaluate_model_provider_readiness(
        current_settings,
        generated_at=generated_at,
    )

    return SettingsStatusRead(
        generated_at=generated_at or datetime.now(UTC),
        read_only_boundary=SETTINGS_STATUS_BOUNDARY,
        tushare=_tushare_status(current_settings),
        telegram=_telegram_status(current_settings),
        model=_model_status(current_settings, model_report),
    )


def _tushare_status(settings: Settings) -> TushareSettingsStatus:
    return TushareSettingsStatus(
        token_configured=settings.tushare_token_configured,
        anns_d_beat_enabled=settings.tushare_anns_d_beat_enabled,
        anns_d_beat_interval_seconds=settings.tushare_anns_d_beat_interval_seconds,
    )


def _telegram_status(settings: Settings) -> TelegramSettingsStatus:
    return TelegramSettingsStatus(
        bot_token_configured=settings.telegram_bot_token_configured,
        allowed_chat_count=len(settings.telegram_allowed_chat_id_set),
        webhook_secret_enabled=settings.telegram_webhook_secret_enabled,
        require_binding=settings.telegram_require_binding,
        push_enabled=settings.telegram_push_enabled,
    )


def _model_status(settings: Settings, report: dict[str, Any]) -> ModelSettingsStatus:
    summary = report.get("summary")
    if not isinstance(summary, dict):
        summary = {}

    checks = report.get("checks")
    if not isinstance(checks, list):
        checks = []

    return ModelSettingsStatus(
        status=_string_value(report.get("status"), default="unknown"),
        analysis_enabled=settings.model_analysis_enabled,
        provider=settings.model_provider_normalized,
        primary_model_configured=settings.model_primary_model_configured,
        fallback_model_configured=settings.model_fallback_model_configured,
        custom_base_url_configured=settings.model_api_base_url_configured,
        openai_api_key_configured=settings.openai_api_key_configured,
        model_api_key_configured=settings.model_api_key_configured,
        raw_prompt_storage_enabled=settings.model_audit_store_raw_prompt,
        summary=SettingsReadinessSummary(
            check_count=_int_value(summary.get("check_count")),
            ok_count=_int_value(summary.get("ok_count")),
            warning_count=_int_value(summary.get("warning_count")),
            failure_count=_int_value(summary.get("failure_count")),
        ),
        checks=[
            SettingsReadinessCheck(
                name=_string_value(check.get("name"), default="unknown"),
                status=_string_value(check.get("status"), default="unknown"),
                detail=_string_value(check.get("detail"), default=""),
            )
            for check in checks
            if isinstance(check, dict)
        ],
    )


def _string_value(value: object, *, default: str) -> str:
    if isinstance(value, str) and value:
        return value
    return default


def _int_value(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return max(0, value)
    return 0
