"""Read-only first-use smoke check for the BaizeFinDB Windows client."""

from __future__ import annotations

import argparse
import importlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from clients.windows import client_api

JsonObject = dict[str, Any]

MAX_TEXT_LENGTH = 500
MAX_LIST_ITEMS = 10
MAX_DICT_ITEMS = 30
MAX_DEPTH = 4
MAX_READINESS_DIAGNOSTICS = 5
DEFAULT_OPS_READINESS_LOOKBACK_HOURS = 24
MIN_OPS_READINESS_LOOKBACK_HOURS = 1
MAX_OPS_READINESS_LOOKBACK_HOURS = 168
REDACTED = "<redacted>"
SENSITIVE_TEXT_PATTERNS = (
    re.compile(r"(?i)(bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)\b(token|secret|password|authorization|credential|api[_-]?key|user[_-]?key)=([^&\s,;]+)"),
    re.compile(r"(?i)\b(source[_-]?url|url|domain|host|webhook)=([^&\s,;]+)"),
    re.compile(r"https?://[^\s,;]+"),
)
SKIPPED_USER_SCOPED_ENDPOINTS = (
    "/portfolio/holdings",
    "/portfolio/watchlist",
    "/reports",
    "/reports/periodic",
)


@dataclass
class CheckItem:
    name: str
    status: str
    message: str
    payload: Any | None = None


@dataclass
class SmokeReport:
    status: str = "ok"
    server_url: str = ""
    user_key: str = REDACTED
    checks: list[CheckItem] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_ok(self, name: str, message: str, payload: Any | None = None) -> None:
        self.checks.append(CheckItem(name=name, status="ok", message=message, payload=payload))

    def add_warning(self, name: str, message: str, payload: Any | None = None) -> None:
        if self.status == "ok":
            self.status = "warning"
        self.warnings.append(f"{name}: {message}")
        self.checks.append(CheckItem(name=name, status="warning", message=message, payload=payload))

    def add_blocker(self, name: str, message: str, payload: Any | None = None) -> None:
        self.status = "blocked"
        self.blockers.append(f"{name}: {message}")
        self.checks.append(CheckItem(name=name, status="blocked", message=message, payload=payload))

    def exit_code(self, *, fail_on_warning: bool = False) -> int:
        if self.blockers:
            return 1
        if fail_on_warning and self.warnings:
            return 1
        return 0


def run_smoke_check(
    *,
    server_url: str | None,
    user_key: str | None,
    ops_readiness_lookback_hours: int = DEFAULT_OPS_READINESS_LOOKBACK_HOURS,
    importer: Callable[[str], Any] = importlib.import_module,
    opener: client_api.UrlOpener | None = None,
) -> SmokeReport:
    report = SmokeReport(user_key=REDACTED)
    normalized_user_key = _normalize_user_key(user_key)
    try:
        normalized_lookback_hours = _validate_ops_readiness_lookback_hours(
            ops_readiness_lookback_hours,
        )
    except ValueError as exc:
        report.add_blocker("ops_readiness_lookback_hours", str(exc))
        return report

    try:
        normalized_server_url = client_api.normalize_base_url(server_url)
    except ValueError as exc:
        report.add_blocker("server_url", str(exc))
        return report

    report.server_url = normalized_server_url
    _check_tkinter(report, importer)
    if report.blockers:
        return report

    _check_core_endpoints(report, normalized_server_url, normalized_lookback_hours, opener)
    if report.blockers:
        return report

    _check_optional_endpoints(report, normalized_server_url, opener)
    _record_user_scoped_skips(report, normalized_user_key)
    return report


