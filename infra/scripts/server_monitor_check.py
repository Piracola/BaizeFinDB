"""Compact monitoring summary for a running BaizeFinDB server.

This script is intentionally a thin read-only wrapper around
server_runtime_check.py. It does not collect endpoints itself; it builds a compact
status payload that cron/systemd or a later alert sender can consume.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import server_alert_payload  # noqa: E402
import server_runtime_check  # noqa: E402

DEFAULT_TOP_FAILURES = 5
DEFAULT_TOP_WARNINGS = 10
READ_ONLY_BOUNDARY = (
    "read-only monitor summary; delegates to server_runtime_check.py and must not "
    "trigger provider collection, radar scans, Telegram pushes, model calls, "
    "reports, backups, cleanup, database writes, or trading actions"
)


def build_monitor_summary(
    runtime_report: dict[str, Any],
    *,
    top_failures: int = DEFAULT_TOP_FAILURES,
    top_warnings: int = DEFAULT_TOP_WARNINGS,
) -> dict[str, Any]:
    failures = _list_of_dicts(runtime_report.get("failures"))
    warnings = _list_of_dicts(runtime_report.get("warnings"))
    if failures:
        status = "blocked"
    elif warnings:
        status = "warning"
    else:
        status = "ok"

    runtime_status = str(runtime_report.get("status") or "unknown")
    strict_warning_failure = (
        status == "warning"
        and runtime_status == "fail"
        and bool(runtime_report.get("fail_on_warning"))
    )

    return {
        "report_type": "server_monitor_summary",
        "generated_at": _now_iso(),
        "status": status,
        "runtime_status": runtime_status,
        "strict_warning_failure": strict_warning_failure,
        "base_url": runtime_report.get("base_url"),
        "sample_count": _as_int(runtime_report.get("sample_count")),
        "started_at": runtime_report.get("started_at"),
        "finished_at": runtime_report.get("finished_at"),
        "summary": {
            "failure_count": len(failures),
            "warning_count": len(warnings),
            "readiness_status_counts": _dict_or_empty(
                runtime_report.get("readiness_status_counts")
            ),
            "alert_counts": _dict_or_empty(runtime_report.get("alert_counts")),
            "latest_server": _dict_or_none(runtime_report.get("latest_server")),
            "latest_trend": _dict_or_none(runtime_report.get("latest_trend")),
        },
        "top_failures": failures[: max(top_failures, 0)],
        "top_warnings": warnings[: max(top_warnings, 0)],
        "boundary": READ_ONLY_BOUNDARY,
    }


def exit_code_for_monitor_report(
    report: dict[str, Any],
    *,
    fail_on_warning: bool,
) -> int:
    if report.get("status") == "blocked":
        return 1
    if report.get("status") == "warning" and fail_on_warning:
        return 1
    return 0


def write_json_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Write a compact monitoring summary for a running BaizeFinDB API.",
    )
    parser.add_argument(
        "--base-url",
        default=server_runtime_check.DEFAULT_BASE_URL,
        help=f"API base URL, default: {server_runtime_check.DEFAULT_BASE_URL}",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=1,
        help="Number of runtime samples to collect, default: 1.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=0.0,
        help="Delay between samples, default: 0 seconds.",
    )
    parser.add_argument(
        "--lookback-hours",
        type=int,
        default=server_runtime_check.DEFAULT_LOOKBACK_HOURS,
        help=(
            "Lookback window for OPS endpoints in hours, default: "
            f"{server_runtime_check.DEFAULT_LOOKBACK_HOURS}."
        ),
    )
    parser.add_argument(
        "--history-limit",
        type=int,
        default=20,
        help="OPS history event limit, default: 20.",
    )
    parser.add_argument(
        "--include-ops-trends",
        action="store_true",
        help="Also read the read-only /ops/trends endpoint through runtime check.",
    )
    parser.add_argument(
        "--trend-bucket-count",
        type=int,
        default=server_runtime_check.DEFAULT_TREND_BUCKET_COUNT,
        help=(
            f"OPS trend bucket count, 1-{server_runtime_check.MAX_TREND_BUCKET_COUNT}, "
            f"default: {server_runtime_check.DEFAULT_TREND_BUCKET_COUNT}."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=5,
        help="HTTP timeout per request in seconds, default: 5.",
    )
    parser.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Return a failing exit code when the compact summary status is warning.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        help="Optional path to write the compact monitor JSON summary.",
    )
    parser.add_argument(
        "--runtime-json-output",
        type=Path,
        help="Optional path to write the full underlying runtime check JSON report.",
    )
    parser.add_argument(
        "--alert-json-output",
        type=Path,
        help="Optional path to write a no-send alert payload from the monitor summary.",
    )
    parser.add_argument(
        "--alert-max-items",
        type=int,
        default=server_alert_payload.DEFAULT_MAX_ITEMS,
        help=(
            "Maximum alert payload items to include, "
            f"0-{server_alert_payload.MAX_ITEMS}, "
            f"default: {server_alert_payload.DEFAULT_MAX_ITEMS}."
        ),
    )
    parser.add_argument(
        "--suppress-warning-alert-notify",
        action="store_true",
        help="When writing alert payloads, set should_notify=false for warning status.",
    )
    parser.add_argument(
        "--include-ok-alert",
        action="store_true",
        help="When writing alert payloads, set should_notify=true for ok status.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    validation_error = _validate_args(args)
    if validation_error:
        print(f"[FAIL] {validation_error}")
        return 2

    runtime_report = server_runtime_check.run_runtime_check(
        base_url=args.base_url,
        samples=args.samples,
        interval_seconds=max(args.interval_seconds, 0),
        lookback_hours=args.lookback_hours,
        history_limit=args.history_limit,
        include_ops_trends=args.include_ops_trends,
        trend_bucket_count=args.trend_bucket_count,
        timeout=args.timeout,
        fail_on_warning=args.fail_on_warning,
    )
    monitor_report = build_monitor_summary(runtime_report)

    if args.runtime_json_output:
        write_json_report(args.runtime_json_output, runtime_report)
    if args.json_output:
        write_json_report(args.json_output, monitor_report)
    if args.alert_json_output:
        alert_error = write_alert_payload(args, monitor_report)
        if alert_error:
            print(f"[FAIL] {alert_error}")
            return 2

    print(_format_summary(monitor_report, args.json_output))
    return exit_code_for_monitor_report(
        monitor_report,
        fail_on_warning=args.fail_on_warning,
    )


def _validate_args(args: argparse.Namespace) -> str:
    if args.samples < 1 or args.samples > 20:
        return "--samples must be between 1 and 20"
    if args.lookback_hours < 1:
        return "--lookback-hours must be >= 1"
    if args.history_limit < 1:
        return "--history-limit must be >= 1"
    if (
        args.trend_bucket_count < 1
        or args.trend_bucket_count > server_runtime_check.MAX_TREND_BUCKET_COUNT
    ):
        return (
            "--trend-bucket-count must be between 1 and "
            f"{server_runtime_check.MAX_TREND_BUCKET_COUNT}"
        )
    if args.timeout < 1:
        return "--timeout must be >= 1"
    if args.alert_max_items < 0 or args.alert_max_items > server_alert_payload.MAX_ITEMS:
        return f"--alert-max-items must be between 0 and {server_alert_payload.MAX_ITEMS}"
    return ""


def write_alert_payload(
    args: argparse.Namespace,
    monitor_report: dict[str, Any],
) -> str:
    try:
        alert_payload = server_alert_payload.build_alert_payload(
            monitor_report,
            source_path=args.json_output,
            max_items=args.alert_max_items,
            suppress_warning_notify=args.suppress_warning_alert_notify,
            include_ok=args.include_ok_alert,
        )
        server_alert_payload.write_json_report(args.alert_json_output, alert_payload)
    except (OSError, server_alert_payload.AlertPayloadInputError) as exc:
        return f"could not write alert payload: {exc}"
    return ""


def _format_summary(report: dict[str, Any], output_path: Path | None) -> str:
    status = str(report["status"])
    label = "OK" if status == "ok" else "WARN" if status == "warning" else "FAIL"
    summary = report["summary"]
    lines = [
        f"[{label}] BaizeFinDB server monitor summary",
        f"status={status} runtime_status={report['runtime_status']}",
        f"base_url={report['base_url']} samples={report['sample_count']}",
        (
            "failures="
            f"{summary['failure_count']} warnings={summary['warning_count']} "
            f"readiness={summary['readiness_status_counts']} "
            f"alerts={summary['alert_counts']}"
        ),
    ]
    latest_server = summary.get("latest_server")
    if latest_server:
        lines.append(f"server={latest_server}")
    latest_trend = summary.get("latest_trend")
    if latest_trend:
        lines.append(f"trend={latest_trend}")
    if output_path:
        lines.append(f"json_output={output_path}")
    for failure in report["top_failures"]:
        lines.append(
            "[FAIL] "
            f"endpoint={failure.get('endpoint')} "
            f"path={failure.get('path')} "
            f"detail={failure.get('error')}"
        )
    for warning in report["top_warnings"]:
        lines.append(f"[WARN] {warning}")
    return "\n".join(lines)


def _list_of_dicts(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _dict_or_empty(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _dict_or_none(value: object) -> dict[str, Any] | None:
    return dict(value) if isinstance(value, dict) else None


def _as_int(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


if __name__ == "__main__":
    sys.exit(main())
