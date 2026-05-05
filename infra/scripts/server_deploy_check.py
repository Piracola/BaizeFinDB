"""Deployment preflight checks for the BaizeFinDB Linux server setup."""

from __future__ import annotations

import argparse
import configparser
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
SERVER_COMPOSE_FILES = ("docker-compose.yml", "docker-compose.server.yml")
DEFAULT_POSTGRES_SERVICE = "postgres"
LINUX_SYSTEMD_UNIT_FILES = (
    "baizefindb-compose.service",
    "baizefindb-monitor.service",
    "baizefindb-monitor.timer",
    "baizefindb-alert-telegram.service",
    "baizefindb-alert-telegram.timer",
    "baizefindb-postgres-backup.service",
    "baizefindb-postgres-backup.timer",
)
SYSTEMD_FORBIDDEN_MARKERS = (
    "telegram_bot_token",
    "telegram_webhook_secret",
    "webhook_url",
    "password=",
    "secret=",
    "token=",
    "curl ",
    "sendmail",
    "smtp",
)
RADAR_SIGNAL_LIST_SMOKE_PATH = "/radar/signals?limit=1"
RADAR_SIGNAL_ANALYSIS_REQUIRED_FIELDS = (
    "signal_id",
    "subject_type",
    "subject_name",
    "priority",
    "lifecycle_stage",
    "review_status",
    "analysis_title",
    "key_points",
    "metric_highlights",
    "risk_flags",
    "evidence_summary",
    "review_summary",
    "agent_inputs",
    "next_actions",
)
M5_SMOKE_ENDPOINTS = (
    ("/health", ("status", "service")),
    ("/health/ready", ("status", "checks")),
    (
        "/ops/overview",
        (
            "generated_at",
            "server",
            "radar",
            "provider_fetch",
            "data_quality",
            "telegram_push",
            "model_calls",
            "alerts",
        ),
    ),
    (
        "/ops/history",
        (
            "generated_at",
            "lookback_hours",
            "limit",
            "recent_events",
            "failure_summary",
        ),
    ),
    (
        "/ops/trends",
        (
            "generated_at",
            "lookback_hours",
            "bucket_count",
            "bucket_seconds",
            "server",
            "buckets",
        ),
    ),
    (
        "/ops/readiness",
        (
            "generated_at",
            "lookback_hours",
            "status",
            "checks",
        ),
    ),
    ("/providers/akshare/status", ("provider_name", "endpoints")),
    (
        "/providers/tushare/status",
        (
            "provider_name",
            "token_configured",
            "fetch_enabled",
            "endpoint_count",
            "implemented_endpoint_count",
        ),
    ),
    (
        "/providers/tushare/readiness",
        (
            "provider_name",
            "generated_at",
            "status",
            "scheduler_policy",
            "endpoints",
        ),
    ),
    ("/radar/overview", ("priority_counts", "lifecycle_counts", "subject_count")),
    (
        "/telegram/status",
        ("bot_token_configured", "push_enabled", "binding_count"),
    ),
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status != "fail"


def find_repo_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").exists() and (
            candidate / "docker-compose.yml"
        ).exists():
            return candidate

    msg = "could not find repository root with pyproject.toml and docker-compose.yml"
    raise RuntimeError(msg)


def server_compose_command(*args: str) -> list[str]:
    command = ["docker", "compose"]
    for compose_file in SERVER_COMPOSE_FILES:
        command.extend(["-f", compose_file])
    command.extend(args)
    return command


def pg_dump_version_command(service: str = DEFAULT_POSTGRES_SERVICE) -> list[str]:
    return server_compose_command("exec", "-T", service, "pg_dump", "--version")


def check_backup_evidence(
    root: Path,
    *,
    service: str,
    check_json_output: str,
) -> CheckResult:
    try:
        exit_code = _run_postgres_backup_check_only(
            root,
            service=service,
            check_json_output=check_json_output,
        )
    except Exception as exc:
        detail = _truncate(str(exc), limit=250)
        return CheckResult(
            "postgres backup check evidence",
            "fail",
            f"backup check evidence failed: {exc.__class__.__name__}: {detail}",
        )

    if exit_code == 0:
        return CheckResult(
            "postgres backup check evidence",
            "ok",
            f"evidence written: {check_json_output}",
        )

    return CheckResult(
        "postgres backup check evidence",
        "fail",
        f"backup check-only returned exit code {exit_code}",
    )