def write_json_report(report: SmokeReport, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report_to_json(report), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def write_compact_json_report(report: SmokeReport, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            report_to_compact_json(report),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def report_to_json(report: SmokeReport) -> JsonObject:
    return {
        "status": report.status,
        "server_url": report.server_url,
        "user_key": REDACTED,
        "blockers": [_sanitize_message(item) for item in report.blockers],
        "warnings": [_sanitize_message(item) for item in report.warnings],
        "checks": [
            {
                "name": check.name,
                "status": check.status,
                "message": _sanitize_message(check.message),
                "payload": _sanitize(check.payload),
            }
            for check in report.checks
        ],
    }


def report_to_compact_json(report: SmokeReport) -> JsonObject:
    return {
        "status": report.status,
        "server": _server_url_metadata(report.server_url),
        "user_key": REDACTED,
        "check_count": len(report.checks),
        "checks": [
            {
                "name": check.name,
                "status": check.status,
                "message": _sanitize_compact_message(check.message),
            }
            for check in report.checks
        ],
        "warnings": [_sanitize_compact_message(item) for item in report.warnings],
        "blockers": [_sanitize_compact_message(item) for item in report.blockers],
        "ops_readiness_non_ok_checks": _compact_ops_readiness_non_ok_checks(report),
    }


def format_summary(report: SmokeReport) -> str:
    lines = [
        "BaizeFinDB Windows client first-use smoke check",
        f"Server: {report.server_url or '-'}",
        f"Status: {report.status}",
        (
            f"Checks: {len(report.checks)} | Blockers: {len(report.blockers)} | "
            f"Warnings: {len(report.warnings)}"
        ),
    ]

    if report.blockers:
        lines.append("")
        lines.append("Blockers:")
        lines.extend(f"- {_sanitize_message(item)}" for item in report.blockers)

    if report.warnings:
        lines.append("")
        lines.append("Warnings:")
        lines.extend(f"- {_sanitize_message(item)}" for item in report.warnings)

    if not report.blockers:
        lines.append("")
        lines.append("Next: launch clients/windows/run-client.ps1 after reviewing warnings.")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a read-only first-use smoke check for the Windows client.",
    )
    parser.add_argument(
        "--server-url",
        default=client_api.DEFAULT_SERVER_URL,
        help=f"BaizeFinDB API base URL. Defaults to {client_api.DEFAULT_SERVER_URL}.",
    )
    parser.add_argument(
        "--user-key",
        default=client_api.DEFAULT_USER_KEY,
        help="User data isolation key. The JSON report redacts this value.",
    )
    parser.add_argument(
        "--json-output",
        help="Optional path for a bounded sanitized JSON report.",
    )
    parser.add_argument(
        "--compact-json-output",
        help=(
            "Optional path for compact evidence with status, check summaries, "
            "warnings, blockers, and redacted metadata only."
        ),
    )
    parser.add_argument(
        "--ops-readiness-lookback-hours",
        type=int,
        default=DEFAULT_OPS_READINESS_LOOKBACK_HOURS,
        help=(
            "Lookback window for /ops/readiness in hours. "
            f"Range {MIN_OPS_READINESS_LOOKBACK_HOURS} to "
            f"{MAX_OPS_READINESS_LOOKBACK_HOURS}; defaults to "
            f"{DEFAULT_OPS_READINESS_LOOKBACK_HOURS}."
        ),
    )
    parser.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Return a nonzero exit code when the smoke check reports warnings.",
    )
    args = parser.parse_args(argv)

    report = run_smoke_check(
        server_url=args.server_url,
        user_key=args.user_key,
        ops_readiness_lookback_hours=args.ops_readiness_lookback_hours,
    )
    if args.json_output:
        write_json_report(report, args.json_output)
    if args.compact_json_output:
        write_compact_json_report(report, args.compact_json_output)

    print(format_summary(report))
    return report.exit_code(fail_on_warning=args.fail_on_warning)


def _check_tkinter(report: SmokeReport, importer: Callable[[str], Any]) -> None:
    try:
        importer("tkinter")
    except Exception as exc:  # noqa: BLE001 - import failure details are diagnostic here.
        report.add_blocker("tkinter", f"Tkinter is not importable: {exc}")
        return

    report.add_ok("tkinter", "Tkinter imports without opening a GUI window.")


