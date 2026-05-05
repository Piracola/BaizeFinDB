"""Build a notification-ready alert payload from a monitor summary JSON file.

The script is deliberately filesystem-only. It does not collect runtime data and
does not send alerts; later adapters can consume the bounded JSON payload.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import export_ops_evidence  # noqa: E402

DEFAULT_MAX_ITEMS = 8
MAX_ITEMS = 50
MAX_MESSAGE_LENGTH = 360
READ_ONLY_BOUNDARY = (
    "filesystem-only alert payload builder; reads an existing monitor summary "
    "JSON and writes bounded JSON for later delivery adapters; does not call API, "
    "Docker, providers, radar scans, Telegram, models, reports, backups, cleanup, "
    "database writes, webhooks, SMTP, or notification senders"
)
VALID_MONITOR_STATUSES = {"ok", "warning", "blocked"}


class AlertPayloadInputError(ValueError):
    """Raised when the monitor summary cannot be converted into an alert payload."""


def build_alert_payload(
    monitor_summary: dict[str, Any],
    *,
    source_path: Path | None = None,
    max_items: int = DEFAULT_MAX_ITEMS,
    suppress_warning_notify: bool = False,
    include_ok: bool = False,
) -> dict[str, Any]:
    _validate_monitor_summary(monitor_summary)

    status = str(monitor_summary["status"])
    severity = severity_for_status(status)
    should_notify = should_notify_for_status(
        status,
        suppress_warning_notify=suppress_warning_notify,
        include_ok=include_ok,
    )
    bounded_max_items = max(min(max_items, MAX_ITEMS), 0)
    items = build_alert_items(monitor_summary, max_items=bounded_max_items)
    summary = build_payload_summary(monitor_summary)
    title = build_title(status)
    message = build_message(status, severity, summary)

    payload: dict[str, Any] = {
        "report_type": "server_alert_payload",
        "generated_at": _now_iso(),
        "source_monitor_summary": {
            "path": _safe_path_text(str(source_path)) if source_path else "",
            "report_type": _safe_text(str(monitor_summary.get("report_type") or "")),
            "generated_at": _safe_text(str(monitor_summary.get("generated_at") or "")),
            "status": status,
            "runtime_status": _safe_text(str(monitor_summary.get("runtime_status") or "")),
            "base_url": export_ops_evidence.REDACTED_URL,
        },
        "status": status,
        "severity": severity,
        "should_notify": should_notify,
        "dedupe_key": build_dedupe_key(status, summary, items),
        "title": title,
        "message": message,
        "summary": summary,
        "items": items,
        "items_truncated": _monitor_items_count(monitor_summary) > len(items),
        "boundary": READ_ONLY_BOUNDARY,
    }
    return payload


def severity_for_status(status: str) -> str:
    if status == "blocked":
        return "critical"
    if status == "warning":
        return "warning"
    return "info"


def should_notify_for_status(
    status: str,
    *,
    suppress_warning_notify: bool,
    include_ok: bool,
) -> bool:
    if status == "blocked":
        return True
    if status == "warning":
        return not suppress_warning_notify
    return include_ok


def build_alert_items(
    monitor_summary: dict[str, Any],
    *,
    max_items: int,
) -> list[dict[str, Any]]:
    failures = _list_of_dicts(monitor_summary.get("top_failures"))
    warnings = _list_of_dicts(monitor_summary.get("top_warnings"))
    items: list[dict[str, Any]] = []

    for failure in failures:
        items.append(
            {
                "severity": "critical",
                "kind": "failure",
                "sample": failure.get("sample"),
                "endpoint": failure.get("endpoint"),
                "path": failure.get("path"),
                "http_status": failure.get("http_status"),
                "detail": failure.get("error") or failure.get("detail") or "",
            }
        )

    for warning in warnings:
        kind = str(warning.get("kind") or "warning")
        items.append(
            {
                "severity": "warning",
                "kind": kind,
                "sample": warning.get("sample"),
                "code": warning.get("code"),
                "key": warning.get("key"),
                "status": warning.get("status"),
                "detail": warning.get("message") or warning.get("detail") or warning,
            }
        )

    return [
        export_ops_evidence.sanitize_value(item)  # type: ignore[arg-type]
        for item in items[:max_items]
    ]


def build_payload_summary(monitor_summary: dict[str, Any]) -> dict[str, Any]:
    summary = _dict_or_empty(monitor_summary.get("summary"))
    return {
        "failure_count": _as_int(summary.get("failure_count")),
        "warning_count": _as_int(summary.get("warning_count")),
        "readiness_status_counts": export_ops_evidence.sanitize_value(
            _dict_or_empty(summary.get("readiness_status_counts"))
        ),
        "alert_counts": export_ops_evidence.sanitize_value(
            _dict_or_empty(summary.get("alert_counts"))
        ),
        "runtime_status": _safe_text(str(monitor_summary.get("runtime_status") or "")),
        "strict_warning_failure": bool(monitor_summary.get("strict_warning_failure")),
        "sample_count": _as_int(monitor_summary.get("sample_count")),
        "started_at": _safe_text(str(monitor_summary.get("started_at") or "")),
        "finished_at": _safe_text(str(monitor_summary.get("finished_at") or "")),
        "latest_server": export_ops_evidence.sanitize_value(
            _dict_or_empty(summary.get("latest_server"))
        ),
        "latest_trend": export_ops_evidence.sanitize_value(
            _dict_or_empty(summary.get("latest_trend"))
        ),
    }


def build_dedupe_key(
    status: str,
    summary: dict[str, Any],
    items: list[dict[str, Any]],
) -> str:
    fingerprint_source = {
        "status": status,
        "runtime_status": summary.get("runtime_status"),
        "failure_count": summary.get("failure_count"),
        "warning_count": summary.get("warning_count"),
        "alert_counts": summary.get("alert_counts"),
        "first_items": [
            {
                "severity": item.get("severity"),
                "kind": item.get("kind"),
                "endpoint": item.get("endpoint"),
                "code": item.get("code"),
                "key": item.get("key"),
                "status": item.get("status"),
            }
            for item in items[:3]
        ],
    }
    encoded = json.dumps(fingerprint_source, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:12]
    return f"baizefindb:{status}:{digest}"


def build_title(status: str) -> str:
    if status == "blocked":
        return "BaizeFinDB server blocked"
    if status == "warning":
        return "BaizeFinDB server warning"
    return "BaizeFinDB server ok"


def build_message(status: str, severity: str, summary: dict[str, Any]) -> str:
    text = (
        f"status={status} severity={severity} "
        f"runtime_status={summary.get('runtime_status')} "
        f"failures={summary.get('failure_count')} "
        f"warnings={summary.get('warning_count')} "
        f"readiness={summary.get('readiness_status_counts')} "
        f"alerts={summary.get('alert_counts')}"
    )
    return export_ops_evidence.bound_text(
        export_ops_evidence.redact_text(text),
        limit=MAX_MESSAGE_LENGTH,
    )


def exit_code_for_payload(
    payload: dict[str, Any],
    *,
    fail_on_notify: bool = False,
) -> int:
    if payload.get("severity") == "critical":
        return 1
    if fail_on_notify and payload.get("should_notify") is True:
        return 1
    return 0


def load_monitor_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise AlertPayloadInputError(f"monitor summary does not exist: {path}")
    if path.is_symlink() or not path.is_file():
        raise AlertPayloadInputError(f"monitor summary must be a regular file: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AlertPayloadInputError(f"monitor summary is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise AlertPayloadInputError("monitor summary must be a JSON object")
    return payload


def write_json_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a bounded no-send alert payload from monitor summary JSON.",
    )
    parser.add_argument(
        "monitor_summary",
        nargs="?",
        type=Path,
        help="Path to server_monitor_check.py compact monitor summary JSON.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        help="Optional path to write the alert payload JSON.",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=DEFAULT_MAX_ITEMS,
        help=f"Maximum alert items to include, 0-{MAX_ITEMS}, default: {DEFAULT_MAX_ITEMS}.",
    )
    parser.add_argument(
        "--suppress-warning-notify",
        action="store_true",
        help="Build warning payloads but set should_notify=false for warning status.",
    )
    parser.add_argument(
        "--include-ok",
        action="store_true",
        help="Set should_notify=true for ok payloads.",
    )
    parser.add_argument(
        "--fail-on-notify",
        action="store_true",
        help="Return non-zero whenever the generated payload should notify.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    validation_error = _validate_args(args)
    if validation_error:
        print(f"[FAIL] {validation_error}", file=sys.stderr)
        return 2

    try:
        monitor_summary = load_monitor_summary(args.monitor_summary)
        payload = build_alert_payload(
            monitor_summary,
            source_path=args.monitor_summary,
            max_items=args.max_items,
            suppress_warning_notify=args.suppress_warning_notify,
            include_ok=args.include_ok,
        )
    except AlertPayloadInputError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2

    if args.json_output:
        write_json_report(args.json_output, payload)
        print(_format_summary(payload, args.json_output))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code_for_payload(payload, fail_on_notify=args.fail_on_notify)


def _validate_args(args: argparse.Namespace) -> str:
    if args.monitor_summary is None:
        return "monitor summary path is required"
    if args.max_items < 0 or args.max_items > MAX_ITEMS:
        return f"--max-items must be between 0 and {MAX_ITEMS}"
    return ""


def _validate_monitor_summary(monitor_summary: dict[str, Any]) -> None:
    if monitor_summary.get("report_type") != "server_monitor_summary":
        raise AlertPayloadInputError(
            "monitor summary report_type must be 'server_monitor_summary'"
        )
    status = str(monitor_summary.get("status") or "")
    if status not in VALID_MONITOR_STATUSES:
        raise AlertPayloadInputError(
            "monitor summary status must be one of ok, warning, blocked"
        )
    if not isinstance(monitor_summary.get("summary"), dict):
        raise AlertPayloadInputError("monitor summary must include a summary object")


def _format_summary(payload: dict[str, Any], output_path: Path) -> str:
    return (
        f"[{str(payload['severity']).upper()}] {payload['title']} "
        f"notify={payload['should_notify']} dedupe_key={payload['dedupe_key']} "
        f"json_output={output_path}"
    )


def _monitor_items_count(monitor_summary: dict[str, Any]) -> int:
    return len(_list_of_dicts(monitor_summary.get("top_failures"))) + len(
        _list_of_dicts(monitor_summary.get("top_warnings"))
    )


def _dict_or_empty(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_of_dicts(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _as_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int | float):
        return int(value)
    return 0


def _safe_text(value: str) -> str:
    return export_ops_evidence.bound_text(export_ops_evidence.redact_text(value))


def _safe_path_text(value: str) -> str:
    return export_ops_evidence.bound_text(value)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


if __name__ == "__main__":
    sys.exit(main())
