"""Preview or explicitly send server alert payloads to Telegram.

The default mode is preview. Passing --send is required before this script calls
Telegram, and delivery evidence never includes the bot token.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
for import_path in (SCRIPT_DIR, BACKEND_DIR):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

import export_ops_evidence  # noqa: E402

from app.telegram.client import TelegramClient, TelegramSendResult  # noqa: E402

DEFAULT_MAX_RECIPIENTS = 50
DEFAULT_DEDUPE_TTL_SECONDS = 3600
MAX_TELEGRAM_MESSAGE_LENGTH = 3200
MAX_DELIVERY_ERROR_LENGTH = 160
READ_ONLY_BOUNDARY = (
    "Telegram alert delivery adapter; preview by default; --send required for "
    "network delivery; reads existing server_alert_payload JSON only; does not "
    "read/write database, collect providers, run radar scans, call models, create "
    "reports, perform backups, cleanup, or trading actions"
)


class TelegramAlertInputError(ValueError):
    """Raised when alert delivery input or configuration is invalid."""


async def run_delivery(
    alert_payload: dict[str, Any],
    *,
    chat_ids: list[int],
    bot_token: str | None,
    send: bool,
    source_path: Path | None = None,
    client: TelegramClient | None = None,
    dedupe_state_path: Path | None = None,
    dedupe_ttl_seconds: int = DEFAULT_DEDUPE_TTL_SECONDS,
    ignore_dedupe: bool = False,
    now: datetime | None = None,
) -> tuple[dict[str, Any], int]:
    validate_alert_payload(alert_payload)
    validate_dedupe_ttl(dedupe_ttl_seconds)
    message = format_telegram_message(alert_payload)
    should_notify = bool(alert_payload.get("should_notify"))
    mode = "send" if send else "preview"
    now_value = now or datetime.now(UTC)
    dedupe = build_dedupe_report(
        state_path=dedupe_state_path,
        ttl_seconds=dedupe_ttl_seconds,
        ignored=ignore_dedupe,
        decision="not_evaluated",
        state_updated=False,
    )

    if not should_notify:
        dedupe["decision"] = "not_notifying"
        return (
            build_delivery_report(
                alert_payload,
                source_path=source_path,
                mode=mode,
                status="skipped",
                reason="alert payload should_notify=false",
                chat_ids=chat_ids,
                message=message,
                deliveries=[],
                dedupe=dedupe,
            ),
            0,
        )

    if send and not _configured_text(bot_token):
        dedupe["decision"] = "config_error"
        return (
            build_delivery_report(
                alert_payload,
                source_path=source_path,
                mode=mode,
                status="config_error",
                reason="TELEGRAM_BOT_TOKEN is required when --send is supplied",
                chat_ids=chat_ids,
                message=message,
                deliveries=[],
                dedupe=dedupe,
            ),
            2,
        )

    if send and not chat_ids:
        dedupe["decision"] = "config_error"
        return (
            build_delivery_report(
                alert_payload,
                source_path=source_path,
                mode=mode,
                status="config_error",
                reason="at least one Telegram chat id is required when --send is supplied",
                chat_ids=chat_ids,
                message=message,
                deliveries=[],
                dedupe=dedupe,
            ),
            2,
        )

    if not send:
        dedupe["decision"] = "preview"
        deliveries = [
            {
                "chat_ref": mask_chat_id(chat_id),
                "status": "preview",
                "sent": False,
                "error": "",
            }
            for chat_id in chat_ids[:DEFAULT_MAX_RECIPIENTS]
        ]
        return (
            build_delivery_report(
                alert_payload,
                source_path=source_path,
                mode=mode,
                status="preview",
                reason="preview only; pass --send to deliver",
                chat_ids=chat_ids,
                message=message,
                deliveries=deliveries,
                dedupe=dedupe,
            ),
            0,
        )

    dedupe_state: dict[str, Any] | None = None
    if dedupe_state_path is not None:
        dedupe_state = load_dedupe_state(dedupe_state_path)
        if ignore_dedupe:
            dedupe["decision"] = "ignored"
        else:
            existing_entry = find_active_dedupe_entry(
                dedupe_state,
                alert_payload,
                ttl_seconds=dedupe_ttl_seconds,
                now=now_value,
            )
            if existing_entry is not None:
                dedupe.update(
                    {
                        "decision": "suppressed",
                        "matched_entry": sanitize_dedupe_entry(existing_entry),
                    }
                )
                return (
                    build_delivery_report(
                        alert_payload,
                        source_path=source_path,
                        mode=mode,
                        status="deduped",
                        reason="dedupe state suppressed a recently sent alert",
                        chat_ids=chat_ids,
                        message=message,
                        deliveries=[],
                        dedupe=dedupe,
                    ),
                    0,
                )
            dedupe["decision"] = "allowed"
    else:
        dedupe["decision"] = "not_configured"

    telegram_client = client or TelegramClient(bot_token)
    deliveries = []
    for chat_id in chat_ids[:DEFAULT_MAX_RECIPIENTS]:
        result = await telegram_client.send_message(chat_id, message)
        deliveries.append(delivery_result(chat_id, result))

    all_sent = all(item["sent"] for item in deliveries)
    status = "sent" if all_sent else "failed"
    reason = "" if all_sent else "one or more Telegram deliveries failed"
    exit_code = 0 if all_sent else 1
    if all_sent and dedupe_state_path is not None and dedupe_state is not None:
        try:
            update_dedupe_state(
                dedupe_state,
                alert_payload,
                chat_ids=chat_ids,
                deliveries=deliveries,
                now=now_value,
            )
            write_dedupe_state(dedupe_state_path, dedupe_state)
            dedupe["state_updated"] = True
        except OSError as exc:
            status = "state_error"
            reason = f"Telegram sent but dedupe state could not be written: {exc}"
            exit_code = 1

    return (
        build_delivery_report(
            alert_payload,
            source_path=source_path,
            mode=mode,
            status=status,
            reason=reason,
            chat_ids=chat_ids,
            message=message,
            deliveries=deliveries,
            dedupe=dedupe,
        ),
        exit_code,
    )


def delivery_result(chat_id: int, result: TelegramSendResult) -> dict[str, Any]:
    return {
        "chat_ref": mask_chat_id(chat_id),
        "status": "sent" if result.ok else "failed",
        "sent": result.ok,
        "telegram_status_code": result.status_code,
        "error": _safe_text(result.error or ""),
    }


def build_delivery_report(
    alert_payload: dict[str, Any],
    *,
    source_path: Path | None,
    mode: str,
    status: str,
    reason: str,
    chat_ids: list[int],
    message: str,
    deliveries: list[dict[str, Any]],
    dedupe: dict[str, Any],
) -> dict[str, Any]:
    return {
        "report_type": "server_alert_telegram_delivery",
        "generated_at": _now_iso(),
        "mode": mode,
        "status": status,
        "reason": _safe_text(reason),
        "source_alert_payload": {
            "path": _safe_text(str(source_path)) if source_path else "",
            "status": _safe_text(str(alert_payload.get("status") or "")),
            "severity": _safe_text(str(alert_payload.get("severity") or "")),
            "should_notify": bool(alert_payload.get("should_notify")),
            "dedupe_key": _safe_text(str(alert_payload.get("dedupe_key") or "")),
        },
        "recipient_count": len(chat_ids),
        "recipient_refs": [mask_chat_id(chat_id) for chat_id in chat_ids],
        "message_preview": message,
        "deliveries": deliveries,
        "dedupe": dedupe,
        "boundary": READ_ONLY_BOUNDARY,
    }


def format_telegram_message(alert_payload: dict[str, Any]) -> str:
    title = _safe_text(str(alert_payload.get("title") or "BaizeFinDB server alert"))
    status = _safe_text(str(alert_payload.get("status") or "unknown"))
    severity = _safe_text(str(alert_payload.get("severity") or "unknown"))
    dedupe_key = _safe_text(str(alert_payload.get("dedupe_key") or ""))
    summary = _dict_or_empty(alert_payload.get("summary"))
    lines = [
        title,
        f"status={status} severity={severity}",
        (
            "runtime="
            f"{_safe_text(str(summary.get('runtime_status') or 'unknown'))} "
            f"failures={_as_int(summary.get('failure_count'))} "
            f"warnings={_as_int(summary.get('warning_count'))}"
        ),
        f"dedupe={dedupe_key}",
        _safe_text(str(alert_payload.get("message") or "")),
    ]

    items = _list_of_dicts(alert_payload.get("items"))
    if items:
        lines.append("details:")
        for item in items[:5]:
            parts = [
                _safe_text(str(item.get("severity") or "")),
                _safe_text(str(item.get("kind") or "")),
                _safe_text(str(item.get("endpoint") or item.get("code") or item.get("key") or "")),
                _safe_text(str(item.get("detail") or "")),
            ]
            lines.append("- " + " | ".join(part for part in parts if part))

    lines.append("delivery: Telegram alert adapter")
    return export_ops_evidence.bound_text(
        "\n".join(line for line in lines if line),
        limit=MAX_TELEGRAM_MESSAGE_LENGTH,
    )


def load_alert_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise TelegramAlertInputError(f"alert payload does not exist: {path}")
    if path.is_symlink() or not path.is_file():
        raise TelegramAlertInputError(f"alert payload must be a regular file: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TelegramAlertInputError(f"alert payload is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise TelegramAlertInputError("alert payload must be a JSON object")
    validate_alert_payload(payload)
    return payload


def validate_alert_payload(payload: dict[str, Any]) -> None:
    if payload.get("report_type") != "server_alert_payload":
        raise TelegramAlertInputError("alert payload report_type must be 'server_alert_payload'")
    if not isinstance(payload.get("should_notify"), bool):
        raise TelegramAlertInputError("alert payload must include boolean should_notify")
    if not payload.get("status") or not payload.get("severity"):
        raise TelegramAlertInputError("alert payload must include status and severity")


def validate_dedupe_ttl(ttl_seconds: int) -> None:
    if ttl_seconds <= 0:
        raise TelegramAlertInputError("--dedupe-ttl-seconds must be positive")


def build_dedupe_report(
    *,
    state_path: Path | None,
    ttl_seconds: int,
    ignored: bool,
    decision: str,
    state_updated: bool,
) -> dict[str, Any]:
    return {
        "enabled": state_path is not None,
        "state_path": _safe_text(str(state_path)) if state_path else "",
        "ttl_seconds": ttl_seconds,
        "ignored": ignored,
        "decision": decision,
        "state_updated": state_updated,
    }


def load_dedupe_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return new_dedupe_state()
    if path.is_symlink() or not path.is_file():
        raise TelegramAlertInputError(f"dedupe state must be a regular file: {path}")
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TelegramAlertInputError(f"dedupe state is not valid JSON: {exc}") from exc
    if not isinstance(state, dict):
        raise TelegramAlertInputError("dedupe state must be a JSON object")
    if state.get("report_type") != "server_alert_telegram_dedupe_state":
        raise TelegramAlertInputError(
            "dedupe state report_type must be 'server_alert_telegram_dedupe_state'"
        )
    if not isinstance(state.get("entries"), dict):
        raise TelegramAlertInputError("dedupe state must include an entries object")
    return state


def new_dedupe_state() -> dict[str, Any]:
    return {
        "report_type": "server_alert_telegram_dedupe_state",
        "updated_at": "",
        "entries": {},
    }


def find_active_dedupe_entry(
    state: dict[str, Any],
    alert_payload: dict[str, Any],
    *,
    ttl_seconds: int,
    now: datetime,
) -> dict[str, Any] | None:
    dedupe_key = str(alert_payload.get("dedupe_key") or "")
    if not dedupe_key:
        return None
    entry = state["entries"].get(dedupe_entry_key(dedupe_key))
    if not isinstance(entry, dict):
        return None
    sent_at = parse_state_datetime(str(entry.get("last_sent_at") or ""))
    age_seconds = int((now - sent_at).total_seconds())
    if age_seconds < 0:
        age_seconds = 0
    if age_seconds < ttl_seconds:
        entry = dict(entry)
        entry["age_seconds"] = age_seconds
        entry["expires_in_seconds"] = ttl_seconds - age_seconds
        return entry
    return None


def update_dedupe_state(
    state: dict[str, Any],
    alert_payload: dict[str, Any],
    *,
    chat_ids: list[int],
    deliveries: list[dict[str, Any]],
    now: datetime,
) -> None:
    dedupe_key = str(alert_payload.get("dedupe_key") or "")
    if not dedupe_key:
        return
    entries = state["entries"]
    entry_key = dedupe_entry_key(dedupe_key)
    previous = entries.get(entry_key)
    previous_count = _as_int(previous.get("send_count")) if isinstance(previous, dict) else 0
    entries[entry_key] = {
        "dedupe_key": _safe_text(dedupe_key),
        "last_sent_at": now.isoformat(),
        "status": _safe_text(str(alert_payload.get("status") or "")),
        "severity": _safe_text(str(alert_payload.get("severity") or "")),
        "recipient_refs": [mask_chat_id(chat_id) for chat_id in chat_ids],
        "send_count": previous_count + 1,
        "last_delivery_status": "sent",
        "delivery_count": len(deliveries),
    }
    state["updated_at"] = now.isoformat()


def write_dedupe_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)


def sanitize_dedupe_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "dedupe_key": _safe_text(str(entry.get("dedupe_key") or "")),
        "last_sent_at": _safe_text(str(entry.get("last_sent_at") or "")),
        "status": _safe_text(str(entry.get("status") or "")),
        "severity": _safe_text(str(entry.get("severity") or "")),
        "recipient_refs": _safe_list(entry.get("recipient_refs")),
        "send_count": _as_int(entry.get("send_count")),
        "last_delivery_status": _safe_text(str(entry.get("last_delivery_status") or "")),
        "age_seconds": _as_int(entry.get("age_seconds")),
        "expires_in_seconds": _as_int(entry.get("expires_in_seconds")),
    }


def parse_state_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise TelegramAlertInputError("dedupe state contains invalid last_sent_at") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def dedupe_entry_key(dedupe_key: str) -> str:
    return hashlib.sha256(dedupe_key.encode("utf-8")).hexdigest()


def resolve_chat_ids(cli_values: list[str], env_value: str | None) -> list[int]:
    raw_values = cli_values if cli_values else [env_value or ""]
    chat_ids: list[int] = []
    for raw_value in raw_values:
        for item in str(raw_value).split(","):
            text = item.strip()
            if not text:
                continue
            try:
                chat_id = int(text)
            except ValueError as exc:
                raise TelegramAlertInputError(f"invalid Telegram chat id: {text}") from exc
            if chat_id not in chat_ids:
                chat_ids.append(chat_id)
    if len(chat_ids) > DEFAULT_MAX_RECIPIENTS:
        raise TelegramAlertInputError(
            f"at most {DEFAULT_MAX_RECIPIENTS} Telegram recipients are supported"
        )
    return chat_ids


def mask_chat_id(chat_id: int) -> str:
    text = str(chat_id)
    sign = "-" if text.startswith("-") else ""
    digits = text[1:] if sign else text
    suffix = digits[-4:] if len(digits) > 4 else digits
    return f"telegram-chat-{sign}***{suffix}"


def write_json_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Preview or explicitly send a server alert payload to Telegram.",
    )
    parser.add_argument(
        "alert_payload",
        nargs="?",
        type=Path,
        help="Path to server_alert_payload.py JSON output.",
    )
    parser.add_argument(
        "--chat-id",
        action="append",
        default=[],
        help="Telegram chat id. May be repeated or comma-separated.",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="Actually send through Telegram. Default is preview only.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        help="Optional path to write Telegram alert delivery evidence.",
    )
    parser.add_argument(
        "--dedupe-state",
        type=Path,
        help="Optional JSON state path for suppressing recently sent dedupe keys.",
    )
    parser.add_argument(
        "--dedupe-ttl-seconds",
        type=int,
        default=DEFAULT_DEDUPE_TTL_SECONDS,
        help="Dedupe cooldown window in seconds when --dedupe-state is supplied.",
    )
    parser.add_argument(
        "--ignore-dedupe",
        action="store_true",
        help="Bypass dedupe suppression but still update state after successful sends.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.alert_payload is None:
        print("[FAIL] alert payload path is required", file=sys.stderr)
        return 2

    try:
        alert_payload = load_alert_payload(args.alert_payload)
        chat_ids = resolve_chat_ids(args.chat_id, os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS"))
        report, exit_code = asyncio.run(
            run_delivery(
                alert_payload,
                chat_ids=chat_ids,
                bot_token=os.environ.get("TELEGRAM_BOT_TOKEN"),
                send=args.send,
                source_path=args.alert_payload,
                dedupe_state_path=args.dedupe_state,
                dedupe_ttl_seconds=args.dedupe_ttl_seconds,
                ignore_dedupe=args.ignore_dedupe,
            )
        )
    except TelegramAlertInputError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2

    try:
        if args.json_output:
            write_json_report(args.json_output, report)
            print(_format_summary(report, args.json_output))
        else:
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    except OSError as exc:
        print(f"[FAIL] could not write Telegram alert delivery report: {exc}", file=sys.stderr)
        return 2

    return exit_code


def _format_summary(report: dict[str, Any], output_path: Path) -> str:
    return (
        f"[{str(report['status']).upper()}] Telegram alert delivery "
        f"mode={report['mode']} recipients={report['recipient_count']} "
        f"json_output={output_path}"
    )


def _safe_text(value: str) -> str:
    return export_ops_evidence.bound_text(
        export_ops_evidence.redact_text(value),
        limit=MAX_DELIVERY_ERROR_LENGTH,
    )


def _configured_text(value: str | None) -> bool:
    return bool(value and value.strip())


def _dict_or_empty(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_of_dicts(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _safe_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_safe_text(str(item)) for item in value[:DEFAULT_MAX_RECIPIENTS]]


def _as_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int | float):
        return int(value)
    return 0


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


if __name__ == "__main__":
    sys.exit(main())
