"""Export sanitized read-only OPS evidence from a running BaizeFinDB API."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_LOOKBACK_HOURS = 24
DEFAULT_HISTORY_LIMIT = 20
MAX_TEXT_LENGTH = 500
MAX_MAPPING_ITEMS = 40
MAX_LIST_ITEMS = 20
MAX_RECENT_EVENTS = 10
REDACTED = "<redacted>"
REDACTED_URL = "<redacted-url>"
REDACTED_DOMAIN = "<redacted-domain>"

OPS_EVIDENCE_ENDPOINTS = (
    ("health", "/health", ()),
    ("health_ready", "/health/ready", ()),
    ("ops_overview", "/ops/overview", ("lookback_hours",)),
    ("ops_history", "/ops/history", ("lookback_hours", "limit")),
    ("ops_readiness", "/ops/readiness", ("lookback_hours",)),
)

SENSITIVE_FIELD_MARKERS = (
    "authorization",
    "api_key",
    "apikey",
    "access_key",
    "bearer",
    "credential",
    "domain",
    "dsn",
    "host",
    "link",
    "password",
    "provider_url",
    "secret",
    "source",
    "token",
    "url",
    "webhook",
    "website",
)
URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
DOMAIN_PATTERN = re.compile(
    r"\b(?:[a-z0-9-]+\.)+(?:com|cn|net|org|io|test|edu|gov|info|biz)\b",
    re.IGNORECASE,
)
SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b((?:api[_-]?key|access[_-]?key|authorization|password|token|secret)"
    r"\s*[:=]\s*)([^\s,;&]+)"
)
BEARER_TOKEN_PATTERN = re.compile(r"(?i)\b(bearer\s+)([a-z0-9._~+/-]{12,})")
LONG_TOKEN_PATTERN = re.compile(r"\b(?=[a-zA-Z0-9._~+/-]{24,}\b)(?=.*\d)[a-zA-Z0-9._~+/-]+\b")


@dataclass(frozen=True)
class EndpointRead:
    name: str
    path: str
    status: str
    http_status: int | None = None
    payload: dict[str, Any] | None = None
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def build_endpoint_path(
    path: str,
    query_keys: tuple[str, ...],
    *,
    lookback_hours: int,
    history_limit: int,
) -> str:
    query: dict[str, int] = {}
    if "lookback_hours" in query_keys:
        query["lookback_hours"] = lookback_hours
    if "limit" in query_keys:
        query["limit"] = history_limit
    if not query:
        return path
    return f"{path}?{urlencode(query)}"


def fetch_json_endpoint(
    base_url: str,
    name: str,
    path: str,
    *,
    timeout: int,
) -> EndpointRead:
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    request = Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310
            body = response.read().decode("utf-8", errors="replace")
            http_status = getattr(response, "status", None)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return EndpointRead(
            name=name,
            path=path,
            status="fail",
            http_status=exc.code,
            payload=_load_json_object(body),
            error=f"HTTP {exc.code}: {bound_text(redact_text(body))}",
        )
    except (TimeoutError, URLError, OSError) as exc:
        return EndpointRead(
            name=name,
            path=path,
            status="fail",
            error=bound_text(redact_text(f"{exc.__class__.__name__}: {exc}")),
        )

    payload = _load_json_object(body)
    if payload is None:
        return EndpointRead(
            name=name,
            path=path,
            status="fail",
            http_status=http_status,
            error=f"response is not a JSON object: {bound_text(redact_text(body))}",
        )

    return EndpointRead(
        name=name,
        path=path,
        status="ok",
        http_status=http_status,
        payload=payload,
    )


def collect_ops_evidence(
    base_url: str,
    *,
    lookback_hours: int,
    history_limit: int,
    timeout: int,
) -> list[EndpointRead]:
    reads: list[EndpointRead] = []
    for name, path, query_keys in OPS_EVIDENCE_ENDPOINTS:
        full_path = build_endpoint_path(
            path,
            query_keys,
            lookback_hours=lookback_hours,
            history_limit=history_limit,
        )
        reads.append(fetch_json_endpoint(base_url, name, full_path, timeout=timeout))
    return reads


def build_evidence_report(
    reads: list[EndpointRead],
    *,
    base_url: str,
    lookback_hours: int,
    history_limit: int,
) -> dict[str, Any]:
    endpoint_map = {read.name: read for read in reads}
    overview = _payload(endpoint_map.get("ops_overview"))
    history = _payload(endpoint_map.get("ops_history"))
    readiness = _payload(endpoint_map.get("ops_readiness"))
    health = _payload(endpoint_map.get("health"))
    health_ready = _payload(endpoint_map.get("health_ready"))

    endpoint_failures = [
        {
            "endpoint": read.name,
            "path": read.path,
            "http_status": read.http_status,
            "error": read.error,
        }
        for read in reads
        if not read.ok
    ]
    readiness_status = _readiness_status(readiness)
    blocked = readiness_status == "blocked"
    status = "error" if endpoint_failures else "blocked" if blocked else "ok"

    recent_events = _list_of_dicts(history.get("recent_events") if history else None)
    bounded_events = recent_events[:MAX_RECENT_EVENTS]

    return {
        "generated_at": _now_iso(),
        "report_type": "ops_evidence",
        "status": status,
        "summary": {
            "status": status,
            "readiness_status": readiness_status,
            "health_status": sanitize_value(health.get("status") if health else "unknown"),
            "health_ready_status": sanitize_value(
                health_ready.get("status") if health_ready else "unknown"
            ),
            "endpoint_failures_count": len(endpoint_failures),
            "blocked": blocked,
            "warning_non_fatal": readiness_status == "warning",
        },
        "request": {
            "base_url": REDACTED_URL,
            "lookback_hours": lookback_hours,
            "history_limit": history_limit,
            "allowed_endpoints": [path for _, path, _ in OPS_EVIDENCE_ENDPOINTS],
            "boundary": (
                "read-only HTTP GET evidence export; no collection, scan, push, "
                "provider, model, backup, cleanup, or database calls"
            ),
        },
        "endpoint_reads": [
            {
                "endpoint": read.name,
                "path": read.path,
                "status": read.status,
                "http_status": read.http_status,
                "error": sanitize_value(read.error) if read.error else "",
            }
            for read in reads
        ],
        "alerts": sanitize_value(overview.get("alerts") if overview else []),
        "readiness_checks": sanitize_value(readiness.get("checks") if readiness else []),
        "failure_summary": sanitize_value(history.get("failure_summary") if history else []),
        "recent_events_count": len(recent_events),
        "recent_events": sanitize_value(bounded_events),
        "recent_events_truncated": len(recent_events) > len(bounded_events),
        "snapshots": {
            "health": sanitize_value(health or {}),
            "health_ready": sanitize_value(health_ready or {}),
            "ops_overview": sanitize_value(overview or {}),
            "ops_history": sanitize_value(history or {}),
            "ops_readiness": sanitize_value(readiness or {}),
        },
        "failures": sanitize_value(endpoint_failures),
    }


def exit_code_for_report(report: dict[str, Any]) -> int:
    if report.get("status") in {"blocked", "error"}:
        return 1
    return 0


def sanitize_value(value: object) -> object:
    if isinstance(value, str):
        return bound_text(redact_text(value))
    if isinstance(value, int | float | bool) or value is None:
        return value
    if isinstance(value, dict):
        sanitized: dict[str, object] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= MAX_MAPPING_ITEMS:
                sanitized["_truncated"] = True
                sanitized["_original_item_count"] = len(value)
                break
            key_text = str(key)
            sanitized[key_text] = REDACTED if is_sensitive_field(key_text) else sanitize_value(item)
        return sanitized
    if isinstance(value, list | tuple):
        items = [sanitize_value(item) for item in value[:MAX_LIST_ITEMS]]
        if len(value) > MAX_LIST_ITEMS:
            items.append(
                {
                    "_truncated": True,
                    "_original_item_count": len(value),
                }
            )
        return items
    return bound_text(redact_text(str(value)))


def redact_text(text: str) -> str:
    redacted = SECRET_ASSIGNMENT_PATTERN.sub(r"\1<redacted>", text)
    redacted = BEARER_TOKEN_PATTERN.sub(r"\1<redacted>", redacted)
    redacted = URL_PATTERN.sub(REDACTED_URL, redacted)
    redacted = DOMAIN_PATTERN.sub(REDACTED_DOMAIN, redacted)
    return LONG_TOKEN_PATTERN.sub(REDACTED, redacted)


def is_sensitive_field(field: str) -> bool:
    normalized = field.lower()
    return any(marker in normalized for marker in SENSITIVE_FIELD_MARKERS)


def bound_text(text: str, limit: int = MAX_TEXT_LENGTH) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...<truncated>"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export sanitized read-only OPS evidence from a running BaizeFinDB API.",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"API base URL, default: {DEFAULT_BASE_URL}",
    )
    parser.add_argument(
        "--lookback-hours",
        type=int,
        default=DEFAULT_LOOKBACK_HOURS,
        help=f"OPS lookback window, default: {DEFAULT_LOOKBACK_HOURS}.",
    )
    parser.add_argument(
        "--history-limit",
        type=int,
        default=DEFAULT_HISTORY_LIMIT,
        help=f"OPS history event limit, default: {DEFAULT_HISTORY_LIMIT}.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=5,
        help="HTTP timeout per request in seconds, default: 5.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        help="Optional path to write the sanitized JSON evidence report.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.lookback_hours < 1:
        print("[FAIL] --lookback-hours must be >= 1", file=sys.stderr)
        return 2
    if args.history_limit < 1:
        print("[FAIL] --history-limit must be >= 1", file=sys.stderr)
        return 2
    if args.timeout < 1:
        print("[FAIL] --timeout must be >= 1", file=sys.stderr)
        return 2

    reads = collect_ops_evidence(
        args.base_url,
        lookback_hours=args.lookback_hours,
        history_limit=args.history_limit,
        timeout=args.timeout,
    )
    report = build_evidence_report(
        reads,
        base_url=args.base_url,
        lookback_hours=args.lookback_hours,
        history_limit=args.history_limit,
    )
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return exit_code_for_report(report)


def _payload(read: EndpointRead | None) -> dict[str, Any] | None:
    if read is None or read.payload is None:
        return None
    return read.payload


def _readiness_status(payload: dict[str, Any] | None) -> str:
    if not payload:
        return "unknown"
    status = str(payload.get("status") or "unknown")
    if status in {"ready", "warning", "blocked"}:
        return status
    return "unknown"


def _list_of_dicts(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _load_json_object(body: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


if __name__ == "__main__":
    sys.exit(main())
