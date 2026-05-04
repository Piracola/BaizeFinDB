import json
import os
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.providers.schemas import DataQualityStatus, ProviderDataset
from app.providers.tushare import TUSHARE_ENDPOINTS

DEFAULT_MAX_SAMPLE_ROWS = 2
MAX_SANITIZED_TEXT_LENGTH = 240
MAX_SANITIZED_MAPPING_ITEMS = 20
MAX_SANITIZED_SEQUENCE_ITEMS = 10
MAX_ERROR_TEXT_LENGTH = 800
SENSITIVE_FIELD_MARKERS = (
    "url",
    "source",
    "domain",
    "website",
    "link",
    "token",
    "password",
    "authorization",
    "api_key",
    "apikey",
    "access_key",
)
URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
DOMAIN_PATTERN = re.compile(
    r"\b(?:[a-z0-9-]+\.)+(?:com|cn|net|org|io|test|edu|gov|info|biz)\b",
    re.IGNORECASE,
)
TUSHARE_TOKEN_PATTERN = re.compile(r"(?i)\b(TUSHARE_TOKEN\s*(?:=|:)?\s*)([^\s,;]+)")
SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b((?:api[_-]?key|access[_-]?key|authorization|password|token|secret)"
    r"\s*[:=]\s*)([^\s,;&]+)"
)
BEARER_TOKEN_PATTERN = re.compile(r"(?i)\b(bearer\s+)([a-z0-9._~+/-]{12,})")
LONG_TOKEN_PATTERN = re.compile(r"\b[a-zA-Z0-9._~+/-]{24,}\b")


def build_success_report(
    *,
    endpoint: str,
    dataset: ProviderDataset,
    query_params: dict[str, object] | None = None,
    max_sample_rows: int = DEFAULT_MAX_SAMPLE_ROWS,
    extra_fields: dict[str, object] | None = None,
) -> dict[str, Any]:
    spec = TUSHARE_ENDPOINTS[endpoint]
    sample_limit = max(max_sample_rows, 0)
    report: dict[str, Any] = {
        "endpoint": endpoint,
        "status": "success",
        "query_params": _sanitize_mapping(query_params or {}),
        "row_count": dataset.row_count,
        "quality_status": dataset.quality.status.value,
        "quality": dataset.quality.model_dump(mode="json"),
        "required_fields": list(spec.required_fields),
        "missing_fields": list(dataset.quality.missing_fields),
        "field_presence": _field_presence(dataset.normalized_rows, spec.required_fields),
        "sample": [
            sanitize_normalized_row(row)
            for row in dataset.normalized_rows[:sample_limit]
        ],
    }
    if extra_fields:
        report.update(_sanitize_mapping(extra_fields))
    return report


def build_failure_report(
    *,
    endpoint: str,
    exc: Exception,
    query_params: dict[str, object] | None = None,
    extra_fields: dict[str, object] | None = None,
) -> dict[str, Any]:
    spec = TUSHARE_ENDPOINTS[endpoint]
    report: dict[str, Any] = {
        "endpoint": endpoint,
        "status": "failure",
        "query_params": _sanitize_mapping(query_params or {}),
        "row_count": 0,
        "quality_status": DataQualityStatus.FAILED.value,
        "quality": {
            "status": DataQualityStatus.FAILED.value,
            "confidence": 0,
            "freshness": spec.freshness,
            "missing_fields": list(spec.required_fields),
        },
        "required_fields": list(spec.required_fields),
        "missing_fields": list(spec.required_fields),
        "sample": [],
        "error": sanitize_error(exc),
    }
    if extra_fields:
        report.update(_sanitize_mapping(extra_fields))
    return report


def build_legacy_success_result(
    *,
    endpoint: str,
    dataset: ProviderDataset,
    max_sample_rows: int = DEFAULT_MAX_SAMPLE_ROWS,
    extra_fields: dict[str, object] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "endpoint": endpoint,
        "status": "success",
        "row_count": dataset.row_count,
        "quality": dataset.quality.model_dump(mode="json"),
        "sample": [
            sanitize_normalized_row(row)
            for row in dataset.normalized_rows[:max_sample_rows]
        ],
    }
    if extra_fields:
        result.update(_sanitize_mapping(extra_fields))
    return result


def build_legacy_failure_result(
    *,
    endpoint: str,
    exc: Exception,
    extra_fields: dict[str, object] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "endpoint": endpoint,
        "status": "failure",
        "error": sanitize_error(exc),
    }
    if extra_fields:
        result.update(_sanitize_mapping(extra_fields))
    return result


def write_json_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sanitize_normalized_row(row: dict[str, object]) -> dict[str, object]:
    sanitized: dict[str, object] = {}
    for key, value in row.items():
        if is_sensitive_field(key):
            continue
        sanitized[key] = sanitize_value(value)
    return sanitized


def sanitize_value(value: object) -> object:
    if isinstance(value, str):
        return bound_text(redact_text(value))
    if isinstance(value, int | float | bool) or value is None:
        return value
    if isinstance(value, Mapping):
        sanitized: dict[str, object] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= MAX_SANITIZED_MAPPING_ITEMS:
                sanitized["_truncated"] = True
                break
            key_text = str(key)
            if is_sensitive_field(key_text):
                continue
            sanitized[key_text] = sanitize_value(item)
        return sanitized
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        items: list[object] = [
            sanitize_value(item)
            for item in value[:MAX_SANITIZED_SEQUENCE_ITEMS]
        ]
        if len(value) > MAX_SANITIZED_SEQUENCE_ITEMS:
            items.append("<truncated>")
        return items
    return bound_text(redact_text(str(value)))


def sanitize_error(exc: Exception) -> str:
    return bound_text(redact_text(f"{exc.__class__.__name__}: {exc}"), MAX_ERROR_TEXT_LENGTH)


def redact_text(text: str) -> str:
    redacted = text
    token = os.environ.get("TUSHARE_TOKEN")

    if token:
        redacted = redacted.replace(token, "<redacted>")

    redacted = TUSHARE_TOKEN_PATTERN.sub(r"\1<redacted>", redacted)
    redacted = SECRET_ASSIGNMENT_PATTERN.sub(r"\1<redacted>", redacted)
    redacted = BEARER_TOKEN_PATTERN.sub(r"\1<redacted>", redacted)
    redacted = URL_PATTERN.sub("<redacted-url>", redacted)
    redacted = DOMAIN_PATTERN.sub("<redacted-domain>", redacted)
    return LONG_TOKEN_PATTERN.sub("<redacted>", redacted)


def bound_text(text: str, limit: int = MAX_SANITIZED_TEXT_LENGTH) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "...<truncated>"


def is_sensitive_field(field: str) -> bool:
    normalized = field.lower()
    if any(marker in normalized for marker in SENSITIVE_FIELD_MARKERS):
        return True
    return (
        normalized == "secret"
        or normalized.endswith("_secret")
        or normalized.endswith("-secret")
    )


def _field_presence(
    rows: list[dict[str, object]],
    required_fields: tuple[str, ...],
) -> dict[str, bool]:
    return {
        field: any(row.get(field) not in (None, "") for row in rows)
        for field in required_fields
    }


def _sanitize_mapping(values: dict[str, object]) -> dict[str, object]:
    return {
        key: ("<redacted>" if is_sensitive_field(key) else sanitize_value(value))
        for key, value in values.items()
    }
