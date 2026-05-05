"""Validate the local Telegram alert environment file without exposing secrets."""

from __future__ import annotations

import argparse
import json
import re
import stat
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_ENV_FILE = Path("/etc/baizefindb/telegram-alert.env")
REPORT_TYPE = "server_alert_telegram_env_check"
ENV_KEY_PATTERN = re.compile(
    r"^(?:export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<value>.*)$"
)
MAX_DETAIL_LENGTH = 240
READ_ONLY_BOUNDARY = (
    "Telegram alert environment preflight; reads one local env file only; does not "
    "send Telegram messages, read databases, collect providers, run radar scans, "
    "call models, create reports, perform backups, cleanup, or trading actions; "
    "never prints bot tokens, raw chat ids, raw URLs, authorization values, webhook "
    "secrets, or env file contents"
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    detail: str = ""
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class EnvParseResult:
    values: dict[str, str]
    malformed_lines: list[int]


def evaluate_env_file(
    env_file: Path,
    *,
    strict_permissions: bool = False,
) -> dict[str, Any]:
    checks: list[CheckResult] = []
    values: dict[str, str] = {}
    chat_ids: list[int] = []

    file_check = check_env_file(env_file)
    checks.append(file_check)
    if file_check.status != "fail":
        checks.append(check_permissions(env_file, strict=strict_permissions))
        try:
            parse_result = parse_env_file(env_file)
        except OSError as exc:
            checks.append(
                CheckResult(
                    "env file readable",
                    "fail",
                    f"could not read env file: {exc.__class__.__name__}",
                )
            )
            return build_report(
                env_file,
                checks,
                token_configured=False,
                chat_ids=[],
                strict_permissions=strict_permissions,
            )
        values = parse_result.values
        checks.append(check_malformed_lines(parse_result.malformed_lines))
        checks.append(check_bot_token(values))
        chat_check, chat_ids = check_chat_ids(values)
        checks.append(chat_check)

    return build_report(
        env_file,
        checks,
        token_configured=is_configured(values.get("TELEGRAM_BOT_TOKEN")),
        chat_ids=chat_ids,
        strict_permissions=strict_permissions,
    )


def check_env_file(env_file: Path) -> CheckResult:
    if not env_file.exists():
        return CheckResult(
            "env file",
            "fail",
            f"env file does not exist: {_safe_path(env_file)}",
        )
    if env_file.is_symlink():
        return CheckResult("env file", "fail", "env file must not be a symlink")
    if not env_file.is_file():
        return CheckResult("env file", "fail", "env file must be a regular file")
    return CheckResult("env file", "ok", f"env file exists: {_safe_path(env_file)}")


def check_permissions(env_file: Path, *, strict: bool) -> CheckResult:
    try:
        mode = stat.S_IMODE(env_file.stat().st_mode)
    except OSError as exc:
        return CheckResult("env file permissions", "fail", f"could not stat env file: {exc}")

    unsafe_bits = mode & 0o077
    if not unsafe_bits:
        return CheckResult(
            "env file permissions",
            "ok",
            f"mode {mode:03o} is not group/world accessible",
            {"mode": f"{mode:03o}"},
        )

    status = "fail" if strict else "warn"
    return CheckResult(
        "env file permissions",
        status,
        f"mode {mode:03o} exposes group/world bits; use chmod 600",
        {"mode": f"{mode:03o}", "strict": strict},
    )


def parse_env_file(env_file: Path) -> EnvParseResult:
    values: dict[str, str] = {}
    malformed_lines: list[int] = []
    lines = env_file.read_text(encoding="utf-8").splitlines()

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = ENV_KEY_PATTERN.match(line)
        if not match:
            malformed_lines.append(line_number)
            continue
        values[match.group("key")] = _strip_optional_quotes(match.group("value").strip())

    return EnvParseResult(values=values, malformed_lines=malformed_lines)


def check_malformed_lines(line_numbers: list[int]) -> CheckResult:
    if not line_numbers:
        return CheckResult("env syntax", "ok", "all non-comment lines use KEY=value syntax")

    bounded_numbers = ", ".join(str(line) for line in line_numbers[:12])
    suffix = "" if len(line_numbers) <= 12 else f", ... +{len(line_numbers) - 12} more"
    return CheckResult(
        "env syntax",
        "fail",
        f"malformed non-comment line numbers: {bounded_numbers}{suffix}",
        {"malformed_line_count": len(line_numbers)},
    )


def check_bot_token(values: dict[str, str]) -> CheckResult:
    if is_configured(values.get("TELEGRAM_BOT_TOKEN")):
        return CheckResult(
            "TELEGRAM_BOT_TOKEN",
            "ok",
            "bot token is configured",
            {"configured": True},
        )
    return CheckResult(
        "TELEGRAM_BOT_TOKEN",
        "fail",
        "TELEGRAM_BOT_TOKEN is missing or blank",
        {"configured": False},
    )


def check_chat_ids(values: dict[str, str]) -> tuple[CheckResult, list[int]]:
    raw_value = values.get("TELEGRAM_ALLOWED_CHAT_IDS", "")
    chat_ids, invalid_count = parse_chat_ids(raw_value)
    if invalid_count:
        return (
            CheckResult(
                "TELEGRAM_ALLOWED_CHAT_IDS",
                "fail",
                f"contains {invalid_count} invalid chat id value(s)",
                {
                    "valid_count": len(chat_ids),
                    "invalid_count": invalid_count,
                    "chat_refs": [mask_chat_id(chat_id) for chat_id in chat_ids],
                },
            ),
            chat_ids,
        )
    if chat_ids:
        return (
            CheckResult(
                "TELEGRAM_ALLOWED_CHAT_IDS",
                "ok",
                f"{len(chat_ids)} unique chat id(s) configured",
                {"chat_refs": [mask_chat_id(chat_id) for chat_id in chat_ids]},
            ),
            chat_ids,
        )
    return (
        CheckResult(
            "TELEGRAM_ALLOWED_CHAT_IDS",
            "fail",
            "at least one Telegram chat id is required",
            {"chat_refs": []},
        ),
        [],
    )


def parse_chat_ids(raw_value: str | None) -> tuple[list[int], int]:
    chat_ids: list[int] = []
    invalid_count = 0
    for item in str(raw_value or "").split(","):
        text = item.strip()
        if not text:
            continue
        try:
            chat_id = int(text)
        except ValueError:
            invalid_count += 1
            continue
        if chat_id not in chat_ids:
            chat_ids.append(chat_id)
    return chat_ids, invalid_count


def build_report(
    env_file: Path,
    checks: list[CheckResult],
    *,
    token_configured: bool,
    chat_ids: list[int],
    strict_permissions: bool,
) -> dict[str, Any]:
    summary = {
        "total": len(checks),
        "ok": sum(1 for check in checks if check.status == "ok"),
        "warn": sum(1 for check in checks if check.status == "warn"),
        "fail": sum(1 for check in checks if check.status == "fail"),
    }
    status_value = "fail" if summary["fail"] else "warn" if summary["warn"] else "ok"
    return {
        "report_type": REPORT_TYPE,
        "generated_at": datetime.now(UTC).isoformat(),
        "status": status_value,
        "env_file": _safe_path(env_file),
        "strict_permissions": strict_permissions,
        "summary": summary,
        "token_configured": token_configured,
        "chat_id_count": len(chat_ids),
        "chat_refs": [mask_chat_id(chat_id) for chat_id in chat_ids],
        "checks": [
            {
                "name": check.name,
                "status": check.status,
                "detail": _safe_text(check.detail),
                "metadata": check.metadata or {},
            }
            for check in checks
        ],
        "boundary": READ_ONLY_BOUNDARY,
    }


def write_json_report(output: Path, report: dict[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the Telegram alert environment file without sending Telegram.",
    )
    parser.add_argument(
        "env_file_arg",
        nargs="?",
        type=Path,
        help=f"Telegram alert env file path, default: {DEFAULT_ENV_FILE}",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        help=f"Telegram alert env file path, default: {DEFAULT_ENV_FILE}",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        help="Optional path to write sanitized preflight evidence JSON.",
    )
    parser.add_argument(
        "--strict-permissions",
        action="store_true",
        help="Fail instead of warn when the env file is group/world accessible.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.env_file_arg is not None and args.env_file is not None:
        parser.error("pass either positional env file or --env-file, not both")

    env_file = args.env_file or args.env_file_arg or DEFAULT_ENV_FILE
    try:
        report = evaluate_env_file(env_file, strict_permissions=args.strict_permissions)
    except OSError as exc:
        print(f"[FAIL] could not read Telegram alert env file: {exc}", file=sys.stderr)
        return 1

    try:
        if args.json_output:
            write_json_report(args.json_output, report)
            print(_format_summary(report, args.json_output))
        else:
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    except OSError as exc:
        print(f"[FAIL] could not write Telegram alert env check report: {exc}", file=sys.stderr)
        return 2

    return 1 if report["status"] == "fail" else 0


def mask_chat_id(chat_id: int) -> str:
    text = str(chat_id)
    sign = "-" if text.startswith("-") else ""
    digits = text[1:] if sign else text
    suffix = digits[-4:] if len(digits) > 4 else digits
    return f"telegram-chat-{sign}***{suffix}"


def is_configured(value: str | None) -> bool:
    return bool(value and value.strip())


def _strip_optional_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _format_summary(report: dict[str, Any], output_path: Path) -> str:
    return (
        f"[{str(report['status']).upper()}] Telegram alert env preflight "
        f"token_configured={report['token_configured']} "
        f"chat_ids={report['chat_id_count']} json_output={output_path}"
    )


def _safe_path(path: Path) -> str:
    return _safe_text(str(path))


def _safe_text(value: str) -> str:
    text = re.sub(r"https?://\S+", "[redacted-url]", str(value))
    text = re.sub(
        r"(?i)\b(token|secret|password|authorization|webhook)=\S+",
        r"\1=[redacted]",
        text,
    )
    text = text.strip()
    if len(text) <= MAX_DETAIL_LENGTH:
        return text
    return f"{text[:MAX_DETAIL_LENGTH]}..."


if __name__ == "__main__":
    raise SystemExit(main())