def check_env(root: Path, *, strict: bool) -> CheckResult:
    env_path = root / ".env"
    if env_path.exists():
        return CheckResult(".env", "ok", ".env exists")

    detail = ".env is missing; create it from .env.example before server start"
    return CheckResult(".env", "fail" if strict else "warn", detail)


def run_command(name: str, command: list[str], root: Path) -> CheckResult:
    try:
        completed = subprocess.run(  # noqa: S603
            command,
            cwd=root,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        return CheckResult(name, "fail", f"command not found: {exc.filename}")

    if completed.returncode == 0:
        output = (completed.stdout or "").strip() or (completed.stderr or "").strip()
        return CheckResult(name, "ok", _truncate(output))

    detail = "\n".join(
        part
        for part in (
            (completed.stdout or "").strip(),
            (completed.stderr or "").strip(),
        )
        if part
    )
    return CheckResult(name, "fail", _truncate(detail))


def check_http(base_url: str, path: str, *, timeout: int) -> CheckResult:
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    request = Request(url, headers={"Accept": "application/json"}, method="GET")
    name = f"HTTP {path}"
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310
            body = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return CheckResult(name, "fail", f"HTTP {exc.code}: {_truncate(body)}")
    except (TimeoutError, URLError, OSError) as exc:
        return CheckResult(name, "fail", str(exc))

    return CheckResult(name, "ok", _truncate(body))


def check_http_json_fields(
    base_url: str,
    path: str,
    required_fields: tuple[str, ...],
    *,
    timeout: int,
) -> CheckResult:
    name = f"HTTP JSON {path}"
    payload, error = _read_http_json(
        base_url,
        path,
        timeout=timeout,
        result_name=name,
    )
    if error is not None:
        return error

    if not isinstance(payload, dict):
        return CheckResult(name, "fail", "JSON response is not an object")

    missing_fields = [field for field in required_fields if field not in payload]
    if missing_fields:
        return CheckResult(
            name,
            "fail",
            f"missing required fields: {', '.join(missing_fields)}",
        )

    return CheckResult(name, "ok", f"fields present: {', '.join(required_fields)}")


def check_m5_smoke(base_url: str, *, timeout: int) -> list[CheckResult]:
    results = [
        check_http_json_fields(
            base_url,
            path,
            required_fields,
            timeout=timeout,
        )
        for path, required_fields in M5_SMOKE_ENDPOINTS
    ]
    results.extend(check_radar_signal_analysis_smoke(base_url, timeout=timeout))
    return results


def check_radar_signal_analysis_smoke(base_url: str, *, timeout: int) -> list[CheckResult]:
    name = f"HTTP JSON {RADAR_SIGNAL_LIST_SMOKE_PATH}"
    payload, error = _read_http_json(
        base_url,
        RADAR_SIGNAL_LIST_SMOKE_PATH,
        timeout=timeout,
        result_name=name,
    )
    if error is not None:
        return [error]

    if not isinstance(payload, list):
        return [CheckResult(name, "fail", "JSON response is not an array")]

    if not payload:
        return [
            CheckResult(
                name,
                "warn",
                "no radar signals available; skipped signal analysis contract sample",
            ),
        ]

    signal_id = _first_signal_id(payload)
    if signal_id is None:
        return [
            CheckResult(
                name,
                "fail",
                "no signal object with integer id found in response",
            ),
        ]

    return [
        CheckResult(name, "ok", f"sampled signal id: {signal_id}"),
        check_http_json_fields(
            base_url,
            f"/radar/signals/{signal_id}/analysis",
            RADAR_SIGNAL_ANALYSIS_REQUIRED_FIELDS,
            timeout=timeout,
        ),
    ]


def check_tushare_anns_d_beat_enablement() -> CheckResult:
    try:
        report = _build_tushare_anns_d_beat_enablement_report()
    except Exception as exc:
        return CheckResult(
            "Tushare anns_d Beat enablement checklist",
            "fail",
            f"checklist could not run: {exc.__class__.__name__}: {_truncate(str(exc), limit=250)}",
        )

    status = str(report.get("status", "fail"))
    if status == "fail":
        result_status = "fail"
    elif status == "warn":
        result_status = "warn"
    elif status in {"ok", "pass"}:
        result_status = "ok"
    else:
        return CheckResult(
            "Tushare anns_d Beat enablement checklist",
            "fail",
            f"unexpected checklist status: {_truncate(status, limit=120)}",
        )

    return CheckResult(
        "Tushare anns_d Beat enablement checklist",
        result_status,
        _format_tushare_anns_d_beat_enablement_summary(report),
    )


def check_systemd_units(root: Path) -> list[CheckResult]:
    linux_dir = root / "infra" / "linux"
    texts: dict[str, str] = {}
    parsers: dict[str, configparser.ConfigParser] = {}
    missing: list[str] = []
    invalid: list[str] = []

    for name in LINUX_SYSTEMD_UNIT_FILES:
        path = linux_dir / name
        if not path.exists():
            missing.append(name)
            continue
        try:
            text = path.read_text(encoding="utf-8")
            parser = _parse_systemd_unit(text)
        except (OSError, configparser.Error) as exc:
            invalid.append(f"{name}: {exc.__class__.__name__}")
            continue
        texts[name] = text
        parsers[name] = parser

    results = [
        CheckResult(
            "systemd unit files present",
            "fail" if missing else "ok",
            (
                f"missing unit file(s): {', '.join(missing)}"
                if missing
                else f"unit files present: {len(LINUX_SYSTEMD_UNIT_FILES)}"
            ),
        ),
        CheckResult(
            "systemd unit files parse",
            "fail" if invalid else "ok",
            (
                f"invalid unit file(s): {', '.join(invalid)}"
                if invalid
                else "all available unit files parsed"
            ),
        ),
    ]

    if texts:
        results.append(_check_systemd_forbidden_markers(texts))

    if "baizefindb-compose.service" in parsers:
        results.append(
            _check_required_markers(
                "systemd compose service",
                texts["baizefindb-compose.service"],
                (
                    "docker compose -f docker-compose.yml -f docker-compose.server.yml up -d",
                    "docker compose -f docker-compose.yml -f docker-compose.server.yml down",
                    "RemainAfterExit=yes",
                    "WantedBy=multi-user.target",
                ),
            )
        )
    if "baizefindb-monitor.service" in parsers:
        results.append(_check_monitor_service(texts["baizefindb-monitor.service"]))
    if "baizefindb-monitor.timer" in parsers:
        results.append(_check_monitor_timer(parsers["baizefindb-monitor.timer"]))
    if "baizefindb-alert-telegram.service" in parsers:
        results.append(
            _check_alert_telegram_service(texts["baizefindb-alert-telegram.service"])
        )
    if "baizefindb-alert-telegram.timer" in parsers:
        results.append(
            _check_alert_telegram_timer(
                parsers["baizefindb-alert-telegram.timer"],
                texts["baizefindb-alert-telegram.timer"],
            )
        )
    if "baizefindb-postgres-backup.service" in parsers:
        results.append(
            _check_postgres_backup_service(texts["baizefindb-postgres-backup.service"])
        )
    if "baizefindb-postgres-backup.timer" in parsers:
        results.append(_check_postgres_backup_timer(parsers["baizefindb-postgres-backup.timer"]))

    return results


def build_report(checks: list[CheckResult]) -> dict[str, object]:
    counts = {
        "ok": sum(1 for check in checks if check.status == "ok"),
        "warn": sum(1 for check in checks if check.status == "warn"),
        "fail": sum(1 for check in checks if check.status == "fail"),
    }
    if counts["fail"]:
        status = "fail"
    elif counts["warn"]:
        status = "warn"
    else:
        status = "ok"

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "status": status,
        "summary": {
            "total": len(checks),
            **counts,
        },
        "checks": [
            {
                "name": check.name,
                "status": check.status,
                "detail": _truncate(check.detail),
            }
            for check in checks
        ],
    }


