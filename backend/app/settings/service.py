import asyncio
import json
import os
import re
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.ai.model_client import (
    ModelCompletionRequest,
    ModelMessage,
    ModelProviderConfigError,
    build_model_client,
)
from app.audit.model_provider_readiness import evaluate_model_provider_readiness
from app.core.config import Settings, get_settings
from app.providers.tushare import TushareProvider
from app.settings.schemas import (
    EditableSettingsAuth,
    EditableSettingsField,
    EditableSettingsRead,
    EditableSettingsSaveResult,
    EditableSettingsUpdate,
    ModelSettingsStatus,
    SettingsConnectionCheck,
    SettingsConnectionTestRequest,
    SettingsConnectionTestResult,
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
EDITABLE_SETTINGS_BOUNDARY = (
    "Owner-only local settings editor; writes supported keys to the server-local "
    ".env file, never returns secret values, does not call providers, and does "
    "not restart worker or beat processes"
)
CONNECTION_TEST_BOUNDARY = (
    "Explicit owner-triggered connection test; may call selected external provider "
    "APIs, never writes databases, never saves secrets, never sends Telegram "
    "messages, never changes radar/reports, and returns sanitized status only"
)
ENV_FILE_PATH = Path(".env")
ENV_KEY_PATTERN = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")
SECRET_DETAIL_PATTERN = re.compile(
    r"(?i)\b(token|api[_-]?key|secret|authorization|bearer)(\s*(?:=|:)?\s*)([^\s,;]+)",
)
LONG_SECRET_PATTERN = re.compile(r"\b[A-Za-z0-9._~+/-]{24,}\b")
TELEGRAM_GET_ME_TIMEOUT_SECONDS = 10

FIELD_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "key": "TUSHARE_TOKEN",
        "label": "Tushare Token",
        "group": "Tushare",
        "input_type": "password",
        "secret": True,
        "help_text": "用于 Tushare daily、stock_basic、anns_d、stock_company 真实抓取。",
    },
    {
        "key": "TUSHARE_ANNS_D_BEAT_ENABLED",
        "label": "Tushare 公告调度",
        "group": "Tushare",
        "input_type": "checkbox",
        "secret": False,
        "help_text": "默认关闭；启用前应先跑公告预调度和真实 token evidence。",
    },
    {
        "key": "TUSHARE_ANNS_D_BEAT_INTERVAL_SECONDS",
        "label": "公告调度间隔秒数",
        "group": "Tushare",
        "input_type": "number",
        "secret": False,
        "help_text": "必须大于 0；默认 3600。",
    },
    {
        "key": "TELEGRAM_BOT_TOKEN",
        "label": "Telegram Bot Token",
        "group": "Telegram",
        "input_type": "password",
        "secret": True,
        "help_text": "用于真实 Telegram Bot API 发送和 webhook 回复。",
    },
    {
        "key": "TELEGRAM_ALLOWED_CHAT_IDS",
        "label": "Telegram 白名单 Chat IDs",
        "group": "Telegram",
        "input_type": "password",
        "secret": True,
        "help_text": "逗号分隔，支持负数群组 ID；不回显原始 chat id。",
    },
    {
        "key": "TELEGRAM_WEBHOOK_SECRET",
        "label": "Telegram Webhook Secret",
        "group": "Telegram",
        "input_type": "password",
        "secret": True,
        "help_text": "配置后 webhook 请求必须携带同名 Telegram secret header。",
    },
    {
        "key": "TELEGRAM_REQUIRE_BINDING",
        "label": "严格绑定模式",
        "group": "Telegram",
        "input_type": "checkbox",
        "secret": False,
        "help_text": "开启后 Telegram chat 需要绑定/白名单才允许操作。",
    },
    {
        "key": "TELEGRAM_PUSH_ENABLED",
        "label": "Telegram 推送",
        "group": "Telegram",
        "input_type": "checkbox",
        "secret": False,
        "help_text": "开启后雷达调度可追加 Telegram 折叠推送。",
    },
    {
        "key": "MODEL_ANALYSIS_ENABLED",
        "label": "模型分析",
        "group": "Model",
        "input_type": "checkbox",
        "secret": False,
        "help_text": "仅控制显式手动模型草稿路径；不接管规则雷达。",
    },
    {
        "key": "MODEL_PROVIDER",
        "label": "模型 Provider",
        "group": "Model",
        "input_type": "select",
        "choices": ["disabled", "openai", "custom"],
        "secret": False,
        "help_text": "OpenAI 或 OpenAI-compatible custom provider。",
    },
    {
        "key": "MODEL_PRIMARY_MODEL",
        "label": "主模型名称",
        "group": "Model",
        "input_type": "password",
        "secret": True,
        "help_text": "不回显模型名；留空不修改。",
    },
    {
        "key": "MODEL_FALLBACK_MODEL",
        "label": "Fallback 模型名称",
        "group": "Model",
        "input_type": "password",
        "secret": True,
        "help_text": "可为空；主模型失败后才使用。",
    },
    {
        "key": "MODEL_API_BASE_URL",
        "label": "Custom Base URL",
        "group": "Model",
        "input_type": "password",
        "secret": True,
        "help_text": "custom provider 需要 HTTP(S) base URL，不允许嵌入账号密码。",
    },
    {
        "key": "MODEL_API_KEY",
        "label": "Custom Model API Key",
        "group": "Model",
        "input_type": "password",
        "secret": True,
        "help_text": "custom provider 使用；不回显。",
    },
    {
        "key": "OPENAI_API_KEY",
        "label": "OpenAI API Key",
        "group": "Model",
        "input_type": "password",
        "secret": True,
        "help_text": "openai provider 使用；不回显。",
    },
    {
        "key": "MODEL_AUDIT_STORE_RAW_PROMPT",
        "label": "保存 Raw Prompt",
        "group": "Model",
        "input_type": "checkbox",
        "secret": False,
        "help_text": "默认关闭；开启会产生隐私和安全风险，仅调试时使用。",
    },
)
FIELD_BY_KEY = {field["key"]: field for field in FIELD_DEFINITIONS}
BOOLEAN_KEYS = {
    "TUSHARE_ANNS_D_BEAT_ENABLED",
    "TELEGRAM_REQUIRE_BINDING",
    "TELEGRAM_PUSH_ENABLED",
    "MODEL_ANALYSIS_ENABLED",
    "MODEL_AUDIT_STORE_RAW_PROMPT",
}
INTEGER_KEYS = {"TUSHARE_ANNS_D_BEAT_INTERVAL_SECONDS"}
SECRET_KEYS = {field["key"] for field in FIELD_DEFINITIONS if field["secret"]}
CONFIGURED_ACCESSORS = {
    "TUSHARE_TOKEN": "tushare_token_configured",
    "TELEGRAM_BOT_TOKEN": "telegram_bot_token_configured",
    "TELEGRAM_WEBHOOK_SECRET": "telegram_webhook_secret_enabled",
    "MODEL_PRIMARY_MODEL": "model_primary_model_configured",
    "MODEL_FALLBACK_MODEL": "model_fallback_model_configured",
    "MODEL_API_BASE_URL": "model_api_base_url_configured",
    "MODEL_API_KEY": "model_api_key_configured",
    "OPENAI_API_KEY": "openai_api_key_configured",
}


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


