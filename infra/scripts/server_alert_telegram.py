"""Preview or explicitly send server alert payloads to Telegram.

The default mode is preview. Passing --send is required before this script calls
Telegram, and delivery evidence never includes the bot token.
"""

from __future__ import annotations

import argparse
import asyncio
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
) -> tuple[dict[str, Any], int]:
    validate_alert_payload(alert_payload)
    message = format_telegram_message(alert_payload)
    should_notify = bool(alert_payload.get("should_notify"))
    mode = "send" if send else "preview"

    if not should_notify:
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
            ),
            0,
        )

    if send and not _configured_text(bot_token):
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
            ),
            2,
        )

    if send and not chat_ids:
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
            ),
            2,
        )

    if not send:
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
            ),
            0,
        )

    telegram_client = client or TelegramClient(bot_token)
    deliveries = []
    for chat_id in chat_ids[:DEFAULT_MAX_RECIPIENTS]:
        result = await telegram_client.send_message(chat_id, message)
        deliveries.append(delivery_result(chat_id, result))

    all_sent = all(item["sent"] for item in deliveries)
    return (
        build_delivery_report(
            alert_payload,
            source_path=source_path,
            mode=mode,
            status="sent" if all_sent else "failed",
            reason="" if all_sent else "one or more Telegram deliveries failed",
            chat_ids=chat_ids,
            message=message,
            deliveries=deliveries,
        ),
        0 if all_sent else 1,
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