def write_report(path: Path, report: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check BaizeFinDB Linux server deployment prerequisites.",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"API base URL for --check-api, default: {DEFAULT_BASE_URL}",
    )
    parser.add_argument(
        "--check-api",
        action="store_true",
        help="Check /health and /health/ready on the target API.",
    )
    parser.add_argument(
        "--check-m5-smoke",
        action="store_true",
        help="Check read-only M5 API JSON contracts on the target API.",
    )
    parser.add_argument(
        "--check-tushare-anns-d-beat-enablement",
        action="store_true",
        help=(
            "Run the offline/no-token Tushare anns_d Beat enablement checklist. "
            "Warnings are non-fatal; only checklist fail status fails this preflight."
        ),
    )
    parser.add_argument(
        "--check-containers",
        action="store_true",
        help="Run docker compose ps for the server overlay.",
    )
    parser.add_argument(
        "--check-systemd-units",
        action="store_true",
        help=(
            "Statically validate tracked infra/linux systemd service/timer templates. "
            "Does not call systemctl or inspect installed units."
        ),
    )
    parser.add_argument(
        "--check-backup",
        action="store_true",
        help="Verify pg_dump is available in the PostgreSQL compose service.",
    )
    parser.add_argument(
        "--backup-check-json-output",
        default=None,
        help=(
            "Write sanitized PostgreSQL backup check-only evidence JSON to this path. "
            "Requires --check-backup and does not export database data."
        ),
    )
    parser.add_argument(
        "--postgres-service",
        default=DEFAULT_POSTGRES_SERVICE,
        help=f"PostgreSQL compose service for --check-backup, default: {DEFAULT_POSTGRES_SERVICE}",
    )
    parser.add_argument(
        "--build",
        action="store_true",
        help="Build baizefindb-api:verify as part of the preflight.",
    )
    parser.add_argument(
        "--strict-env",
        action="store_true",
        help="Fail if .env is missing instead of warning.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=5,
        help="HTTP timeout in seconds for --check-api.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=None,
        help="Optional path to write a structured JSON preflight report.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.backup_check_json_output and not args.check_backup:
        parser.error("--backup-check-json-output requires --check-backup")

    root = find_repo_root()
    checks = [
        check_env(root, strict=args.strict_env),
        run_command(
            "docker compose config",
            ["docker", "compose", "config", "--quiet"],
            root,
        ),
        run_command(
            "docker compose server config",
            server_compose_command("config", "--quiet"),
            root,
        ),
    ]

    if args.build:
        checks.append(
            run_command(
                "docker build api image",
                ["docker", "build", "-t", "baizefindb-api:verify", "."],
                root,
            ),
        )

    if args.check_containers:
        checks.append(
            run_command(
                "docker compose server ps",
                server_compose_command("ps"),
                root,
            ),
        )

    if args.check_systemd_units:
        checks.extend(check_systemd_units(root))

    if args.check_backup:
        if args.backup_check_json_output:
            checks.append(
                check_backup_evidence(
                    root,
                    service=args.postgres_service,
                    check_json_output=args.backup_check_json_output,
                ),
            )
        else:
            checks.append(
                run_command(
                    "postgres pg_dump available",
                    pg_dump_version_command(args.postgres_service),
                    root,
                ),
            )

    if args.check_api:
        checks.extend(
            [
                check_http(args.base_url, "/health", timeout=args.timeout),
                check_http(args.base_url, "/health/ready", timeout=args.timeout),
            ],
        )

    if args.check_m5_smoke:
        checks.extend(check_m5_smoke(args.base_url, timeout=args.timeout))

    if args.check_tushare_anns_d_beat_enablement:
        checks.append(check_tushare_anns_d_beat_enablement())

    for check in checks:
        label = check.status.upper()
        print(f"[{label}] {check.name}")
        if check.detail:
            print(check.detail)

    report = build_report(checks)
    if args.json_output:
        write_report(args.json_output, report)

    return 0 if all(check.ok for check in checks) else 1


def _truncate(text: str, *, limit: int = 700) -> str:
    if len(text) <= limit:
        return text
    return f"{text[: limit - 15]}\n... truncated"


def _parse_systemd_unit(text: str) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    parser.read_string(text)
    return parser


def _check_systemd_forbidden_markers(texts: dict[str, str]) -> CheckResult:
    hits: list[str] = []
    for name, text in texts.items():
        lowered = text.lower()
        for marker in SYSTEMD_FORBIDDEN_MARKERS:
            if marker in lowered:
                hits.append(f"{name}:{marker}")

    return CheckResult(
        "systemd unit files no embedded secrets or alternate delivery",
        "fail" if hits else "ok",
        (
            f"forbidden marker(s): {', '.join(hits[:8])}"
            if hits
            else "no forbidden secret or alternate delivery markers found"
        ),
    )


def _check_required_markers(name: str, text: str, markers: tuple[str, ...]) -> CheckResult:
    missing = [marker for marker in markers if marker not in text]
    return CheckResult(
        name,
        "fail" if missing else "ok",
        (
            f"missing marker(s): {', '.join(missing)}"
            if missing
            else "required markers present"
        ),
    )


def _check_unit_values(
    name: str,
    parser: configparser.ConfigParser,
    expected: tuple[tuple[str, str, str], ...],
) -> CheckResult:
    mismatches = []
    for section, key, expected_value in expected:
        actual = parser[section].get(key, "") if parser.has_section(section) else ""
        if actual != expected_value:
            mismatches.append(
                f"{section}.{key} expected {expected_value}, got {actual or 'missing'}"
            )

    return CheckResult(
        name,
        "fail" if mismatches else "ok",
        (
            f"mismatch(es): {'; '.join(mismatches[:6])}"
            if mismatches
            else "expected values present"
        ),
    )


def _check_monitor_service(text: str) -> CheckResult:
    result = _check_required_markers(
        "systemd monitor service",
        text,
        (
            "server_monitor_check.py",
            "--include-ops-trends",
            "--json-output ${BAIZEFINDB_MONITOR_OUTPUT}",
            "--runtime-json-output ${BAIZEFINDB_RUNTIME_OUTPUT}",
            "--alert-json-output ${BAIZEFINDB_ALERT_OUTPUT}",
            "BAIZEFINDB_ALERT_OUTPUT=evidence/server-alert-payload.json",
        ),
    )
    if result.status == "fail":
        return result
    if "--fail-on-warning" in text:
        return CheckResult(
            "systemd monitor service",
            "fail",
            "monitor timer template must not fail warning-only summaries by default",
        )
    return result


def _check_monitor_timer(parser: configparser.ConfigParser) -> CheckResult:
    return _check_unit_values(
        "systemd monitor timer",
        parser,
        (
            ("Timer", "Unit", "baizefindb-monitor.service"),
            ("Timer", "OnBootSec", "2min"),
            ("Timer", "OnUnitActiveSec", "5min"),
            ("Timer", "AccuracySec", "30s"),
            ("Timer", "Persistent", "true"),
            ("Install", "WantedBy", "timers.target"),
        ),
    )


def _check_alert_telegram_service(text: str) -> CheckResult:
    result = _check_required_markers(
        "systemd alert Telegram service",
        text,
        (
            "server_alert_telegram_env_check.py",
            "--env-file /etc/baizefindb/telegram-alert.env",
            "--strict-permissions",
            "--json-output ${BAIZEFINDB_ALERT_TELEGRAM_ENV_CHECK_OUTPUT}",
            "server_alert_telegram.py ${BAIZEFINDB_ALERT_PAYLOAD}",
            "--send",
            "--dedupe-state ${BAIZEFINDB_ALERT_TELEGRAM_DEDUPE_STATE}",
            "--dedupe-ttl-seconds ${BAIZEFINDB_ALERT_TELEGRAM_TTL_SECONDS}",
            "--json-output ${BAIZEFINDB_ALERT_TELEGRAM_OUTPUT}",
            "EnvironmentFile=-/etc/baizefindb/telegram-alert.env",
        ),
    )
    if result.status == "fail":
        return result
    if "--ignore-dedupe" in text:
        return CheckResult(
            "systemd alert Telegram service",
            "fail",
            "alert service must not bypass dedupe in the template",
        )
    return result


def _check_alert_telegram_timer(
    parser: configparser.ConfigParser,
    text: str,
) -> CheckResult:
    value_check = _check_unit_values(
        "systemd alert Telegram timer",
        parser,
        (
            ("Timer", "Unit", "baizefindb-alert-telegram.service"),
            ("Timer", "OnBootSec", "3min"),
            ("Timer", "OnUnitActiveSec", "5min"),
            ("Timer", "AccuracySec", "30s"),
            ("Timer", "Persistent", "true"),
            ("Install", "WantedBy", "timers.target"),
        ),
    )
    if value_check.status == "fail":
        return value_check

    forbidden = (
        "ExecStart",
        "server_alert_telegram.py",
        "server_monitor_check.py",
        "postgres_backup.py",
        "run_radar_scan",
    )
    return _check_required_absence("systemd alert Telegram timer", text, forbidden)


def _check_postgres_backup_service(text: str) -> CheckResult:
    result = _check_required_markers(
        "systemd PostgreSQL backup service",
        text,
        (
            "postgres_backup.py --backup-dir backups --check-only",
            "--check-json-output ${BAIZEFINDB_BACKUP_CHECK_OUTPUT}",
            "postgres_backup.py --backup-dir backups",
            "BAIZEFINDB_BACKUP_CHECK_OUTPUT=evidence/postgres-backup-timer-check.json",
        ),
    )
    if result.status == "fail":
        return result
    return _check_required_absence(
        "systemd PostgreSQL backup service",
        text,
        ("postgres_restore.py", "--confirm-restore"),
    )


def _check_postgres_backup_timer(parser: configparser.ConfigParser) -> CheckResult:
    return _check_unit_values(
        "systemd PostgreSQL backup timer",
        parser,
        (
            ("Timer", "Unit", "baizefindb-postgres-backup.service"),
            ("Timer", "OnCalendar", "*-*-* 03:15:00"),
            ("Timer", "RandomizedDelaySec", "15min"),
            ("Timer", "Persistent", "true"),
            ("Install", "WantedBy", "timers.target"),
        ),
    )


def _check_required_absence(name: str, text: str, markers: tuple[str, ...]) -> CheckResult:
    present = [marker for marker in markers if marker in text]
    return CheckResult(
        name,
        "fail" if present else "ok",
        (
            f"forbidden marker(s): {', '.join(present)}"
            if present
            else "forbidden markers absent"
        ),
    )


def _read_http_json(
    base_url: str,
    path: str,
    *,
    timeout: int,
    result_name: str,
) -> tuple[object | None, CheckResult | None]:
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    request = Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310
            body = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return None, CheckResult(result_name, "fail", f"HTTP {exc.code}: {_truncate(body)}")
    except (TimeoutError, URLError, OSError) as exc:
        return None, CheckResult(result_name, "fail", str(exc))

    try:
        return json.loads(body), None
    except json.JSONDecodeError as exc:
        return None, CheckResult(result_name, "fail", f"invalid JSON: {exc.msg}")


def _first_signal_id(payload: list[object]) -> int | None:
    for item in payload:
        if not isinstance(item, dict):
            continue
        signal_id = item.get("id")
        if type(signal_id) is int:
            return signal_id
    return None


def _build_tushare_anns_d_beat_enablement_report() -> dict[str, object]:
    try:
        from infra.scripts.check_tushare_anns_d_beat_enablement import build_report
    except ModuleNotFoundError:
        from check_tushare_anns_d_beat_enablement import build_report

    return build_report(check_readiness=False)


def _load_postgres_backup_helper():
    try:
        from infra.scripts import postgres_backup
    except ModuleNotFoundError:
        import postgres_backup

    return postgres_backup


def _run_postgres_backup_check_only(
    root: Path,
    *,
    service: str,
    check_json_output: str,
) -> int:
    postgres_backup = _load_postgres_backup_helper()
    backup_dir = "backups"
    output_path = postgres_backup.backup_path(root, backup_dir, None)
    return postgres_backup.run_check_only(
        root,
        output_path,
        backup_dir=backup_dir,
        explicit_output=None,
        check_json_output=check_json_output,
        service=service,
        db_user=postgres_backup.DEFAULT_DB_USER,
        db_name=postgres_backup.DEFAULT_DB_NAME,
    )


def _format_tushare_anns_d_beat_enablement_summary(report: dict[str, object]) -> str:
    summary = report.get("summary")
    if not isinstance(summary, dict):
        summary = {}

    parts = [
        f"status={report.get('status', 'unknown')}",
        f"mode={report.get('mode', 'unknown')}",
        (
            "summary "
            f"pass={summary.get('pass', 0)} "
            f"warn={summary.get('warn', 0)} "
            f"fail={summary.get('fail', 0)}"
        ),
    ]

    gate_parts = _format_tushare_anns_d_beat_enablement_gates(report)
    if gate_parts:
        parts.append(gate_parts)

    return "; ".join(parts)


def _format_tushare_anns_d_beat_enablement_gates(report: dict[str, object]) -> str:
    checklist = report.get("checklist")
    if not isinstance(checklist, list):
        return ""

    attention_gates = []
    for item in checklist:
        if not isinstance(item, dict):
            continue
        gate_status = item.get("status")
        if gate_status not in {"warn", "fail"}:
            continue
        gate_id = str(item.get("id", "unknown"))
        attention_gates.append(f"{gate_id}:{gate_status}")

    if not attention_gates:
        return ""
    return f"attention gates={', '.join(attention_gates[:6])}"


if __name__ == "__main__":
    sys.exit(main())