def build_editable_settings(
    settings: Settings | None = None,
    *,
    generated_at: datetime | None = None,
) -> EditableSettingsRead:
    current_settings = settings or get_settings()
    now = generated_at or datetime.now(UTC)
    return EditableSettingsRead(
        generated_at=now,
        write_boundary=EDITABLE_SETTINGS_BOUNDARY,
        auth=EditableSettingsAuth(
            admin_token_configured=current_settings.settings_admin_token_configured,
            local_write_without_token=not current_settings.settings_admin_token_configured,
        ),
        fields=_editable_fields(current_settings),
        status=build_settings_status(current_settings, generated_at=now),
    )


def save_editable_settings(
    payload: EditableSettingsUpdate,
    *,
    env_file: Path = ENV_FILE_PATH,
) -> EditableSettingsSaveResult:
    updates, unchanged_secret_keys = _normalize_updates(payload)
    if updates:
        _write_env_updates(env_file, updates)
        _apply_process_env(updates)
        get_settings.cache_clear()

    refreshed = get_settings()
    return EditableSettingsSaveResult(
        saved=bool(updates),
        updated_keys=sorted(updates),
        unchanged_secret_keys=sorted(unchanged_secret_keys),
        restart_note=(
            "API process settings were refreshed. Docker, Celery worker, and beat "
            "processes may need restart before they see changed environment values."
        ),
        settings=build_editable_settings(refreshed),
    )


