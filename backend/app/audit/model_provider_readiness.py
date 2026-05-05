"""Read-only model provider readiness checks for future LLM-backed flows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from app.core.config import Settings, get_settings

REPORT_TYPE = "model_provider_readiness"
SUPPORTED_MODEL_PROVIDERS = ("disabled", "openai", "custom")
READ_ONLY_BOUNDARY = (
    "Model provider readiness preflight; reads configuration only; does not call "
    "model APIs, validate tokens over the network, read databases, collect providers, "
    "run radar scans, create reports, send Telegram messages, perform backups, or "
    "take trading actions; never prints API keys, authorization values, raw prompts, "
    "model responses, or env file contents"
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    detail: str
    metadata: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
        }
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload


def evaluate_model_provider_readiness(
    settings: Settings | None = None,
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    current_settings = settings or get_settings()
    timestamp = generated_at or datetime.now(UTC)
    provider = current_settings.model_provider_normalized

    checks = [
        _provider_check(provider),
        _enablement_check(current_settings, provider),
        _primary_model_check(current_settings, provider),
        _fallback_model_check(current_settings, provider),
        _credential_check(current_settings, provider),
        _custom_base_url_check(current_settings, provider),
        _raw_prompt_storage_check(current_settings),
    ]
    summary = _summary(checks)

    return {
        "generated_at": timestamp.isoformat(),
        "report_type": REPORT_TYPE,
        "status": _overall_status(summary),
        "read_only_boundary": READ_ONLY_BOUNDARY,
        "configuration": _configuration_metadata(current_settings, provider),
        "summary": summary,
        "checks": [check.as_dict() for check in checks],
    }


def _provider_check(provider: str) -> CheckResult:
    if provider in SUPPORTED_MODEL_PROVIDERS:
        return CheckResult(
            "model provider",
            "ok",
            f"provider is {provider}",
            {"provider": provider, "supported": list(SUPPORTED_MODEL_PROVIDERS)},
        )
    return CheckResult(
        "model provider",
        "fail",
        "MODEL_PROVIDER must be one of disabled, openai, or custom",
        {"provider": provider, "supported": list(SUPPORTED_MODEL_PROVIDERS)},
    )


def _enablement_check(settings: Settings, provider: str) -> CheckResult:
    if not settings.model_analysis_enabled:
        status = "ok" if provider == "disabled" else "warn"
        detail = (
            "model analysis is disabled; deterministic analysis scaffold remains active"
            if status == "ok"
            else "MODEL_PROVIDER is configured but MODEL_ANALYSIS_ENABLED is false"
        )
        return CheckResult(
            "model analysis enablement",
            status,
            detail,
            {"enabled": False, "provider": provider},
        )

    if provider == "disabled":
        return CheckResult(
            "model analysis enablement",
            "fail",
            "MODEL_ANALYSIS_ENABLED=true requires MODEL_PROVIDER=openai or custom",
            {"enabled": True, "provider": provider},
        )

    return CheckResult(
        "model analysis enablement",
        "ok",
        "model analysis is explicitly enabled",
        {"enabled": True, "provider": provider},
    )


def _primary_model_check(settings: Settings, provider: str) -> CheckResult:
    if not settings.model_analysis_enabled or provider == "disabled":
        return CheckResult(
            "primary model",
            "ok",
            "primary model is not required while model analysis is disabled",
            {"configured": settings.model_primary_model_configured},
        )

    if settings.model_primary_model_configured:
        return CheckResult(
            "primary model",
            "ok",
            "primary model is configured",
            {"configured": True, "model": settings.model_primary_model.strip()},
        )

    return CheckResult(
        "primary model",
        "fail",
        "MODEL_PRIMARY_MODEL is required when model analysis is enabled",
        {"configured": False},
    )


def _fallback_model_check(settings: Settings, provider: str) -> CheckResult:
    if not settings.model_analysis_enabled or provider == "disabled":
        return CheckResult(
            "fallback model",
            "ok",
            "fallback model is optional while model analysis is disabled",
            {"configured": settings.model_fallback_model_configured},
        )

    if settings.model_fallback_model_configured:
        return CheckResult(
            "fallback model",
            "ok",
            "fallback model is configured",
            {"configured": True, "model": settings.model_fallback_model.strip()},
        )

    return CheckResult(
        "fallback model",
        "warn",
        "MODEL_FALLBACK_MODEL is not configured; model failures can only degrade",
        {"configured": False},
    )


def _credential_check(settings: Settings, provider: str) -> CheckResult:
    if not settings.model_analysis_enabled or provider == "disabled":
        return CheckResult(
            "model credentials",
            "ok",
            "model credentials are not required while model analysis is disabled",
            _credential_metadata(settings),
        )

    if provider == "openai":
        if settings.openai_api_key_configured:
            return CheckResult(
                "model credentials",
                "ok",
                "OPENAI_API_KEY is configured",
                _credential_metadata(settings),
            )
        return CheckResult(
            "model credentials",
            "fail",
            "OPENAI_API_KEY is required for MODEL_PROVIDER=openai",
            _credential_metadata(settings),
        )

    if provider == "custom":
        if settings.model_api_key_configured:
            return CheckResult(
                "model credentials",
                "ok",
                "MODEL_API_KEY is configured",
                _credential_metadata(settings),
            )
        return CheckResult(
            "model credentials",
            "fail",
            "MODEL_API_KEY is required for MODEL_PROVIDER=custom",
            _credential_metadata(settings),
        )

    return CheckResult(
        "model credentials",
        "fail",
        "unsupported MODEL_PROVIDER prevents credential evaluation",
        _credential_metadata(settings),
    )


def _custom_base_url_check(settings: Settings, provider: str) -> CheckResult:
    if not settings.model_analysis_enabled or provider != "custom":
        return CheckResult(
            "custom model base URL",
            "ok",
            "custom base URL is not required for this provider state",
            _base_url_metadata(settings.model_api_base_url),
        )

    if not settings.model_api_base_url_configured:
        return CheckResult(
            "custom model base URL",
            "fail",
            "MODEL_API_BASE_URL is required for MODEL_PROVIDER=custom",
            _base_url_metadata(settings.model_api_base_url),
        )

    parsed = urlparse(settings.model_api_base_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return CheckResult(
            "custom model base URL",
            "fail",
            "MODEL_API_BASE_URL must be an HTTP(S) URL with a host",
            _base_url_metadata(settings.model_api_base_url),
        )
    if _safe_port(parsed) == "invalid":
        return CheckResult(
            "custom model base URL",
            "fail",
            "MODEL_API_BASE_URL has an invalid port",
            _base_url_metadata(settings.model_api_base_url),
        )
    if parsed.username or parsed.password:
        return CheckResult(
            "custom model base URL",
            "fail",
            "MODEL_API_BASE_URL must not embed credentials",
            _base_url_metadata(settings.model_api_base_url),
        )

    return CheckResult(
        "custom model base URL",
        "ok",
        "custom model base URL is configured",
        _base_url_metadata(settings.model_api_base_url),
    )


def _raw_prompt_storage_check(settings: Settings) -> CheckResult:
    if settings.model_audit_store_raw_prompt:
        return CheckResult(
            "raw prompt storage",
            "warn",
            "MODEL_AUDIT_STORE_RAW_PROMPT=true; use only for explicit debug sessions",
            {"raw_prompt_storage_enabled": True},
        )
    return CheckResult(
        "raw prompt storage",
        "ok",
        "raw prompt storage is disabled",
        {"raw_prompt_storage_enabled": False},
    )


def _configuration_metadata(settings: Settings, provider: str) -> dict[str, Any]:
    return {
        "model_analysis_enabled": settings.model_analysis_enabled,
        "model_provider": provider,
        "primary_model": _configured_model_name(settings.model_primary_model),
        "fallback_model": _configured_model_name(settings.model_fallback_model),
        "custom_base_url": _base_url_metadata(settings.model_api_base_url),
        "credentials": _credential_metadata(settings),
        "raw_prompt_storage_enabled": settings.model_audit_store_raw_prompt,
    }


def _configured_model_name(value: str | None) -> dict[str, Any]:
    if not _is_configured(value):
        return {"configured": False, "name": None}
    return {"configured": True, "name": value.strip()}


def _credential_metadata(settings: Settings) -> dict[str, bool]:
    return {
        "openai_api_key_configured": settings.openai_api_key_configured,
        "model_api_key_configured": settings.model_api_key_configured,
    }


def _base_url_metadata(value: str | None) -> dict[str, Any]:
    if not _is_configured(value):
        return {
            "configured": False,
            "scheme": None,
            "host": None,
            "port": None,
            "path_configured": False,
            "credentials_embedded": False,
        }

    parsed = urlparse(value.strip())
    return {
        "configured": True,
        "scheme": parsed.scheme or None,
        "host": parsed.hostname,
        "port": _safe_port(parsed),
        "path_configured": bool(parsed.path and parsed.path != "/"),
        "credentials_embedded": bool(parsed.username or parsed.password),
    }


def _summary(checks: list[CheckResult]) -> dict[str, int]:
    return {
        "check_count": len(checks),
        "ok_count": sum(1 for check in checks if check.status == "ok"),
        "warning_count": sum(1 for check in checks if check.status == "warn"),
        "failure_count": sum(1 for check in checks if check.status == "fail"),
    }


def _overall_status(summary: dict[str, int]) -> str:
    if summary["failure_count"]:
        return "fail"
    if summary["warning_count"]:
        return "warn"
    return "ok"


def _is_configured(value: str | None) -> bool:
    return bool(value and value.strip())


def _safe_port(parsed: Any) -> int | str | None:
    try:
        return parsed.port
    except ValueError:
        return "invalid"