def _check_core_endpoints(
    report: SmokeReport,
    server_url: str,
    ops_readiness_lookback_hours: int,
    opener: client_api.UrlOpener | None,
) -> None:
    health = _call_endpoint(
        report,
        "health",
        lambda: client_api.get_json(server_url, "/health", opener=opener),
        required=True,
    )
    if isinstance(health, Mapping):
        status = str(health.get("status", ""))
        if not status:
            report.add_blocker("health", "/health returned a malformed payload", health)
        elif status not in {"ok", "ready"}:
            report.add_blocker("health", f"/health returned status {status}", health)
    else:
        report.add_blocker("health", "/health returned a malformed payload", health)

    ready = _call_endpoint(
        report,
        "health_ready",
        lambda: client_api.fetch_health(server_url, opener=opener),
        required=True,
    )
    if isinstance(ready, Mapping):
        status = str(ready.get("status", ""))
        if status != "ready":
            report.add_blocker(
                "health_ready",
                f"/health/ready returned status {status or '-'}",
                ready,
            )
    else:
        report.add_blocker("health_ready", "/health/ready returned a malformed payload", ready)

    ops_readiness = _call_endpoint(
        report,
        "ops_readiness",
        lambda: client_api.fetch_ops_readiness(
            server_url,
            lookback_hours=ops_readiness_lookback_hours,
            opener=opener,
        ),
        required=True,
    )
    if isinstance(ops_readiness, Mapping):
        status = str(ops_readiness.get("status", ""))
        if status == "blocked":
            report.add_blocker(
                "ops_readiness",
                _ops_readiness_status_message(
                    "/ops/readiness is blocked",
                    ops_readiness,
                ),
                ops_readiness,
            )
        elif status == "warning":
            report.add_warning(
                "ops_readiness",
                _ops_readiness_status_message(
                    "/ops/readiness returned warning",
                    ops_readiness,
                ),
                ops_readiness,
            )
        elif status != "ready":
            report.add_blocker(
                "ops_readiness",
                f"/ops/readiness returned malformed status {status or '-'}",
                ops_readiness,
            )
    else:
        report.add_blocker(
            "ops_readiness",
            "/ops/readiness returned a malformed payload",
            ops_readiness,
        )


def _check_optional_endpoints(
    report: SmokeReport,
    server_url: str,
    opener: client_api.UrlOpener | None,
) -> None:
    _call_endpoint(
        report,
        "ops_overview",
        lambda: client_api.fetch_ops_overview(server_url, opener=opener),
        required=False,
    )
    _call_endpoint(
        report,
        "ops_history",
        lambda: client_api.fetch_ops_history(server_url, limit=10, opener=opener),
        required=False,
    )
    _call_endpoint(
        report,
        "tushare_status",
        lambda: client_api.fetch_tushare_status(server_url, opener=opener),
        required=False,
    )
    _call_endpoint(
        report,
        "tushare_readiness",
        lambda: client_api.fetch_tushare_readiness(server_url, opener=opener),
        required=False,
    )

    radar = _call_endpoint(
        report,
        "radar_overview",
        lambda: client_api.fetch_radar_overview(server_url, opener=opener),
        required=False,
    )
    if isinstance(radar, Mapping) and not _has_radar_data(radar):
        report.add_warning(
            "radar_overview",
            "Radar overview is reachable but has no first-use data.",
            radar,
        )

    signals = _call_endpoint(
        report,
        "signals",
        lambda: client_api.fetch_signals(server_url, limit=10, opener=opener),
        required=False,
    )
    if isinstance(signals, list) and not signals:
        report.add_warning("signals", "Signal list is reachable but empty.", signals)

    bindings = _call_endpoint(
        report,
        "telegram_bindings",
        lambda: client_api.fetch_telegram_bindings(server_url, limit=10, opener=opener),
        required=False,
    )
    if isinstance(bindings, list) and not bindings:
        report.add_warning(
            "telegram_bindings",
            "Telegram binding list is reachable but empty.",
            bindings,
        )