async def run_settings_connection_test(
    payload: SettingsConnectionTestRequest,
    *,
    settings: Settings | None = None,
    generated_at: datetime | None = None,
) -> SettingsConnectionTestResult:
    current_settings = settings or get_settings()
    target = payload.target
    checks = [
        SettingsConnectionCheck(
            name="server",
            status="ok",
            detail="BaizeFinDB API process can execute settings diagnostics.",
        ),
    ]

    targets = ["tushare", "telegram", "model"] if target == "all" else [target]
    for selected_target in targets:
        if selected_target == "server":
            continue
        checks.append(await _run_single_connection_test(selected_target, current_settings))

    return SettingsConnectionTestResult(
        generated_at=generated_at or datetime.now(UTC),
        target=target,
        status=_aggregate_connection_status(checks),
        boundary=CONNECTION_TEST_BOUNDARY,
        checks=checks,
    )


def _editable_fields(settings: Settings) -> list[EditableSettingsField]:
    return [
        EditableSettingsField(
            key=definition["key"],
            label=definition["label"],
            group=definition["group"],
            input_type=definition["input_type"],
            value=_field_value(settings, definition),
            configured=_field_configured(settings, definition["key"]),
            secret=definition["secret"],
            choices=list(definition.get("choices", [])),
            help_text=definition["help_text"],
        )
        for definition in FIELD_DEFINITIONS
    ]


def _field_value(settings: Settings, definition: dict[str, Any]) -> str | bool | int | None:
    key = definition["key"]
    if definition["secret"]:
        return None
    if key == "TUSHARE_ANNS_D_BEAT_ENABLED":
        return settings.tushare_anns_d_beat_enabled
    if key == "TUSHARE_ANNS_D_BEAT_INTERVAL_SECONDS":
        return settings.tushare_anns_d_beat_interval_seconds
    if key == "TELEGRAM_REQUIRE_BINDING":
        return settings.telegram_require_binding
    if key == "TELEGRAM_PUSH_ENABLED":
        return settings.telegram_push_enabled
    if key == "MODEL_ANALYSIS_ENABLED":
        return settings.model_analysis_enabled
    if key == "MODEL_PROVIDER":
        return settings.model_provider_normalized
    if key == "MODEL_AUDIT_STORE_RAW_PROMPT":
        return settings.model_audit_store_raw_prompt
    return None


def _field_configured(settings: Settings, key: str) -> bool:
    accessor = CONFIGURED_ACCESSORS.get(key)
    if accessor:
        return bool(getattr(settings, accessor))
    value = _field_value(settings, FIELD_BY_KEY[key])
    if isinstance(value, bool):
        return value
    return bool(value)


def _normalize_updates(
    payload: EditableSettingsUpdate,
) -> tuple[dict[str, str], set[str]]:
    updates: dict[str, str] = {}
    unchanged_secret_keys: set[str] = set()
    clear_keys = set(payload.clear)

    unknown_keys = (set(payload.values) | clear_keys) - set(FIELD_BY_KEY)
    if unknown_keys:
        raise ValueError(f"Unsupported settings keys: {', '.join(sorted(unknown_keys))}")

    for key in clear_keys:
        updates[key] = ""

    for key, raw_value in payload.values.items():
        if key in clear_keys:
            continue
        if key in SECRET_KEYS and _is_blank(raw_value):
            unchanged_secret_keys.add(key)
            continue
        updates[key] = _normalize_value(key, raw_value)

    return updates, unchanged_secret_keys


