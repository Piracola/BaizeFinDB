import argparse
import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any

from app.providers.schemas import DataQualityStatus, ProviderDataset
from app.providers.tushare import TUSHARE_ENDPOINTS, TushareProvider

ENDPOINT = "anns_d"
DEFAULT_MAX_SAMPLE_ROWS = 2
SENSITIVE_FIELD_MARKERS = (
    "url",
    "source",
    "domain",
    "website",
    "link",
    "token",
    "secret",
)
URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
DOMAIN_PATTERN = re.compile(
    r"\b(?:[a-z0-9-]+\.)+(?:com|cn|net|org|io|test|edu|gov|info|biz)\b",
    re.IGNORECASE,
)
TUSHARE_TOKEN_PATTERN = re.compile(
    r"(?i)\b(TUSHARE_TOKEN\s*(?:=|:)?\s*)([^\s,;]+)"
)
SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b((?:api[_-]?key|token|secret)\s*[:=]\s*)([^\s,;&]+)"
)


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify Tushare announcements without DB writes."
    )
    parser.add_argument(
        "--ann-date",
        help="Announcement date in YYYYMMDD format. Defaults to today.",
    )
    parser.add_argument(
        "--json-output",
        help="Optional path for a sanitized JSON evidence report.",
    )
    parser.add_argument(
        "--max-sample-rows",
        type=int,
        default=DEFAULT_MAX_SAMPLE_ROWS,
        help="Maximum sanitized normalized rows to include in the report.",
    )
    args = parser.parse_args()

    provider = TushareProvider()
    query_params = {"ann_date": args.ann_date} if args.ann_date else None

    try:
        dataset = await provider.fetch(ENDPOINT, query_params=query_params)
        report = build_success_report(
            dataset=dataset,
            ann_date=args.ann_date,
            max_sample_rows=args.max_sample_rows,
        )
        result = (
            report
            if args.json_output
            else build_legacy_success_result(dataset=dataset)
        )
    except Exception as exc:
        report = build_failure_report(exc=exc, ann_date=args.ann_date)
        result = report if args.json_output else build_legacy_failure_result(exc=exc)

    if args.json_output:
        write_json_report(Path(args.json_output), report)

    print(json.dumps(result, ensure_ascii=False, indent=2))


def build_success_report(
    dataset: ProviderDataset,
    ann_date: str | None,
    max_sample_rows: int = DEFAULT_MAX_SAMPLE_ROWS,
) -> dict[str, Any]:
    spec = TUSHARE_ENDPOINTS[ENDPOINT]
    quality = dataset.quality.model_dump(mode="json")
    sample_limit = max(max_sample_rows, 0)

    return {
        "endpoint": ENDPOINT,
        "status": "success",
        "ann_date": ann_date or _infer_ann_date(dataset.normalized_rows),
        "row_count": dataset.row_count,
        "quality_status": dataset.quality.status.value,
        "quality": quality,
        "required_fields": list(spec.required_fields),
        "missing_fields": list(dataset.quality.missing_fields),
        "field_presence": _field_presence(dataset.normalized_rows, spec.required_fields),
        "sample": [
            _sanitize_normalized_row(row)
            for row in dataset.normalized_rows[:sample_limit]
        ],
    }


def build_failure_report(exc: Exception, ann_date: str | None) -> dict[str, Any]:
    spec = TUSHARE_ENDPOINTS[ENDPOINT]

    return {
        "endpoint": ENDPOINT,
        "status": "failure",
        "ann_date": ann_date,
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
        "error": _sanitize_error(exc),
    }


def build_legacy_success_result(dataset: ProviderDataset) -> dict[str, Any]:
    return {
        "endpoint": ENDPOINT,
        "status": "success",
        "row_count": dataset.row_count,
        "quality": dataset.quality.model_dump(mode="json"),
        "sample": [
            _sanitize_normalized_row(row)
            for row in dataset.normalized_rows[:DEFAULT_MAX_SAMPLE_ROWS]
        ],
    }


def build_legacy_failure_result(exc: Exception) -> dict[str, Any]:
    return {
        "endpoint": ENDPOINT,
        "status": "failure",
        "error": _sanitize_error(exc),
    }


def write_json_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sanitize_normalized_row(row: dict[str, object]) -> dict[str, object]:
    sanitized: dict[str, object] = {}

    for key, value in row.items():
        if _is_sensitive_field(key):
            continue
        sanitized[key] = _sanitize_value(value)

    return sanitized


def _sanitize_value(value: object) -> object:
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, int | float | bool) or value is None:
        return value
    return _redact_text(str(value))


def _sanitize_error(exc: Exception) -> str:
    return _redact_text(f"{exc.__class__.__name__}: {exc}")[:800]


def _redact_text(text: str) -> str:
    redacted = text
    token = os.environ.get("TUSHARE_TOKEN")

    if token:
        redacted = redacted.replace(token, "<redacted>")

    redacted = TUSHARE_TOKEN_PATTERN.sub(r"\1<redacted>", redacted)
    redacted = SECRET_ASSIGNMENT_PATTERN.sub(r"\1<redacted>", redacted)
    redacted = URL_PATTERN.sub("<redacted-url>", redacted)
    return DOMAIN_PATTERN.sub("<redacted-domain>", redacted)


def _field_presence(
    rows: list[dict[str, object]],
    required_fields: tuple[str, ...],
) -> dict[str, bool]:
    return {
        field: any(row.get(field) not in (None, "") for row in rows)
        for field in required_fields
    }


def _infer_ann_date(rows: list[dict[str, object]]) -> str | None:
    for row in rows:
        value = row.get("ann_date")
        if isinstance(value, str) and value:
            return value
    return None


def _is_sensitive_field(field: str) -> bool:
    normalized = field.lower()
    return any(marker in normalized for marker in SENSITIVE_FIELD_MARKERS)


if __name__ == "__main__":
    asyncio.run(main())