def _call_endpoint(
    report: SmokeReport,
    name: str,
    call: Callable[[], Any],
    *,
    required: bool,
) -> Any | None:
    try:
        payload = call()
    except (client_api.BaizeApiError, ValueError) as exc:
        if required:
            report.add_blocker(name, str(exc), getattr(exc, "payload", None))
        else:
            report.add_warning(name, str(exc), getattr(exc, "payload", None))
        return None

    report.add_ok(name, "Endpoint returned a valid JSON payload.", payload)
    return payload


def _record_user_scoped_skips(report: SmokeReport, user_key: str) -> None:
    report.add_warning(
        "user_scoped_reads",
        (
            "Skipped portfolio/watchlist/report/periodic endpoints for user_key "
            f"{_redacted_user_key(user_key)} because current GET handlers can create user rows."
        ),
        {"skipped_endpoints": list(SKIPPED_USER_SCOPED_ENDPOINTS), "user_key": REDACTED},
    )


def _has_radar_data(payload: Mapping[str, Any]) -> bool:
    counts = payload.get("priority_counts")
    if isinstance(counts, Mapping) and any(_positive_number(value) for value in counts.values()):
        return True

    for key in ("current_subjects", "active_signals", "stock_backtrace_evidences"):
        value = payload.get(key)
        if isinstance(value, list) and value:
            return True

    latest_scan = payload.get("latest_scan")
    return isinstance(latest_scan, Mapping) and latest_scan.get("id") is not None


def _positive_number(value: Any) -> bool:
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def _ops_readiness_status_message(prefix: str, payload: Mapping[str, Any]) -> str:
    diagnostics = _ops_readiness_diagnostics(payload)
    if not diagnostics:
        return prefix
    return f"{prefix}: {'; '.join(diagnostics)}"


def _ops_readiness_diagnostics(payload: Mapping[str, Any]) -> list[str]:
    checks = payload.get("checks")
    if not isinstance(checks, list):
        return []

    diagnostics: list[str] = []
    non_ok_checks = []
    for check in checks:
        if not isinstance(check, Mapping):
            continue
        status = str(check.get("status", "")).lower()
        if status in {"", "ok", "ready"}:
            continue
        non_ok_checks.append(check)

    for check in non_ok_checks[:MAX_READINESS_DIAGNOSTICS]:
        name = _sanitize_message(_bounded_text(str(check.get("name") or "unnamed_check")))
        message = _sanitize_message(
            _bounded_text(str(check.get("message") or "No message returned.")),
        )
        diagnostics.append(f"{name}: {message}")
    if len(non_ok_checks) > MAX_READINESS_DIAGNOSTICS:
        diagnostics.append(f"+{len(non_ok_checks) - MAX_READINESS_DIAGNOSTICS} more")
    return diagnostics


def _sanitize_compact_message(message: str) -> str:
    sanitized = _sanitize_message(message)
    sanitized = re.sub(r"(?i)\bJSON payloads?\b", "JSON response", sanitized)
    sanitized = re.sub(r"(?i)\bendpoint payloads?\b", "endpoint responses", sanitized)
    return re.sub(r"(?i)\bpayloads?\b", "response data", sanitized)


def _compact_ops_readiness_non_ok_checks(report: SmokeReport) -> list[JsonObject]:
    for check in report.checks:
        if check.name != "ops_readiness" or not isinstance(check.payload, Mapping):
            continue
        checks = check.payload.get("checks")
        if not isinstance(checks, list):
            return []

        summaries: list[JsonObject] = []
        for readiness_check in checks:
            if not isinstance(readiness_check, Mapping):
                continue
            status = str(readiness_check.get("status", "")).lower()
            if status in {"", "ok", "ready"}:
                continue
            summaries.append(
                {
                    "name": _sanitize_message(
                        _bounded_text(str(readiness_check.get("name") or "unnamed_check")),
                    ),
                    "status": _sanitize_message(_bounded_text(status)),
                    "message": _sanitize_compact_message(
                        _bounded_text(
                            str(readiness_check.get("message") or "No message returned."),
                        ),
                    ),
                },
            )
            if len(summaries) >= MAX_READINESS_DIAGNOSTICS:
                break
        return summaries
    return []


