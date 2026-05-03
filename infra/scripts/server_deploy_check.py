"""Deployment preflight checks for the BaizeFinDB Linux server setup."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
SERVER_COMPOSE_FILES = ("docker-compose.yml", "docker-compose.server.yml")
DEFAULT_POSTGRES_SERVICE = "postgres"
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
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        return CheckResult(name, "fail", f"command not found: {exc.filename}")

    if completed.returncode == 0:
        output = completed.stdout.strip() or completed.stderr.strip()
        return CheckResult(name, "ok", _truncate(output))

    detail = "\n".join(
        part
        for part in (completed.stdout.strip(), completed.stderr.strip())
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
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    request = Request(url, headers={"Accept": "application/json"}, method="GET")
    name = f"HTTP JSON {path}"
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310
            body = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return CheckResult(name, "fail", f"HTTP {exc.code}: {_truncate(body)}")
    except (TimeoutError, URLError, OSError) as exc:
        return CheckResult(name, "fail", str(exc))

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        return CheckResult(name, "fail", f"invalid JSON: {exc.msg}")

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
    return [
        check_http_json_fields(
            base_url,
            path,
            required_fields,
            timeout=timeout,
        )
        for path, required_fields in M5_SMOKE_ENDPOINTS
    ]


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
        "--check-containers",
        action="store_true",
        help="Run docker compose ps for the server overlay.",
    )
    parser.add_argument(
        "--check-backup",
        action="store_true",
        help="Verify pg_dump is available in the PostgreSQL compose service.",
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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = find_repo_root()
    checks = [
        check_env(root, strict=args.strict_env),
        run_command("docker compose config", ["docker", "compose", "config"], root),
        run_command(
            "docker compose server config",
            server_compose_command("config"),
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

    if args.check_backup:
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

    for check in checks:
        label = check.status.upper()
        print(f"[{label}] {check.name}")
        if check.detail:
            print(check.detail)

    return 0 if all(check.ok for check in checks) else 1


def _truncate(text: str, *, limit: int = 700) -> str:
    if len(text) <= limit:
        return text
    return f"{text[: limit - 15]}\n... truncated"


if __name__ == "__main__":
    sys.exit(main())
