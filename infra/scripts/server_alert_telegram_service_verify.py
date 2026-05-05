"""Verify manual Telegram alert systemd service evidence.

This verifier is filesystem-only. It reads the JSON evidence produced by the
manual baizefindb-alert-telegram.service path and writes a bounded verdict that
is safe to share during server handoff.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_ENV_CHECK_JSON = Path("evidence/server-alert-telegram-env-check.json")
DEFAULT_DELIVERY_JSON = Path("evidence/server-alert-telegram-send.json")
DEFAULT_DEDUPE_STATE_JSON = Path("evidence/server-alert-telegram-dedupe-state.json")

REPORT_TYPE = "server_alert_telegram_service_verification"
ENV_CHECK_REPORT_TYPE = "server_alert_telegram_env_check"
DELIVERY_REPORT_TYPE = "server_alert_telegram_delivery"
DEDUPE_STATE_REPORT_TYPE = "server_alert_telegram_dedupe_state"

MAX_DETAIL_LENGTH = 240
MAX_RECIPIENT_REFS = 50
READ_ONLY_BOUNDARY = (
    "Telegram alert service evidence verifier; reads existing env-check, delivery, "
    "and dedupe-state JSON evidence only; does not call systemd, send Telegram "
    "messages, read env files, read databases, collect providers, run radar scans, "
    "call models, create reports, perform backups, cleanup, or trading actions; "
    "never prints bot tokens, raw chat ids, raw URLs, authorization values, webhook "
    "secrets, env file contents, message previews, or delivery raw errors"
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    detail: str = ""
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class LoadedEvidence:
    path: Path
    payload: dict[str, Any] | None
    checks: list[CheckResult]


def verify_service_evidence(
    *,
    env_check_json: Path = DEFAULT_ENV_CHECK_JSON,
    delivery_json: Path = DEFAULT_DELIVERY_JSON,
    dedupe_state_json: Path = DEFAULT_DEDUPE_STATE_JSON,
) -> dict[str, Any]:
    checks: list[CheckResult] = []

    env_check = load_evidence(
        env_check_json,
        expected_report_type=ENV_CHECK_REPORT_TYPE,
        name="env check evidence",
        required=True,
    )
    checks.extend(env_check.checks)
    if env_check.payload is not None:
        checks.extend(validate_env_check(env_check.payload))

    delivery = load_evidence(
        delivery_json,
        expected_report_type=DELIVERY_REPORT_TYPE,
        name="delivery evidence",
        required=True,
    )
    checks.extend(delivery.checks)
    delivery_status = ""
    delivery_mode = ""
    recipient_count = 0
    recipient_refs: list[str] = []
    dedupe_enabled = False
    dedupe_state_updated = False
    dedupe_required = False

    if delivery.payload is not None:
        delivery_checks, metadata = validate_delivery(delivery.payload)
        checks.extend(delivery_checks)
        delivery_status = metadata["delivery_status"]
        delivery_mode = metadata["delivery_mode"]
        recipient_count = metadata["recipient_count"]
        recipient_refs = metadata["recipient_refs"]
        dedupe_enabled = metadata["dedupe_enabled"]
        dedupe_state_updated = metadata["dedupe_state_updated"]
        dedupe_required = delivery_status in {"sent", "deduped"}

    dedupe_state_entry_count = 0
    if dedupe_required:
        dedupe_state = load_evidence(
            dedupe_state_json,
            expected_report_type=DEDUPE_STATE_REPORT_TYPE,
            name="dedupe state evidence",
            required=True,
        )
        checks.extend(dedupe_state.checks)
        if dedupe_state.payload is not None:
            dedupe_checks, dedupe_state_entry_count = validate_dedupe_state(
                dedupe_state.payload
            )
            checks.extend(dedupe_checks)
    elif delivery_status == "skipped":
        checks.append(
            CheckResult(
                "dedupe state evidence",
                "warn",
                "dedupe state is not required because delivery was skipped",
            )
        )

    summary = summarize_checks(checks)
    status = "fail" if summary["fail"] else "warn" if summary["warn"] else "ok"
    return {
        "report_type": REPORT_TYPE,
        "generated_at": datetime.now(UTC).isoformat(),
        "status": status,
        "summary": summary,
        "source_files": {
            "env_check_json": _safe_path(env_check_json),
            "delivery_json": _safe_path(delivery_json),
            "dedupe_state_json": _safe_path(dedupe_state_json),
        },
        "env_check_status": _safe_status(env_check.payload),
        "delivery_mode": delivery_mode,
        "delivery_status": delivery_status,
        "dedupe_enabled": dedupe_enabled,
        "dedupe_state_updated": dedupe_state_updated,
        "dedupe_state_entry_count": dedupe_state_entry_count,
        "recipient_count": recipient_count,
        "recipient_refs": recipient_refs,
        "checks": [
            {
                "name": check.name,
                "status": check.status,
                "detail": _safe_text(check.detail),
                "metadata": sanitize_metadata(check.metadata or {}),
            }
            for check in checks
        ],
        "boundary": READ_ONLY_BOUNDARY,
    }


def load_evidence(
    path: Path,
    *,
    expected_report_type: str,
    name: str,
    required: bool,
) -> LoadedEvidence:
    checks: list[CheckResult] = []
    if path.is_symlink():
        checks.append(CheckResult(name, "fail", "evidence file must not be a symlink"))
        return LoadedEvidence(path=path, payload=None, checks=checks)
    if not path.exists():
        status = "fail" if required else "warn"
        checks.append(CheckResult(name, status, f"evidence file is missing: {path}"))
        return LoadedEvidence(path=path, payload=None, checks=checks)
    if not path.is_file():
        checks.append(CheckResult(name, "fail", "evidence file must be a regular file"))
        return LoadedEvidence(path=path, payload=None, checks=checks)

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        checks.append(
            CheckResult(
                name,
                "fail",
                f"could not read evidence file: {exc.__class__.__name__}",
            )
        )
        return LoadedEvidence(path=path, payload=None, checks=checks)
    except json.JSONDecodeError as exc:
        checks.append(
            CheckResult(
                name,
                "fail",
                f"evidence file is not valid JSON: line {exc.lineno} column {exc.colno}",
            )
        )
        return LoadedEvidence(path=path, payload=None, checks=checks)

    if not isinstance(payload, dict):
        checks.append(CheckResult(name, "fail", "evidence file must contain a JSON object"))
        return LoadedEvidence(path=path, payload=None, checks=checks)
    if payload.get("report_type") != expected_report_type:
        checks.append(
            CheckResult(
                name,
                "fail",
                f"expected report_type {expected_report_type}",
                {"found_report_type": _safe_text(str(payload.get("report_type") or ""))},
            )
        )
        return LoadedEvidence(path=path, payload=None, checks=checks)

    checks.append(CheckResult(name, "ok", "evidence file loaded"))
    return LoadedEvidence(path=path, payload=payload, checks=checks)


def validate_env_check(payload: dict[str, Any]) -> list[CheckResult]:
    checks: list[CheckResult] = []
    status = str(payload.get("status") or "").lower()
    if status == "ok":
        checks.append(CheckResult("env check status", "ok", "env preflight status is ok"))
    else:
        checks.append(
            CheckResult(
                "env check status",
                "fail",
                f"env preflight status must be ok; got {status or 'missing'}",
            )
        )

    token_configured = payload.get("token_configured") is True
    checks.append(
        CheckResult(
            "env check token",
            "ok" if token_configured else "fail",
            "bot token is configured" if token_configured else "bot token is not configured",
            {"configured": token_configured},
        )
    )

    chat_id_count = _as_int(payload.get("chat_id_count"))
    checks.append(
        CheckResult(
            "env check recipients",
            "ok" if chat_id_count > 0 else "fail",
            (
                f"{chat_id_count} masked recipient ref(s) configured"
                if chat_id_count > 0
                else "at least one chat id must be configured"
            ),
            {
                "chat_id_count": chat_id_count,
                "chat_refs": sanitize_recipient_refs(payload.get("chat_refs")),
            },
        )
    )
    return checks


def validate_delivery(payload: dict[str, Any]) -> tuple[list[CheckResult], dict[str, Any]]:
    checks: list[CheckResult] = []
    mode = str(payload.get("mode") or "").lower()
    status = str(payload.get("status") or "").lower()
    recipient_count = _as_int(payload.get("recipient_count"))
    recipient_refs = sanitize_recipient_refs(payload.get("recipient_refs"))
    dedupe = _dict_or_empty(payload.get("dedupe"))
    dedupe_enabled = dedupe.get("enabled") is True
    dedupe_state_updated = dedupe.get("state_updated") is True

    checks.append(
        CheckResult(
            "delivery mode",
            "ok" if mode == "send" else "fail",
            f"delivery mode is {mode or 'missing'}",
        )
    )

    if status == "sent":
        checks.extend(validate_sent_delivery(payload, dedupe_enabled, dedupe_state_updated))
    elif status == "deduped":
        checks.append(
            CheckResult(
                "delivery status",
                "ok",
                "delivery was suppressed by existing dedupe state",
            )
        )
        checks.append(
            CheckResult(
                "delivery dedupe",
                "ok" if dedupe_enabled else "fail",
                "dedupe is enabled" if dedupe_enabled else "dedupe must be enabled",
                {"decision": _safe_text(str(dedupe.get("decision") or ""))},
            )
        )
    elif status == "skipped":
        checks.append(
            CheckResult(
                "delivery status",
                "warn",
                "service ran but alert payload did not require a Telegram send",
            )
        )
    elif status in {"preview", "config_error", "failed", "state_error"}:
        checks.append(
            CheckResult(
                "delivery status",
                "fail",
                f"delivery status {status} does not verify manual service send",
            )
        )
    else:
        checks.append(
            CheckResult(
                "delivery status",
                "fail",
                f"delivery status is unsupported: {status or 'missing'}",
            )
        )

    return checks, {
        "delivery_mode": mode,
        "delivery_status": status,
        "recipient_count": recipient_count,
        "recipient_refs": recipient_refs,
        "dedupe_enabled": dedupe_enabled,
        "dedupe_state_updated": dedupe_state_updated,
    }


def validate_sent_delivery(
    payload: dict[str, Any],
    dedupe_enabled: bool,
    dedupe_state_updated: bool,
) -> list[CheckResult]:
    deliveries = _list_of_dicts(payload.get("deliveries"))
    recipient_count = _as_int(payload.get("recipient_count"))
    all_deliveries_sent = bool(deliveries) and all(
        item.get("sent") is True and str(item.get("status") or "").lower() == "sent"
        for item in deliveries
    )
    recipient_count_matches = recipient_count > 0 and len(deliveries) == recipient_count
    return [
        CheckResult(
            "delivery status",
            "ok",
            "delivery status is sent",
        ),
        CheckResult(
            "delivery recipients",
            "ok" if recipient_count_matches else "fail",
            (
                f"{recipient_count} recipient delivery result(s) present"
                if recipient_count_matches
                else "sent delivery must include one result per recipient"
            ),
            {"recipient_count": recipient_count, "delivery_count": len(deliveries)},
        ),
        CheckResult(
            "delivery results",
            "ok" if all_deliveries_sent else "fail",
            (
                "all delivery results are sent"
                if all_deliveries_sent
                else "sent delivery evidence includes non-sent result(s)"
            ),
        ),
        CheckResult(
            "delivery dedupe",
            "ok" if dedupe_enabled and dedupe_state_updated else "fail",
            (
                "dedupe is enabled and state was updated"
                if dedupe_enabled and dedupe_state_updated
                else "sent delivery must have dedupe enabled and state_updated=true"
            ),
            {"enabled": dedupe_enabled, "state_updated": dedupe_state_updated},
        ),
    ]


def validate_dedupe_state(payload: dict[str, Any]) -> tuple[list[CheckResult], int]:
    entries = payload.get("entries")
    entry_count = len(entries) if isinstance(entries, dict) else 0
    status = "ok" if isinstance(entries, dict) and entry_count > 0 else "fail"
    return (
        [
            CheckResult(
                "dedupe state entries",
                status,
                (
                    f"dedupe state contains {entry_count} entry(s)"
                    if status == "ok"
                    else "dedupe state must include a non-empty entries object"
                ),
                {"entry_count": entry_count},
            )
        ],
        entry_count,
    )


def summarize_checks(checks: list[CheckResult]) -> dict[str, int]:
    return {
        "total": len(checks),
        "ok": sum(1 for check in checks if check.status == "ok"),
        "warn": sum(1 for check in checks if check.status == "warn"),
        "fail": sum(1 for check in checks if check.status == "fail"),
    }


def sanitize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in metadata.items():
        safe_key = _safe_text(str(key))
        if isinstance(value, bool | int | float) or value is None:
            sanitized[safe_key] = value
        elif isinstance(value, list):
            sanitized[safe_key] = [_safe_text(str(item)) for item in value[:MAX_RECIPIENT_REFS]]
        else:
            sanitized[safe_key] = _safe_text(str(value))
    return sanitized


def sanitize_recipient_refs(value: object) -> list[str]:
    if not isinstance(value, list):
        return []

    refs: list[str] = []
    for item in value[:MAX_RECIPIENT_REFS]:
        text = str(item)
        if text.startswith("telegram-chat-") and "***" in text:
            refs.append(_safe_text(text))
        else:
            refs.append("telegram-chat-[redacted]")
    return refs


def write_json_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify manual Telegram alert service evidence without sending Telegram.",
    )
    parser.add_argument(
        "--env-check-json",
        type=Path,
        default=DEFAULT_ENV_CHECK_JSON,
        help=f"Env preflight evidence path, default: {DEFAULT_ENV_CHECK_JSON}",
    )
    parser.add_argument(
        "--delivery-json",
        type=Path,
        default=DEFAULT_DELIVERY_JSON,
        help=f"Telegram send evidence path, default: {DEFAULT_DELIVERY_JSON}",
    )
    parser.add_argument(
        "--dedupe-state-json",
        type=Path,
        default=DEFAULT_DEDUPE_STATE_JSON,
        help=f"Dedupe state evidence path, default: {DEFAULT_DEDUPE_STATE_JSON}",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        help="Optional path to write sanitized service verification evidence JSON.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = verify_service_evidence(
        env_check_json=args.env_check_json,
        delivery_json=args.delivery_json,
        dedupe_state_json=args.dedupe_state_json,
    )

    try:
        if args.json_output:
            write_json_report(args.json_output, report)
            print(_format_summary(report, args.json_output))
        else:
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    except OSError as exc:
        print(
            f"[FAIL] could not write Telegram alert service verification report: {exc}",
            file=sys.stderr,
        )
        return 2

    return 1 if report["status"] == "fail" else 0


def _format_summary(report: dict[str, Any], output_path: Path) -> str:
    return (
        f"[{str(report['status']).upper()}] Telegram alert service evidence "
        f"delivery={report['delivery_status'] or 'missing'} "
        f"checks={report['summary']} json_output={output_path}"
    )


def _safe_path(path: Path) -> str:
    return _safe_text(str(path))


def _safe_status(payload: dict[str, Any] | None) -> str:
    if payload is None:
        return ""
    return _safe_text(str(payload.get("status") or ""))


def _safe_text(value: str) -> str:
    text = str(value)
    text = re.sub(r"https?://\S+", "[redacted-url]", text)
    text = re.sub(r"\b\d{6,}:[A-Za-z0-9_-]{12,}\b", "[redacted-token]", text)
    text = re.sub(
        r"(?i)\b(token|secret|password|authorization|webhook)=\S+",
        r"\1=[redacted]",
        text,
    )
    text = re.sub(r"(?<!\*)\b-?\d{5,}\b", "[redacted-number]", text)
    text = text.strip()
    if len(text) <= MAX_DETAIL_LENGTH:
        return text
    return f"{text[:MAX_DETAIL_LENGTH]}..."


def _as_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int | float):
        return int(value)
    return 0


def _dict_or_empty(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_of_dicts(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


if __name__ == "__main__":
    raise SystemExit(main())