def _normalize_value(key: str, value: str | bool | int | None) -> str:
    if key in BOOLEAN_KEYS:
        return "true" if _parse_bool(key, value) else "false"
    if key in INTEGER_KEYS:
        return str(_parse_positive_int(key, value))

    text = "" if value is None else str(value).strip()
    if key == "MODEL_PROVIDER":
        value_normalized = text.lower()
        choices = set(FIELD_BY_KEY[key].get("choices", []))
        if value_normalized not in choices:
            raise ValueError("MODEL_PROVIDER must be disabled, openai, or custom.")
        return value_normalized
    if key == "MODEL_API_BASE_URL" and text:
        _validate_http_url_without_credentials(text)
    if key == "TELEGRAM_ALLOWED_CHAT_IDS" and text:
        _validate_chat_ids(text)
    return text


def _parse_bool(key: str, value: str | bool | int | None) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    text = "" if value is None else str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off", ""}:
        return False
    raise ValueError(f"{key} must be a boolean value.")


def _parse_positive_int(key: str, value: str | bool | int | None) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{key} must be a positive integer.")
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be a positive integer.") from exc
    if parsed <= 0:
        raise ValueError(f"{key} must be greater than 0.")
    return parsed


def _validate_http_url_without_credentials(value: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("MODEL_API_BASE_URL must be an HTTP(S) URL with a host.")
    if parsed.username or parsed.password:
        raise ValueError("MODEL_API_BASE_URL must not include embedded credentials.")


def _validate_chat_ids(value: str) -> None:
    invalid = [
        chat_id
        for chat_id in (part.strip() for part in value.split(","))
        if not chat_id or not re.fullmatch(r"-?\d+", chat_id)
    ]
    if invalid:
        raise ValueError("TELEGRAM_ALLOWED_CHAT_IDS must be comma-separated numeric chat ids.")


def _is_blank(value: str | bool | int | None) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _write_env_updates(env_file: Path, updates: dict[str, str]) -> None:
    existing_lines = (
        env_file.read_text(encoding="utf-8").splitlines()
        if env_file.exists()
        else _default_env_lines()
    )
    remaining_updates = dict(updates)
    written_lines: list[str] = []

    for line in existing_lines:
        match = ENV_KEY_PATTERN.match(line)
        if not match:
            written_lines.append(line)
            continue

        key = match.group(1)
        if key in remaining_updates:
            written_lines.append(f"{key}={_format_env_value(remaining_updates.pop(key))}")
        else:
            written_lines.append(line)

    if remaining_updates:
        if written_lines and written_lines[-1]:
            written_lines.append("")
        written_lines.append("# Local settings editor managed values.")
        for key in sorted(remaining_updates):
            written_lines.append(f"{key}={_format_env_value(remaining_updates[key])}")

    env_file.write_text("\n".join(written_lines).rstrip() + "\n", encoding="utf-8")


def _apply_process_env(updates: dict[str, str]) -> None:
    for key, value in updates.items():
        os.environ[key] = value


def _default_env_lines() -> list[str]:
    example_path = Path(".env.example")
    if example_path.exists():
        return example_path.read_text(encoding="utf-8").splitlines()
    return []


def _format_env_value(value: str) -> str:
    if value == "":
        return ""
    if re.search(r"\s|#|\"|\\", value):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


async def _run_single_connection_test(
    target: str,
    settings: Settings,
) -> SettingsConnectionCheck:
    try:
        if target == "tushare":
            return await _test_tushare_connection(settings)
        if target == "telegram":
            return await _test_telegram_connection(settings)
        if target == "model":
            return await _test_model_connection(settings)
    except Exception as exc:
        return SettingsConnectionCheck(
            name=target,
            status="fail",
            detail=_sanitize_test_detail(str(exc) or exc.__class__.__name__, settings),
        )

    return SettingsConnectionCheck(
        name=target,
        status="fail",
        detail="Unknown settings connection test target.",
    )


async def _test_tushare_connection(settings: Settings) -> SettingsConnectionCheck:
    if not settings.tushare_token_configured:
        return SettingsConnectionCheck(
            name="tushare",
            status="fail",
            detail="Tushare token is not configured.",
        )

    dataset = await TushareProvider(settings=settings).fetch("daily")
    if dataset.row_count <= 0:
        return SettingsConnectionCheck(
            name="tushare",
            status="warn",
            detail="Tushare responded but returned no daily rows for the default trade date.",
        )
    return SettingsConnectionCheck(
        name="tushare",
        status="ok",
        detail=f"Tushare daily responded with {dataset.row_count} rows.",
    )


async def _test_telegram_connection(settings: Settings) -> SettingsConnectionCheck:
    if not settings.telegram_bot_token_configured:
        return SettingsConnectionCheck(
            name="telegram",
            status="fail",
            detail="Telegram bot token is not configured.",
        )

    return await asyncio.to_thread(_telegram_get_me, settings)


def _telegram_get_me(settings: Settings) -> SettingsConnectionCheck:
    token = (settings.telegram_bot_token or "").strip()
    request = urllib.request.Request(
        url=f"https://api.telegram.org/bot{token}/getMe",
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=TELEGRAM_GET_ME_TIMEOUT_SECONDS,
        ) as response:
            raw_body = response.read()
    except urllib.error.HTTPError as exc:
        return SettingsConnectionCheck(
            name="telegram",
            status="fail",
            detail=f"Telegram getMe returned HTTP {exc.code}.",
        )
    except Exception as exc:
        return SettingsConnectionCheck(
            name="telegram",
            status="fail",
            detail=f"Telegram getMe transport failed: {exc.__class__.__name__}.",
        )

    response_payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    if response_payload.get("ok") is True:
        return SettingsConnectionCheck(
            name="telegram",
            status="ok",
            detail="Telegram getMe responded successfully.",
        )
    return SettingsConnectionCheck(
        name="telegram",
        status="fail",
        detail="Telegram getMe responded but did not return ok=true.",
    )


async def _test_model_connection(settings: Settings) -> SettingsConnectionCheck:
    if not settings.model_analysis_enabled or settings.model_provider_normalized == "disabled":
        return SettingsConnectionCheck(
            name="model",
            status="fail",
            detail="Model analysis or provider is disabled.",
        )

    readiness = evaluate_model_provider_readiness(settings)
    if readiness.get("status") != "ok":
        return SettingsConnectionCheck(
            name="model",
            status="fail",
            detail="Model provider readiness is not ok; fix settings before testing connection.",
        )

    try:
        client = build_model_client(settings)
    except ModelProviderConfigError as exc:
        return SettingsConnectionCheck(
            name="model",
            status="fail",
            detail=_sanitize_test_detail(str(exc), settings),
        )

    request = ModelCompletionRequest(
        call_site="settings.connection_test",
        messages=[
            ModelMessage(
                role="system",
                content="Return only a short JSON object for connectivity testing.",
            ),
            ModelMessage(role="user", content='Return {"ok": true}.'),
        ],
        response_format={"type": "json_object"},
        timeout_seconds=10.0,
    )
    response = await client.complete(request, model=settings.model_primary_model or "")
    if response.content.strip():
        return SettingsConnectionCheck(
            name="model",
            status="ok",
            detail="Model provider returned a chat completion response.",
        )
    return SettingsConnectionCheck(
        name="model",
        status="warn",
        detail="Model provider responded with empty content.",
    )


def _aggregate_connection_status(checks: list[SettingsConnectionCheck]) -> str:
    statuses = {check.status for check in checks}
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses or "warning" in statuses:
        return "warn"
    return "ok"


def _sanitize_test_detail(detail: str, settings: Settings) -> str:
    redacted = detail
    for secret in (
        settings.tushare_token,
        settings.telegram_bot_token,
        settings.telegram_allowed_chat_ids,
        settings.telegram_webhook_secret,
        settings.model_primary_model,
        settings.model_fallback_model,
        settings.model_api_base_url,
        settings.model_api_key,
        settings.openai_api_key,
        settings.settings_admin_token,
    ):
        if secret and secret.strip():
            redacted = redacted.replace(secret.strip(), "<redacted>")
    redacted = SECRET_DETAIL_PATTERN.sub(r"\1\2<redacted>", redacted)
    return LONG_SECRET_PATTERN.sub("<redacted>", redacted)


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