def _server_url_metadata(server_url: str) -> JsonObject:
    if not server_url:
        return {
            "scheme": "",
            "host": "",
            "port": None,
            "path": "",
            "has_path": False,
        }

    parts = urlsplit(server_url)
    path = parts.path.rstrip("/")
    return {
        "scheme": parts.scheme.lower(),
        "host": _sanitize_message(parts.hostname or ""),
        "port": parts.port,
        "path": _sanitize_message(path),
        "has_path": bool(path),
    }


def _sanitize(value: Any, *, depth: int = 0) -> Any:
    if depth > MAX_DEPTH:
        return "<truncated>"

    if isinstance(value, Mapping):
        output: JsonObject = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= MAX_DICT_ITEMS:
                output["<truncated>"] = True
                break
            text_key = str(key)
            if _is_sensitive_key(text_key):
                output[text_key] = REDACTED
            else:
                output[text_key] = _sanitize(item, depth=depth + 1)
        return output

    if isinstance(value, list):
        output = [_sanitize(item, depth=depth + 1) for item in value[:MAX_LIST_ITEMS]]
        if len(value) > MAX_LIST_ITEMS:
            output.append({"<truncated>": len(value) - MAX_LIST_ITEMS})
        return output

    if isinstance(value, str):
        if _looks_sensitive_text(value):
            return REDACTED
        return _bounded_text(value)

    if isinstance(value, int | float | bool) or value is None:
        return value

    return _bounded_text(str(value))


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower()
    return any(
        marker in normalized
        for marker in (
            "token",
            "secret",
            "password",
            "authorization",
            "credential",
            "api_key",
            "apikey",
            "user_key",
        )
    )


def _looks_sensitive_text(value: str) -> bool:
    lowered = value.lower()
    return "bearer " in lowered or "token=" in lowered or "secret=" in lowered


def _bounded_text(value: str) -> str:
    return value if len(value) <= MAX_TEXT_LENGTH else f"{value[:MAX_TEXT_LENGTH]}...<truncated>"


def _sanitize_message(value: str) -> str:
    sanitized = value
    for pattern in SENSITIVE_TEXT_PATTERNS:
        if pattern.pattern.startswith("(?i)(bearer"):
            sanitized = pattern.sub(r"\1" + REDACTED, sanitized)
        elif pattern.pattern.startswith("(?i)\\b"):
            sanitized = pattern.sub(lambda match: f"{match.group(1)}={REDACTED}", sanitized)
        else:
            sanitized = pattern.sub(REDACTED, sanitized)
    return _bounded_text(sanitized)


def _normalize_user_key(value: str | None) -> str:
    normalized = (value or client_api.DEFAULT_USER_KEY).strip()
    return normalized or client_api.DEFAULT_USER_KEY


def _validate_ops_readiness_lookback_hours(value: int) -> int:
    if MIN_OPS_READINESS_LOOKBACK_HOURS <= value <= MAX_OPS_READINESS_LOOKBACK_HOURS:
        return value
    raise ValueError(
        "OPS readiness lookback must be between "
        f"{MIN_OPS_READINESS_LOOKBACK_HOURS} and {MAX_OPS_READINESS_LOOKBACK_HOURS} hours.",
    )


def _redacted_user_key(value: str) -> str:
    if not value:
        return REDACTED
    return f"{value[:1]}***"


if __name__ == "__main__":
    raise SystemExit(main())
